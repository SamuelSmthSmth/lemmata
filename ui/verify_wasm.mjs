// Does the engine give the same verdicts inside the browser's Python?
//
// The static build runs the checker in Pyodide (CPython on WebAssembly) with
// the wheels ui/vendor_pyodide.py fetches.  This boots that exact set in Node,
// runs every case the repo pins (ui/wasm_cases.py: the course packs, the
// examples, the capability probes), and compares each verdict with the one
// recorded -- and with a native run of the same cases, for timing.
//
//   uv run python ui/vendor_pyodide.py     # once: fetch Pyodide and the wheels
//   node ui/verify_wasm.mjs [filter]       # filter: only case ids containing it
//
// Any verdict that differs is a failure.  Nothing here is re-pinned to fit.

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const UI = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(UI);
const VENDOR = path.join(UI, "static", "vendor", "pyodide");
const filter = process.argv[2] ?? "";

if (!existsSync(path.join(VENDOR, "pyodide.mjs"))) {
  console.log("SKIPPED: run `uv run python ui/vendor_pyodide.py` first.");
  process.exit(0);
}

const clock = () => performance.now();
const timings = {};

let t = clock();
const { loadPyodide } = await import(path.join(VENDOR, "pyodide.mjs"));
const pyodide = await loadPyodide({ indexURL: `${VENDOR}/` });
timings.boot = clock() - t;

t = clock();
const wheels = readdirSync(path.join(VENDOR, "wheels")).map((name) => path.join(VENDOR, "wheels", name));
await pyodide.loadPackage(wheels, { messageCallback: () => {} });
timings.wheels = clock() - t;

// The repository, read-only, as the engine's source tree.
pyodide.mountNodeFS("/repo", ROOT);
t = clock();
pyodide.runPython(`
import sys
sys.path[:0] = ["/repo/src", "/repo"]
import aether, ui.wasm_cases
`);
timings.import = clock() - t;

// The first check pays for building the parser and warming the solvers.
t = clock();
pyodide.runPython(`
from aether import ProofChecker
ProofChecker().check_source("Let x : Real\\nStep: x + x = 2 * x\\n")
`);
timings.firstCheck = clock() - t;

console.log(
  `pyodide booted in ${(timings.boot / 1000).toFixed(1)} s, wheels ${(timings.wheels / 1000).toFixed(1)} s, ` +
    `engine import ${(timings.import / 1000).toFixed(1)} s, first check ${(timings.firstCheck / 1000).toFixed(1)} s`,
);

pyodide.globals.set("report", (i, n, id, got, ms) => {
  if (ms > 2000 || i % 25 === 0 || i === n) console.log(`  ${String(i).padStart(3)}/${n}  ${ms.toFixed(0).padStart(6)} ms  ${got.padEnd(12)} ${id}`);
});
pyodide.globals.set("only", filter);
const wasm = JSON.parse(pyodide.runPython(`import json; json.dumps(ui.wasm_cases.run(only, progress=report))`));

console.log("running the same cases natively for comparison…");
const native = JSON.parse(execFileSync("uv", ["run", "python", "ui/wasm_cases.py", filter], { cwd: ROOT, encoding: "utf8", maxBuffer: 1 << 26 }));
const nativeById = new Map(native.results.map((r) => [r.id, r]));

const failures = [];
const ratios = [];
for (const r of wasm.results) {
  const n = nativeById.get(r.id);
  if (r.got !== r.expected) failures.push(`${r.id}: pinned ${r.expected}, Pyodide gave ${r.got}${n ? ` (native ${n.got})` : ""}`);
  if (n && n.ms >= 20) ratios.push(r.ms / n.ms);
}

const stats = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  const at = (q) => s[Math.min(s.length - 1, Math.floor(q * s.length))];
  return { median: at(0.5), p95: at(0.95), max: s[s.length - 1], total: s.reduce((a, b) => a + b, 0) };
};
const fmt = (x) => (x >= 1000 ? `${(x / 1000).toFixed(1)} s` : `${x.toFixed(0)} ms`);
const w = stats(wasm.results.map((r) => r.ms));
const nat = stats(native.results.map((r) => r.ms));
const ratio = stats(ratios);

console.log();
console.log(`Python ${wasm.python} (Pyodide) vs ${native.python} (native), ${wasm.results.length} cases`);
console.log(`                 Pyodide      native`);
console.log(`  median         ${fmt(w.median).padEnd(12)} ${fmt(nat.median)}`);
console.log(`  p95            ${fmt(w.p95).padEnd(12)} ${fmt(nat.p95)}`);
console.log(`  slowest        ${fmt(w.max).padEnd(12)} ${fmt(nat.max)}`);
console.log(`  all cases      ${fmt(w.total).padEnd(12)} ${fmt(nat.total)}`);
console.log(`  slowdown (cases ≥20 ms natively): median ${ratio.median.toFixed(1)}×, p95 ${ratio.p95.toFixed(1)}×`);
console.log();
if (failures.length) {
  console.log(`${failures.length} verdict(s) differ:`);
  for (const f of failures) console.log(`  - ${f}`);
  // Each one again, on its own and in full, so the cause is in the log.
  for (const r of wasm.results.filter((x) => x.got !== x.expected)) {
    pyodide.globals.set("case_id", r.id);
    console.log(`\n--- ${r.id} under Pyodide (node ${process.version}), in sequence ---\n${r.report ?? ""}`);
    console.log(`--- the same, on its own ---`);
    console.log(
      pyodide.runPython(`
import traceback
from aether import ProofChecker
case = next(c for c in ui.wasm_cases.cases() if c["id"] == case_id)
try:
    out = "\\n".join(r.format_report() for r in ProofChecker(strict_domains=case["strict"]).check_source(case["source"]))
except Exception:
    out = traceback.format_exc()
out
`),
    );
  }
  process.exit(1);
}
console.log(`every pinned verdict holds under Pyodide (${wasm.results.length} of ${wasm.results.length})`);
