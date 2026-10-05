// Where the engine runs: on the server, or in this browser.
//
// The development server (`python -m ui`) answers /api/* with the engine in
// worker processes.  The static build (ui/build_static.py) has no server: it
// marks the page with <meta name="lemmata-engine" content="browser">, and the
// engine runs here instead, in a Pyodide Web Worker (js/engine-worker.js),
// with the catalogue, capabilities and site details read from static JSON.
//
// Both answer with the same shapes -- the worker runs the very functions the
// server's workers run (ui/engine_jobs.py) -- so js/api.js is the only module
// that knows which one it is talking to.

export const mode = globalThis.document?.querySelector('meta[name="lemmata-engine"]')?.content === "browser" ? "browser" : "server";

// A check gets as long as the server gives it (AETHER_CHECK_BUDGET's default).
// localStorage "aether:check-budget-ms" overrides it, for a slow machine or a
// test that needs a check to overrun.
export const BUDGET_MS = (() => {
  try {
    const value = Number(globalThis.localStorage?.getItem("aether:check-budget-ms"));
    return value > 0 ? value : 20000;
  } catch {
    return 20000;
  }
})();

const listeners = new Set();
let status = { state: mode === "browser" ? "idle" : "ready", detail: "" };

/** Follow the in-browser engine's state: idle, loading, ready, restarting, failed. */
export function onEngineStatus(listener) {
  listeners.add(listener);
  listener(status);
  return () => listeners.delete(listener);
}

function setStatus(state, detail = "") {
  status = { state, detail };
  for (const listener of listeners) listener(status);
}

let worker = null;
let ready = null; // a promise that settles when the current worker can take jobs
let seq = 0;
const pending = new Map(); // id -> {resolve, reject}
let queue = Promise.resolve(); // one job at a time: Python in a worker is single-threaded

function start(restarting = false) {
  worker = new Worker(new URL("./engine-worker.js", import.meta.url), { type: "module" });
  setStatus(restarting ? "restarting" : "loading", "Loading the checker");
  ready = new Promise((resolve, reject) => {
    worker.addEventListener("message", (event) => {
      const data = event.data;
      if (data.type === "progress") setStatus(restarting ? "restarting" : "loading", data.detail);
      else if (data.type === "ready") {
        setStatus("ready");
        resolve();
      } else if (data.type === "failed") {
        setStatus("failed", data.error);
        reject(new Error(`The checker could not start: ${data.error}`));
      } else if (data.id !== undefined && pending.has(data.id)) {
        const { resolve: done, reject: fail } = pending.get(data.id);
        pending.delete(data.id);
        if (data.ok) done(data.result);
        else fail(new Error(data.error));
      }
    });
    worker.addEventListener("error", (event) => {
      setStatus("failed", event.message);
      reject(new Error(`The checker could not start: ${event.message}`));
    });
  });
  ready.catch(() => {});
}

class Overran extends Error {}

/**
 * Run one job in the worker, under the budget; an overrun replaces the worker.
 * A job whose `signal` aborts while it waits its turn is dropped, so typing
 * does not queue up a check per keystroke.
 */
function job(kind, payload, { budget = BUDGET_MS, signal = null } = {}) {
  if (!worker) start();
  const run = async () => {
    await ready;
    if (signal?.aborted) throw new DOMException("The check was superseded", "AbortError");
    const id = ++seq;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        worker.terminate();
        start(true);
        reject(new Overran(`stopped after ${budget / 1000} s`));
      }, budget);
      pending.set(id, {
        resolve: (value) => (clearTimeout(timer), resolve(value)),
        reject: (error) => (clearTimeout(timer), reject(error)),
      });
      worker.postMessage({ id, kind, payload });
    });
  };
  const result = queue.then(run, run);
  queue = result.catch(() => {});
  return result;
}

/** Start loading the engine now, so the first check does not wait for it. */
export function warmUp() {
  if (mode === "browser" && !worker) start();
}

/** The same body /api/check answers with when a check overruns its budget. */
function timeoutResponse(strictDomains, started) {
  return {
    verdict: "TIMEOUT",
    reports: [],
    parse_error: {
      message:
        "One of the steps asks the solver something it cannot settle quickly, so the check was stopped " +
        "rather than left running. Split the step into smaller ones, or add the hypothesis it depends on.",
      headline: `Checking stopped after ${(BUDGET_MS / 1000).toFixed(BUDGET_MS % 1000 ? 1 : 0)} s`,
      line: null,
      col: null,
    },
    summary: { total: 0, valid: 0, warnings: 0, invalid: 0 },
    strict_domains: strictDomains,
    duration_ms: performance.now() - started,
  };
}

// ---------------------------------------------------------------------------
// The browser's answers to what api.js asks
// ---------------------------------------------------------------------------

export const browser = {
  async check({ source, strictDomains, showWorking = false, files, path, citations, signal }) {
    const started = performance.now();
    try {
      return await job("check", { source, strict_domains: strictDomains, show_working: showWorking, files, path, citations }, { signal });
    } catch (error) {
      if (error instanceof Overran) return timeoutResponse(strictDomains, started);
      throw error;
    }
  },
  async latex({ source, standalone, strictDomains, breakdown, session }) {
    try {
      const latex = await job("latex", { source, standalone, strict_domains: strictDomains, breakdown, session, style: "plain" });
      return { latex };
    } catch (error) {
      return { latex: "", error: error instanceof Overran ? `checking the proof for the report ${error.message}` : error.message };
    }
  },
  async lean({ source, files, path, citations }) {
    try {
      return await job("lean", { source, files, path, citations });
    } catch (error) {
      return { lean: "", rows: [], untranslated: [], error: error instanceof Overran ? `checking the proof for the export ${error.message}` : error.message };
    }
  },
  async validatePack(data) {
    return job("validate_pack", { pack: data });
  },
  async json(name) {
    const response = await fetch(new URL(`../data/${name}.json`, import.meta.url));
    if (!response.ok) throw new Error(`${name} could not be loaded (${response.status})`);
    return response.json();
  },
};
