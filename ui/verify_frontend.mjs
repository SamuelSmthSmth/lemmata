// Frontend checks that do not need a browser.
//
//   1. every relative import in every static module resolves, and every named
//      import from the vendored CodeMirror graph actually exists
//   1b. the vendored Web Awesome tree is intact and imports nothing remotely
//   2. every tag in AETHER_TOKENS resolves to a real @lezer/highlight tag
//   3. the Aether tokenizer produces the expected token stream
//
// Run with:  node ui/verify_frontend.mjs

import { existsSync, readdirSync, readFileSync } from "node:fs";

const STATIC = new URL("./static/", import.meta.url);
const moduleAt = (rel) => import(new URL(rel, STATIC).href);

const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
  return condition;
};

// --- 1. module imports ------------------------------------------------------
//
// Every UI module is scanned, not just the entry point: a name imported from
// the wrong vendored package silently resolves to `undefined`, which shows up
// as a missing editor rather than an error.

const MODULE_FILES = [
  ...readdirSync(new URL("js/", STATIC))
    .filter((name) => name.endsWith(".js"))
    .sort()
    .map((name) => `js/${name}`),
  "aether-language.js",
];

const namedImportRe = /import\s*\{([^}]+)\}\s*from\s*"([^"]+)"/g;
const bareImportRe = /import\s*"([^"]+)"/g;

const exportName = (name) => name.trim().split(/\s+as\s+/)[0].trim();
let vendorImports = 0;

for (const rel of MODULE_FILES) {
  const fileUrl = new URL(rel, STATIC);
  const source = readFileSync(fileUrl, "utf8");
  const relative = [
    ...[...source.matchAll(namedImportRe)].map(([, , spec]) => spec),
    ...[...source.matchAll(bareImportRe)].map(([, spec]) => spec),
  ].filter((spec) => spec.startsWith("."));

  for (const spec of relative) {
    const resolved = new URL(spec, fileUrl);
    // Sibling modules touch the DOM at import time, so only their existence can
    // be checked here.  The vendored graph is DOM-free and is actually loaded.
    check(existsSync(resolved), `${rel} imports ${spec}, which does not exist`);
  }

  for (const [, names, spec] of source.matchAll(namedImportRe)) {
    // Only the CodeMirror graph is imported here. Every Web Awesome entry
    // touches `document`/`customElements` at module scope and cannot be loaded
    // in Node at all; that tree is checked structurally further down instead.
    if (!spec.includes("/vendor/esm/")) continue;
    vendorImports += 1;
    const mod = await import(new URL(spec, fileUrl).href);
    for (const name of names.split(",").map(exportName).filter(Boolean)) {
      check(name in mod, `${rel} imports { ${name} } from ${spec}, which does not export it`);
    }
  }
}

check(
  vendorImports >= 5,
  `expected several vendored imports across the UI modules, found ${vendorImports}`,
);

// Names later waves rely on.  Asserting them here turns a silently-undefined
// import into a named failure.
const VENDOR_API = [
  ["@codemirror/state@6.mjs", ["Compartment", "EditorState"]],
  ["@codemirror/view@6.mjs", ["EditorView", "keymap", "placeholder"]],
  ["@codemirror/language@6.mjs", ["indentUnit", "syntaxHighlighting", "StreamLanguage"]],
  ["@codemirror/commands@6.mjs", ["indentLess", "indentMore"]],
];

for (const [spec, names] of VENDOR_API) {
  const mod = await moduleAt(`vendor/esm/${spec}`);
  for (const name of names) {
    check(name in mod, `vendor/esm/${spec} does not export ${name}`);
  }
}

// --- 1b. the vendored Web Awesome tree --------------------------------------
//
// Checked structurally, on purpose. Its entries need a DOM, so they cannot be
// imported here. What matters instead is that the entry still exports what
// components.js imports, and that nothing in the tree imports over the network
// -- the whole point of vendoring it is that the UI runs offline.

const WA_ROOT = new URL("vendor/webawesome/", STATIC);

const waEntry = readFileSync(new URL("webawesome.js", WA_ROOT), "utf8");
for (const name of ["setBasePath", "allDefined"]) {
  check(
    new RegExp(`\\b${name}\\b`).test(waEntry),
    `the Web Awesome entry does not mention ${name}, which components.js imports`,
  );
}

const waModules = [];
(function walk(dir, prefix = "") {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.isDirectory()) walk(new URL(`${entry.name}/`, dir), rel);
    else if (entry.name.endsWith(".js")) waModules.push({ url: new URL(entry.name, dir), rel });
  }
})(WA_ROOT);

// 93 today: 12 components plus the chunks they share. The floor is only there
// to catch a vendor run that resolved almost nothing.
check(waModules.length > 80, `expected a vendored Web Awesome graph, found ${waModules.length}`);

const remoteSpecRe = /(?:from|import)\s*\(?\s*"(https?:\/\/[^"]+)"/g;
const remote = [];
for (const { url, rel } of waModules) {
  for (const [, spec] of readFileSync(url, "utf8").matchAll(remoteSpecRe)) {
    remote.push(`${rel} -> ${spec}`);
  }
}
check(
  remote.length === 0,
  `vendored Web Awesome must not import over the network: ${remote.slice(0, 2).join(", ")}`,
);

