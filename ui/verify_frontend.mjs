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

// --- 2b. the palette --------------------------------------------------------
//
// The colours are built from a palette editor.js resolves out of the design
// tokens, so they cannot drift from the rest of the app.  Three files have to
// agree about the key list -- aether-language.js, styles.css and editor.js --
// and a mismatch in any of them shows up only as a token that is quietly not
// coloured, so all three are checked against each other here.

const PALETTE_KEYS = language.PALETTE_KEYS;
check(Array.isArray(PALETTE_KEYS) && PALETTE_KEYS.length >= 10, "PALETTE_KEYS is missing or short");

const stubPalette = Object.fromEntries(PALETTE_KEYS.map((key) => [key, "#000"]));
check(
  typeof language.makeHighlightStyle === "function" &&
    Boolean(language.makeHighlightStyle(stubPalette)),
  "makeHighlightStyle must build a syntax style from a resolved palette",
);

const stylesCss = readFileSync(new URL("styles.css", STATIC), "utf8");
const editorJs = readFileSync(new URL("js/editor.js", STATIC), "utf8");
// Comments are stripped before any rule is parsed: several of them contain
// braces and semicolons (\mathbb{N} and `grid-template-areas: "a b c";` both
// appear in prose), and a naive scan would end the wrong rule at the wrong
// character.
const stylesCssCode = stylesCss.replace(/\/\*[\s\S]*?\*\//g, " ");

for (const key of PALETTE_KEYS) {
  const variable = language.tokenVariable(key);
  check(
    stylesCss.includes(`${variable}:`),
    `styles.css defines no ${variable} for the ${key} palette key`,
  );
  check(
    editorJs.includes(`"${variable}"`),
    `js/editor.js does not resolve ${variable}, so ${key} would fall back to a literal`,
  );
}

/** The body of the first rule whose selector contains `needle`. */
function ruleBody(needle) {
  const start = stylesCssCode.indexOf(needle);
  if (start === -1) return null;
  const open = stylesCssCode.indexOf("{", start);
  const close = stylesCssCode.indexOf("}", open);
  if (open === -1 || close === -1) return null;
  return stylesCssCode.slice(open + 1, close);
}

// The vivid scheme is the point of the toggle: if its hues ever collapse onto
// one another it stops being vivid, and nothing else would notice.
for (const selector of [
  ':root[data-syntax="vivid"]',
  ':root[data-theme="dark"][data-syntax="vivid"]',
]) {
  const body = ruleBody(selector);
  if (!check(body !== null, `styles.css has no ${selector} rule`)) continue;

  const colours = new Set();
  for (const key of PALETTE_KEYS) {
    const variable = language.tokenVariable(key);
    const match = body.match(new RegExp(`${variable}\\s*:\\s*(#[0-9a-fA-F]{3,8})`));
    if (!check(match, `${selector} does not set ${variable} to a hex colour`)) continue;
    colours.add(match[1].toLowerCase());
  }

  // A few keys are deliberately quiet (glue words, comments, plain ink), so the
  // bar is "clearly more than one hue" rather than "all distinct".
  check(
    colours.size >= 8,
    `${selector} uses only ${colours.size} distinct colours across ${PALETTE_KEYS.length} keys -- not vivid`,
  );
}

// ...and the mono scheme is the quiet one it claims to be.  Its values are
// declared in the app's own :root block -- the one that defines --font-mono --
// where each key aliases the palette rather than naming a hue of its own.
// The search has to be scoped: the vivid overrides come *before* that block in
// the file, since a rule with an attribute selector outranks a bare :root
// wherever it sits.
{
  const baseStart = stylesCssCode.indexOf("--font-mono:");
  const baseEnd = stylesCssCode.indexOf("\n}", baseStart);
  const base = baseStart === -1 ? "" : stylesCssCode.slice(baseStart, baseEnd);
  const values = new Set();
  for (const key of PALETTE_KEYS) {
    const variable = language.tokenVariable(key);
    const match = base.match(new RegExp(`${variable}\\s*:\\s*([^;]+);`));
    if (!check(match, `the mono :root block defines no default for ${variable}`)) continue;
    const value = match[1].trim();
    values.add(value);
    check(
      value.startsWith("var("),
      `the default ${variable} is the literal ${value}; mono should follow the palette`,
    );
  }
  check(values.size <= 4, `the mono scheme uses ${values.size} distinct values -- it should stay quiet`);
}

// --- 2c. panel arrangements -------------------------------------------------
//
// layout.js keeps its pure half free of the DOM so it can be loaded here; only
// the interaction wiring needs a browser (ui/verify_browser.py covers that).
// The one thing the two halves cannot check about each other is the CSS, so
// every arrangement id is matched against a [data-layout] rule, and each of
// those rules is required to use all three slot names.

const layoutModule = await moduleAt("js/layout.js");
const { ARRANGEMENTS, DEFAULT_ORDER, SLOTS, layout, layoutApi } = layoutModule;

check(ARRANGEMENTS.length >= 4, `expected at least four arrangements, found ${ARRANGEMENTS.length}`);
check(
  new Set(ARRANGEMENTS.map((a) => a.id)).size === ARRANGEMENTS.length,
  "arrangement ids are not unique",
);
for (const arrangement of ARRANGEMENTS) {
  check(
    Boolean(arrangement.label) && Boolean(arrangement.hint),
    `arrangement ${arrangement.id} is missing a label or a hint`,
  );
  check(
    layoutModule.isArrangement(arrangement.id) && !layoutModule.isArrangement("nope"),
    `isArrangement disagrees about ${arrangement.id}`,
  );

  const body = ruleBody(`[data-layout="${arrangement.id}"]`);
  if (!check(body !== null, `styles.css has no [data-layout="${arrangement.id}"] rule`)) continue;

  const letters = new Set();
  for (const [, areas] of body.matchAll(/grid-template-areas:\s*([^;]+);/g)) {
    for (const [, name] of areas.matchAll(/"([^"]*)"/g)) {
      for (const letter of name.split(/\s+/).filter(Boolean)) letters.add(letter);
    }
  }
  check(
    letters.size === SLOTS.length && SLOTS.every((slot) => letters.has(slot)),
    `[data-layout="${arrangement.id}"] places ${[...letters].join(",") || "nothing"} rather than every slot`,
  );
}

