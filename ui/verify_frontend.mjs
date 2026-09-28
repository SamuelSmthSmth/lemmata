// Frontend checks that do not need a browser.
//
//   1. every relative import in every static module resolves, and every named
//      import from the vendored CodeMirror graph actually exists
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
    if (!spec.includes("/vendor/")) continue;
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

// --- 2. language module + tags ---------------------------------------------

const language = await moduleAt("aether-language.js");

for (const [token, tag] of Object.entries(language.AETHER_TOKENS)) {
  check(tag !== undefined, `AETHER_TOKENS.${token} is an undefined tag`);
}
check(
  Boolean(language.aetherLanguage?.parser) && language.aetherLanguage?.name === "aether",
  "aetherLanguage is not a usable StreamLanguage instance",
);
check(
  Boolean(language.aetherHighlightStyles?.light && language.aetherHighlightStyles?.dark),
  "aetherHighlightStyles must define both a light and a dark style",
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