// --- 1c. the vendored fonts -------------------------------------------------
//
// fonts.css points at the woff2 subsets by relative URL.  A typo there fails
// silently and invisibly -- the browser just substitutes a system face -- so
// assert every URL resolves to a file that is actually vendored.

const fontsCssPath = new URL("fonts.css", STATIC);
const fontsCss = readFileSync(fontsCssPath, "utf8");
const fontUrls = [...fontsCss.matchAll(/url\(\s*["']?([^"')]+)["']?\s*\)/g)].map(([, u]) => u);

check(fontUrls.length >= 2, `expected fonts.css to reference vendored subsets, found ${fontUrls.length}`);
for (const url of fontUrls) {
  check(
    existsSync(new URL(url, fontsCssPath)),
    `fonts.css references ${url}, which does not exist`,
  );
}

// --- 2. language module + tags ---------------------------------------------

const language = await moduleAt("aether-language.js");

for (const [token, tag] of Object.entries(language.AETHER_TOKENS)) {
  check(tag !== undefined, `AETHER_TOKENS.${token} is an undefined tag`);
}
check(
  Boolean(language.aetherLanguage?.parser) && language.aetherLanguage?.name === "aether",
  "aetherLanguage is not a usable StreamLanguage instance",
);
// The syntax colours are built from a palette editor.js resolves out of the
// design tokens, so they cannot drift from the rest of the app.
const stubPalette = {
  keyword: "#000",
  type: "#000",
  ink: "#000",
  operator: "#000",
  glue: "#000",
  string: "#000",
  comment: "#000",
};
check(
  typeof language.makeHighlightStyle === "function" &&
    Boolean(language.makeHighlightStyle(stubPalette)),
  "makeHighlightStyle must build a syntax style from a resolved palette",
);

// --- 3. tokenizer -----------------------------------------------------------

const { StringStream } = await moduleAt("vendor/esm/@codemirror/language@6.mjs");
const { aetherToken } = language;

function tokenize(line) {
  const stream = new StringStream(line, 4, 4);
  const out = [];
  let guard = 0;
  while (!stream.eol() && guard++ < 1000) {
    const start = stream.pos;
    const token = aetherToken(stream);
    if (stream.pos === start) stream.next(); // never allow a non-advancing loop
    out.push([token, line.slice(start, stream.pos)]);
  }
  return out;
}

function significant(line) {
  return tokenize(line)
    .filter(([, text]) => text.trim() !== "")
    .map(([token, text]) => `${token}:${text}`);
}

const CASES = [
  {
    line: "    Assume h1: Even(n)",
    want: [
      "intro:Assume",
      "variableName:h1",
      "operator::",
      "typeName:Even",
      "operator:(",
      "variableName:n",
      "operator:)",
    ],
  },
  {
    line: 'Theorem: "Even square theorem"',
    want: ["structure:Theorem", "operator::", 'string:"Even square theorem"'],
  },
  {
    line: "    Obtain k : Int such that n = 2 * k from h1",
    want: [
      "intro:Obtain",
      "variableName:k",
      "operator::",
      "typeName:Int",
      "join:such that",
      "variableName:n",
      "operator:=",
      "number:2",
      "operator:*",
      "variableName:k",
      "join:from",
      "variableName:h1",
    ],
  },
  {
    line: "    Hence MultipleOf(n^2, 4)",
    want: [
      "flow:Hence",
      "typeName:MultipleOf",
      "operator:(",
      "variableName:n",
      "operator:^",
      "number:2",
      "operator:,",
      "number:4",
      "operator:)",
    ],
  },
  { line: "# a comment -> ignored by the grammar", want: ["comment:# a comment -> ignored by the grammar"] },
  { line: "-- also a comment", want: ["comment:-- also a comment"] },
  { line: "    Step: = 4 * k^2", want: ["intro:Step", "operator::", "operator:=", "number:4", "operator:*", "variableName:k", "operator:^", "number:2"] },
  { line: "    Base case n = 0:", want: ["structure:Base case", "variableName:n", "operator:=", "number:0", "operator::"] },
  { line: "    Inductive step:", want: ["structure:Inductive step", "operator::"] },
  { line: "    QED", want: ["structure:QED"] },
];

console.log("tokenizer output");
console.log("----------------");
for (const { line, want } of CASES) {
  const got = significant(line);
  const ok = JSON.stringify(got) === JSON.stringify(want);
  console.log(`${ok ? "ok  " : "FAIL"} ${line}`);
  if (!ok) {
    console.log(`      want: ${JSON.stringify(want)}`);
    console.log(`      got:  ${JSON.stringify(got)}`);
    failures.push(`tokenizer mismatch for ${JSON.stringify(line)}`);
  }
}

console.log();
if (failures.length) {
  console.log(`${failures.length} check(s) failed:`);
  for (const failure of failures) console.log(`  - ${failure}`);
  process.exit(1);
}
console.log("frontend checks passed");