check(
  SLOTS.length === DEFAULT_ORDER.length,
  `${SLOTS.length} slots for ${DEFAULT_ORDER.length} panes`,
);
for (const slot of SLOTS) {
  check(
    stylesCss.includes(`.pane[data-slot="${slot}"]`) || stylesCss.includes(`.pane[data-slot]`),
    `styles.css has no rule for slot ${slot}`,
  );
}

// Storage is user-editable and outlives upgrades, so normalization has to
// repair it rather than trust it.
const repaired = layoutModule.normalizeLayout({
  arrangement: "sideways",
  order: ["context", "ghost", "context"],
});
check(
  repaired.arrangement === ARRANGEMENTS[0].id,
  `an unknown arrangement became ${repaired.arrangement}`,
);
check(
  JSON.stringify(repaired.order) === JSON.stringify(["context", "editor", "audit"]),
  `a damaged order was repaired to ${repaired.order.join(",")}`,
);
check(
  JSON.stringify(layoutModule.normalizeLayout(null).order) === JSON.stringify(DEFAULT_ORDER),
  "an empty store did not fall back to the default order",
);

// Swapping is symmetric and ignores nonsense.
check(
  JSON.stringify(layoutModule.swapInOrder(DEFAULT_ORDER, "editor", "context")) ===
    JSON.stringify(["context", "audit", "editor"]),
  "swapInOrder did not swap the two panes",
);
check(
  layoutModule.swapInOrder(DEFAULT_ORDER, "editor", "editor") === DEFAULT_ORDER &&
    layoutModule.swapInOrder(DEFAULT_ORDER, "editor", "ghost") === DEFAULT_ORDER,
  "swapInOrder changed something for a no-op swap",
);

