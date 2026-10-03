// The engine, in the browser: Pyodide in a Web Worker.
//
// Used by the static build only (see js/backend.js).  It loads the vendored
// Pyodide runtime, installs the engine's wheels (SymPy, mpmath, Lark, z3),
// unpacks the engine itself (static/engine/engine.zip: the `aether` package
// plus ui/engine_jobs.py and friends), and then answers jobs with exactly the
// functions the server's worker processes run -- engine_jobs.Engine.run.
//
// Messages in:  {id, kind, payload}            kind: check | latex | validate_pack
// Messages out: {type: "progress", stage, detail}
//               {type: "ready"} | {type: "failed", error}
//               {id, ok: true, result} | {id, ok: false, error}
//
// A job that overruns its budget is not interrupted here: Python cannot be
// stopped from inside.  The page terminates this worker instead and starts a
// fresh one, exactly as the server kills a stalled worker process.

const VENDOR = new URL("../vendor/pyodide/", import.meta.url);
const ENGINE = new URL("../engine/engine.zip", import.meta.url);

let engine = null;
const progress = (stage, detail = "") => self.postMessage({ type: "progress", stage, detail });

async function boot() {
  progress("runtime", "Loading Python");
  const { loadPyodide } = await import(new URL("pyodide.mjs", VENDOR).href);
  const pyodide = await loadPyodide({ indexURL: VENDOR.href });

  progress("packages", "Loading SymPy and Z3");
  const wheels = await (await fetch(new URL("wheels.json", VENDOR))).json();
  await pyodide.loadPackage(
    wheels.map((name) => new URL(`wheels/${name}`, VENDOR).href),
    { messageCallback: () => {}, errorCallback: (message) => progress("packages", message) },
  );

  progress("engine", "Starting the checker");
  const archive = await fetch(ENGINE);
  if (!archive.ok) throw new Error(`the engine archive could not be loaded (${archive.status})`);
  pyodide.unpackArchive(await archive.arrayBuffer(), "zip", { extractDir: "/engine" });
  pyodide.runPython(`
import sys
sys.path.insert(0, "/engine")
import json
from ui.engine_jobs import Engine, error_text
_engine = Engine()

def _run(kind, payload_json):
    try:
        return json.dumps({"ok": True, "result": _engine.run(kind, json.loads(payload_json))})
    except Exception as exc:
        return json.dumps({"ok": False, "error": error_text(exc)})
`);
  engine = pyodide.globals.get("_run");
}

const booted = boot().then(
  () => self.postMessage({ type: "ready" }),
  (error) => self.postMessage({ type: "failed", error: String(error?.message ?? error) }),
);

self.onmessage = async (event) => {
  const { id, kind, payload } = event.data;
  await booted;
  if (!engine) {
    self.postMessage({ id, ok: false, error: "the checker did not start" });
    return;
  }
  const answer = JSON.parse(engine(kind, JSON.stringify(payload)));
  self.postMessage({ id, ...answer });
};