// Moving clamps at the ends instead of wrapping.
check(
  layoutModule.moveInOrder(DEFAULT_ORDER, "editor", -1) === DEFAULT_ORDER,
  "moveInOrder moved the first pane off the front",
);
check(
  JSON.stringify(layoutModule.moveInOrder(DEFAULT_ORDER, "editor", 2)) ===
    JSON.stringify(["audit", "context", "editor"]),
  "moveInOrder did not carry a pane to the end",
);
check(
  JSON.stringify(layoutModule.moveInOrder(DEFAULT_ORDER, "context", -1)) ===
    JSON.stringify(["editor", "context", "audit"]),
  "moveInOrder did not move a pane one slot back",
);
check(
  layoutModule.moveInOrder(DEFAULT_ORDER, "editor", 0) === DEFAULT_ORDER,
  "a zero-length move returned a new order",
);

check(
  layout.arrangement === ARRANGEMENTS[0].id &&
    JSON.stringify(layoutApi.current.order) === JSON.stringify(DEFAULT_ORDER),
  `a fresh session did not start on ${ARRANGEMENTS[0].id}`,
);

// The controls layout.js looks for must exist, since it bails silently when
// they do not.
const indexHtml = readFileSync(new URL("index.html", STATIC), "utf8");
for (const id of ["layout-toggle", "layout-popup", "layout-options", "syntax-toggle"]) {
  check(indexHtml.includes(`id="${id}"`), `index.html has no #${id}`);
}
check(indexHtml.includes('class="layout"'), "index.html has no main.layout grid");
check(
  /aether-syntax/.test(indexHtml),
  "index.html does not resolve the syntax scheme before first paint",
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
  // The notes' notation: Unicode symbols, infinity and postfix factorial.
  {
    line: "Therefore ∀ ε > 0, ∃ δ ∈ ℝ, δ ≤ ε",
    want: [
      "flow:Therefore", "flow:∀", "macro:ε", "operator:>", "number:0", "operator:,",
      "flow:∃", "macro:δ", "logicKw:∈", "typeName:ℝ", "operator:,", "macro:δ", "operator:≤", "macro:ε",
    ],
  },
  {
    line: "Step: lim(1/x, x, oo) = \\infty",
    want: [
      "intro:Step", "operator::", "mathFn:lim", "operator:(", "number:1", "operator:/", "variableName:x",
      "operator:,", "variableName:x", "operator:,", "number:oo", "operator:)", "operator:=", "number:\\infty",
    ],
  },
  { line: "Step: n! = gcd(a⁻¹, x²)", want: [
    "intro:Step", "operator::", "variableName:n", "operator:!", "operator:=", "mathFn:gcd", "operator:(",
    "variableName:a", "number:⁻¹", "operator:,", "variableName:x", "number:²", "operator:)",
  ] },
  // Math functions are call-shaped, so they get their own token rather than
  // sharing the introduction keywords -- the vivid scheme colours them apart.
  {
    line: "    Step: sqrt(x) >= 0",
    want: [
      "intro:Step",
      "operator::",
      "mathFn:sqrt",
      "operator:(",
      "variableName:x",
      "operator:)",
      "operator:>=",
      "number:0",
    ],
  },
  {
    // The escapes the grammar accepts (\\mathbb{N}, \\epsilon) are macros; the
    // bare capital that follows is still a type name.
    line: "    Given n : \\mathbb{N}",
    want: [
      "intro:Given",
      "variableName:n",
      "operator::",
      "macro:\\mathbb",
      "operator:{",
      "typeName:N",
      "operator:}",
    ],
  },
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
