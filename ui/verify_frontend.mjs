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
const { ARRANGEMENTS, DEFAULT_ARRANGEMENT, DEFAULT_ORDER, SLOTS, layout, layoutApi } = layoutModule;

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
  repaired.arrangement === DEFAULT_ARRANGEMENT,
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
  layout.arrangement === DEFAULT_ARRANGEMENT &&
    JSON.stringify(layoutApi.current.order) === JSON.stringify(DEFAULT_ORDER),
  `a fresh session did not start on ${DEFAULT_ARRANGEMENT}`,
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

// --- 4. workspace archives --------------------------------------------------
//
// The workspace exports and imports as .zip with a hand-written codec, so it
// is checked against a real implementation in both directions: Python's
// zipfile must read what we write, and we must read what it writes (deflated,
// as every desktop archiver does).

const { writeZip, readZip } = await moduleAt("js/zip.js");
const { execFileSync } = await import("node:child_process");
const { mkdtempSync, writeFileSync } = await import("node:fs");
const { tmpdir } = await import("node:os");
const { join } = await import("node:path");

const sample = [
  { path: "Even square.aether", text: 'Theorem: "Even square"\nProof:\n    Given n : Int\nQED\n' },
  { path: "sheets/week 1/ε–δ.aether", text: "Therefore ∀ ε > 0, ∃ δ > 0, δ < ε\n" },
];
const roundTrip = await readZip(writeZip(sample));
check(JSON.stringify(roundTrip) === JSON.stringify(sample), "zip.js does not round-trip its own archive");

const scratch = mkdtempSync(join(tmpdir(), "aether-zip-"));
const ours = join(scratch, "ours.zip");
writeFileSync(ours, writeZip(sample));
const python = (code, ...args) => execFileSync("python3", ["-c", code, ...args], { encoding: "utf8" });
try {
  const listed = JSON.parse(
    python(
      "import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); assert z.testzip() is None; print(json.dumps([[i.filename, z.read(i).decode()] for i in z.infolist()]))",
      ours,
    ),
  );
  check(
    JSON.stringify(listed) === JSON.stringify(sample.map((e) => [e.path, e.text])),
    "Python's zipfile does not read the archive zip.js writes",
  );
  const theirs = join(scratch, "theirs.zip");
  python(
    "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1],'w',zipfile.ZIP_DEFLATED); z.writestr('folder/', ''); z.writestr('folder/lemma.aether', 'Let x : Real\\n' * 40); z.close()",
    theirs,
  );
  const read = await readZip(readFileSync(theirs));
  check(
    read.length === 1 && read[0].path === "folder/lemma.aether" && read[0].text === "Let x : Real\n".repeat(40),
    "zip.js cannot read a deflated archive written by Python's zipfile",
  );
} catch (error) {
  check(false, `zip interop check could not run: ${error.message}`);
}
let rejected = false;
try {
  await readZip(new TextEncoder().encode("not an archive"));
} catch (error) {
  rejected = /not a ZIP/.test(error.message);
}
check(rejected, "zip.js does not reject a non-archive with a readable message");
console.log("workspace archives checked");

// --- packs.js: the browser's package manager for course packs ---------------
const packs = await moduleAt("js/packs.js");
const { readFileSync: readCourse } = await import("node:fs");
const course = JSON.parse(readCourse(new URL("../../courses/mth2010.json", STATIC), "utf8"));
check(packs.compareVersions("1.2.0", "1.10.0") < 0, "compareVersions does not order 1.2.0 before 1.10.0");
check(packs.compareVersions("1.0.0", "1.0.0-beta") > 0, "compareVersions does not put a release after its pre-release");
check(packs.compareVersions("2.0.0", "2.0.0") === 0, "compareVersions does not find equal versions equal");
check(packs.packLabel(course) === "MTH2010", "packLabel does not use the course code");
check(packs.packLabel({ ...course, courses: [] }) === course.title, "packLabel does not fall back to the title without a course");
check(packs.splitKey("core/mth2010/lagrange")?.name === "core/mth2010", "splitKey does not split on the last slash");
check(packs.migrateOrigin("mth2008/theorem-1-1") === "core/mth2008/theorem-1-1", "migrateOrigin does not scope a legacy origin");
check(packs.migrateOrigin("examples/file-guarded_division_scratchpad") === "core/examples/file-guarded-division-scratchpad", "migrateOrigin does not re-slug an examples file entry");
check(packs.migrateOrigin("core/mth2008/x") === "core/mth2008/x", "migrateOrigin changes an origin that is already scoped");

const edited = structuredClone(course);
edited.version = "1.1.0";
edited.entries[0].source += "\n";
edited.entries.pop();
edited.entries.push({ ...course.entries[1], id: "brand-new" });
const diff = packs.diffPacks(course, edited);
check(diff.changed.length === 1 && diff.added.length === 1 && diff.removed.length === 1, `diffPacks miscounts: ${JSON.stringify(diff)}`);
check(packs.describeDiff(diff) === "1 changed, 1 new, 1 removed", `describeDiff says "${packs.describeDiff(diff)}"`);
check(packs.describeDiff(packs.diffPacks(course, course)) === null, "describeDiff describes no change");

const record = { name: course.name, version: course.version, origin: "bundled", pack: course };
check(packs.updatesFor([edited], [record]).length === 1, "updatesFor misses a newer version");
check(packs.updatesFor([course], [record]).length === 0, "updatesFor offers an identical pack");
check(packs.updatesFor([{ ...course, version: "0.9.0" }], [record]).length === 0, "updatesFor offers an older version");
check(packs.browsable([course, edited], [record]).length === 0 && packs.browsable([course], []).length === 1, "browsable lists installed packs");

const sources = packs.importSources([course]);
const trapIds = course.entries.filter((e) => e.kind === "trap").map((e) => e.id);
check(Object.keys(sources).every((k) => k.startsWith("@core/mth2010/") && k.endsWith(".aether")), "importSources keys are not @name/entry.aether");
check(trapIds.every((id) => !(`@core/mth2010/${id}.aether` in sources)), "importSources lends out a trap");
check(packs.importLine("core/mth2010", "lagrange") === 'import "@core/mth2010/lagrange"', "importLine is not the short import form");
check(packs.importsFromPacks('Let x : Real\nimport "@core/a/b"\n') && !packs.importsFromPacks('import "lemmas"\n'), "importsFromPacks misreads an import");

const file = packs.packToFile(course);
check(file.filename === "core-mth2010.pack.json" && JSON.stringify(packs.parsePackFile(file.text)) === JSON.stringify(course), "a pack does not survive .pack.json round-trip");
let notJson = false;
try {
  packs.parsePackFile("{ nope");
} catch (error) {
  notJson = /not JSON/.test(error.message);
}
check(notJson, "parsePackFile does not reject a non-JSON file readably");
// Authoring: a folder exports as a pack, true by construction.
const manifest = packs.newManifest("Sheets/Week 1");
check(manifest.name === "me/week-1" && manifest.courses.length === 0, `newManifest starts as ${manifest.name}, with courses ${manifest.courses}`);
manifest.entries = { b: { kind: "trap", explanation: "Step 2 divides by zero.", chapter: "Mistakes" }, a: { ref: "Lemma 1", title: "Doubling" } };
const folderFiles = [
  { id: "a", path: "Sheets/Week 1/Double.aether", source: "Let x : Real\nStep: x + x = 2 * x\n" },
  { id: "b", path: "Sheets/Week 1/Bad.aether", source: "Step: 1 = 2\n" },
];
const built = packs.buildPack(manifest, folderFiles, new Map([["a", "VALID"], ["b", "INVALID"]]));
check(built.problems.length === 0, `buildPack found problems in a good folder: ${built.problems}`);
check(built.pack.entries.find((e) => e.id === "doubling")?.ref === "Lemma 1", "buildPack ignores an entry's own reference and title");
check(built.pack.chapters.length === 2 && !("courses" in built.pack), "buildPack mis-groups chapters or invents a course code");
const asProblems = (map, change = {}) => packs.buildPack({ ...manifest, ...change }, folderFiles, new Map(map)).problems.join(" ");
check(/a trap must fail/.test(asProblems([["a", "VALID"], ["b", "VALID"]])), "buildPack accepts a trap that checks");
check(/does not parse/.test(asProblems([["a", "PARSE ERROR"], ["b", "INVALID"]])), "buildPack accepts a proof that does not parse");
check(/could not be checked/.test(asProblems([["a", "TIMEOUT"], ["b", "INVALID"]])), "buildPack records a verdict it never got");
check(/core\/ scope/.test(asProblems([["a", "VALID"], ["b", "INVALID"]], { name: "core/mine" })), "buildPack lets a pack claim the core/ scope");
console.log("packs checked");

// --- registry.js: the index, search, and checking a download -----------------
const registry = await moduleAt("js/registry.js");
const sha = "a".repeat(64);
const doc = {
  format: 1,
  engine: "0.1.0",
  contribute: "https://github.com/x/y",
  packs: [
    { name: "core/mth2008", version: "1.1.0", title: "Real Analysis", courses: ["MTH2008"], summary: "Analysis.", authors: ["A"], license: "CC-BY-SA-4.0", entries: 67, traps: 10, chapters: ["The Real Numbers"], search: "Example 2.18 limits", url: "packs/core/mth2008.pack.json", sha256: sha },
    { name: "someone/groups", version: "1.0.0", title: "Group basics", courses: [], summary: "Real numbers do not appear.", authors: ["B"], license: "CC-BY-SA-4.0", entries: 2, traps: 1, chapters: ["Groups"], search: "Lemma 1 Lagrange", url: "packs/someone/groups.pack.json", sha256: sha },
    { name: "Bad Name", version: "1.0.0", url: "x", sha256: sha },
    { name: "someone/nosha", version: "1.0.0", url: "x" },
  ],
};
const stubs = registry.indexStubs(doc);
check(stubs.length === 2, `indexStubs keeps malformed rows (${stubs.length})`);
check(registry.indexStubs({ ...doc, format: 2 }).length === 0, "indexStubs reads an index format it does not know");
check(stubs[0].remote.count === 67 && stubs[0].entries.length === 0 && stubs[0].remote.engine === "0.1.0", "a stub does not carry its index row");
check(registry.searchStubs(stubs, "MTH2008 real analysis")[0]?.name === "core/mth2008", "search does not find a pack by course and title");
check(registry.searchStubs(stubs, "real")[0]?.name === "core/mth2008", "a title match does not outrank a summary match");
check(registry.searchStubs(stubs, "lagrange")[0]?.name === "someone/groups", "search does not reach the theorems inside a pack");
check(registry.searchStubs(stubs, "lagrange analysis").length === 0, "search matches a pack missing one of the words");
check(registry.searchStubs(stubs, "").length === 0, "an empty search lists packs");
const bundledPack = { name: "core/mth2008", version: "1.0.0" };
check(registry.offered(stubs, [bundledPack]).map((s) => s.name).join() === "core/mth2008,someone/groups", "offered drops a newer registry copy of a bundled pack");
check(registry.offered(stubs, [{ name: "core/mth2008", version: "1.1.0" }]).map((s) => s.name).join() === "someone/groups", "offered lists a registry copy no newer than the bundled one");
const bytes = new TextEncoder().encode('{"x":1}');
const good = await registry.sha256Hex(bytes);
const { createHash } = await import("node:crypto");
check(good === createHash("sha256").update(bytes).digest("hex"), "sha256Hex disagrees with Node's sha256");
check((await registry.verifiedText(bytes, good)) === '{"x":1}', "verifiedText refuses bytes that match");
let refused = false;
try {
  await registry.verifiedText(bytes, sha);
} catch (error) {
  refused = /checksum/.test(error.message);
}
check(refused, "verifiedText accepts bytes the index does not vouch for");
console.log("registry checked");

// --- hint fixes and citations (js/fixes.js, js/packs.js) -----------------------
{
  const { fixChange } = await import(new URL("./static/js/fixes.js", import.meta.url));
  const { citationIndex, mayCite } = await import(new URL("./static/js/packs.js", import.meta.url));
  // A minimal CodeMirror Text: lines, line(n), sliceString.
  const textDoc = (text) => {
    const lines = text.split("\n");
    const starts = [];
    let at = 0;
    for (const l of lines) {
      starts.push(at);
      at += l.length + 1;
    }
    return {
      lines: lines.length,
      line: (n) => ({ from: starts[n - 1], to: starts[n - 1] + lines[n - 1].length, text: lines[n - 1] }),
      sliceString: (a, b) => text.slice(a, b),
    };
  };
  const apply = (text, change) => text.slice(0, change.from) + change.insert + text.slice(change.to);
  const proof = 'Theorem: "t"\nProof:\n    Let x : Real\n    Step: (x^2 - 1) / (x - 1) = x + 1\nQED';
  const inserted = fixChange(textDoc(proof), { line: 4, insert_before: "Assume x - 1 != 0" });
  check(inserted && apply(proof, inserted).includes("    Assume x - 1 != 0\n    Step:"), "an inserted line takes the indentation of the line it goes above");
  const swap = "Therefore x > 2";
  const swapped = fixChange(textDoc(swap), { line: 1, col_start: 13, col_end: 14, text: "≥", was: ">" });
  check(swapped && apply(swap, swapped) === "Therefore x ≥ 2", "a replacement edits exactly the columns it names");
  check(fixChange(textDoc("Therefore x < 2"), { line: 1, col_start: 13, col_end: 14, text: "≥", was: ">" }) === null, "a fix whose text has changed since the check is refused");
  check(fixChange(textDoc("x"), { line: 3, insert_before: "y" }) === null, "a fix past the end of the proof is refused");

  const pack = {
    name: "core/mth2008", title: "Real Analysis", courses: ["MTH2008"],
    entries: [
      { id: "t11", ref: "Theorem 1.1", title: "The triangle inequality, by the four cases", kind: "proof" },
      { id: "trap", ref: "Trap", title: "A trap", kind: "trap" },
      { id: "n", ref: "Notation", title: "In Unicode", kind: "proof" },
    ],
  };
  const index = citationIndex([pack], { "lemmas.aether": 'Lemma: "Bernoulli"\nProof:' });
  check(index["Theorem 1.1"]?.[0]?.[1] === "@core/mth2008/t11.aether", "a numbered reference is citable");
  check(Boolean(index["MTH2008 Theorem 1.1"]) && Boolean(index["The triangle inequality"]), "so are the course-qualified reference and the title's short form");
  check(!index["Trap"] && !index["Notation"] && !index["A trap"], "traps and unnumbered references are not");
  check(index["Bernoulli"]?.[0]?.[1] === "lemmas.aether", "a workspace theorem is citable by its name");
  check(mayCite("Step: x = y by Theorem 1.1") && mayCite("By h1, x > 0") && mayCite("Since x > 2, y > 1") && !mayCite("Let x : Real"), "mayCite spots a proof that cites");
  console.log("hint fixes and citations checked");
}

// --- typeset maths ------------------------------------------------------------
//
// Visual mode replaces each expression with its MathML, so two things must
// hold: a span is the mathematics and nothing else (never a keyword, a label,
// a justification), and what the editor cannot read stays as source.

{
  const { mathSpans, renderSpan, parseMath } = await moduleAt("visual-math.js");
  const spans = (line) => mathSpans(line).map((s) => `${s.kind}:${s.text}`);
  const SPANS = [
    ["    Given n : Int", ["decl:n : Int"]],
    ["    Assume h1: Even(n)", ["expr:Even(n)"]],
    ["    Obtain k : Int such that n = 2 * k from h1", ["decl:k : Int", "expr:n = 2 * k"]],
    ["    Step: = 4 * k^2 [by algebra]", ["chain:= 4 * k^2"]],
    ["    Therefore exists m : Int, n^2 = 4 * m [witness: k^2]", ["expr:exists m : Int, n^2 = 4 * m", "expr:k^2"]],
    ["    Since x > 2, x^2 > 4", ["expr:x > 2", "expr:x^2 > 4"]],
    ["    Since forall x, x >= 0, y >= 0", ["expr:forall x, x >= 0", "expr:y >= 0"]],
    ["    By Theorem 1.1, |a + b| <= |a| + |b|", ["expr:|a + b| <= |a| + |b|"]],
    ["    Let ε > 0 be given", ["expr:ε > 0"]],
    ["    Given ε : ℝ where ε > 0", ["decl:ε : ℝ", "expr:ε > 0"]],
    ["    Step: sqrt(x^2) = abs(x)  # a comment", ["expr:sqrt(x^2) = abs(x)"]],
    ["    Step: a⁻¹ * a = e using inverse law", ["expr:a⁻¹ * a = e"]],
    ["    Case x >= 0:", ["expr:x >= 0"]],
    ['Theorem: "Even square theorem"', []],
    ["Proof:", []],
    ['    import "lemmas"', []],
  ];
  for (const [line, want] of SPANS) {
    const got = spans(line);
    check(JSON.stringify(got) === JSON.stringify(want), `mathSpans(${JSON.stringify(line)}) is ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
    // Offsets point at the text they claim to.
    for (const s of mathSpans(line)) check(line.slice(s.from, s.to) === s.text, `a span of ${JSON.stringify(line)} does not cover its own text`);
  }

  const markup = (text, kind = "expr") => renderSpan({ text, kind }) ?? "";
  check(markup("(x^2 - 4) / (x - 2) = x + 2").includes("<mfrac>") && !markup("(x^2 - 4) / (x - 2)").includes(">(<"), "a fraction stacks and drops the brackets that only grouped its terms");
  check(markup("sqrt(x) >= 0").includes("<msqrt>") && markup("√x >= 0").includes("<msqrt>"), "sqrt(…) and √ both set as a radical");
  check(markup("2 * k = n").includes("⁢") && markup("2 * 3 = 6").includes(">·<"), "2 * k prints as 2k, but 2 * 3 keeps its dot");
  check(markup("x <= y").includes(">≤<") && markup("x != y").includes(">≠<") && markup("x in S").includes(">∈<"), "relations print as their signs");
  check(markup("forall x : Real, x^2 >= 0").includes(">ℝ<") && markup("forall x in Real, x >= 0").includes(">ℝ<"), "a quantifier's type prints as its blackboard letter");
  check(markup("x : Real", "decl").includes(">∈<") && markup("f : Real -> Real", "decl").includes(">→<"), "a declaration reads x ∈ ℝ, and a function type f : ℝ → ℝ");
  check(markup("i = k (mod n)").includes(">mod<"), "k (mod n) is a congruence, not a call of k");
  check(markup("(1/2)^k = 1").includes("vm-tall") && !markup("(x + 1)^2 = 1").includes("vm-tall"), "only brackets round something tall are set to grow");
  check(markup("\\sum_{k=0}^{\\infty} r^k = 1") && markup("\\int_{1}^{2} 3*t^2 dt = 7") && markup("\\lim_{x \\to 0^+} 1/x = \\infty"), "the notes' sums, integrals and limits typeset");
  check(markup("x_1 + epsilon").includes("<msub>") && markup("x_1 + epsilon").includes(">ϵ<"), "x_1 is a subscript and a spelled-out Greek name its letter");
  check(markup("a < b").includes("&lt;"), "MathML text is escaped");
  // What it cannot read, it leaves alone: half-typed and unknown input is source.
  for (const text of ["x^2 = (", "x = $y$", "x y", "2 k = n", "f(x,", ""]) check(parseMath(text) === null, `parseMath(${JSON.stringify(text)}) should leave it as source`);
  check(renderSpan({ text: "x", kind: "expr" }) === null && renderSpan({ text: "42", kind: "expr" }) === null, "a lone name or number is not worth a widget");

  // Every proof the packs ship: nothing throws, and nearly every span typesets.
  let total = 0;
  let typeset = 0;
  for (const name of readdirSync(new URL("../courses/", import.meta.url)).filter((f) => f.endsWith(".json") && !f.includes("schema"))) {
    const course = JSON.parse(readFileSync(new URL(`../courses/${name}`, import.meta.url), "utf8"));
    for (const entry of course.entries) {
      for (const line of (entry.source ?? "").split("\n")) {
        for (const s of mathSpans(line)) {
          total++;
          if (renderSpan(s)) typeset++;
        }
      }
    }
  }
  check(total > 400 && typeset / total > 0.97, `visual mode typesets ${typeset} of ${total} spans in the course packs`);
  console.log(`typeset maths checked (${typeset}/${total} pack spans)`);
}

// --- Show in Lean (js/lean.js) --------------------------------------------------
{
  const { leanTokens, leanTokenLines, sourceTokens, leanEditorUrl, leanFilename, untranslatedNote } = await import(new URL("./static/js/lean.js", import.meta.url));
  const tokens = leanTokens("  have s6 : n ^ 2 = 4 := by sorry  -- SymPy: try ring");
  check(tokens.map((t) => t.text).join("") === "  have s6 : n ^ 2 = 4 := by sorry  -- SymPy: try ring", "Lean tokens rebuild the line exactly");
  check(tokens.find((t) => t.text === "have")?.kind === "kw" && tokens.find((t) => t.text === "sorry")?.kind === "sorry", "Lean's keywords and sorry are told apart");
  check(tokens[tokens.length - 1].kind === "comment" && tokens[tokens.length - 1].text.startsWith("-- SymPy"), "a -- comment runs to the end of the line");
  check(!leanTokens("  intro ε hε").some((t) => t.kind === "kw" && t.text !== "intro"), "names are not keywords");
  const block = leanTokenLines(["/-! Written by Lemmata.", "    the comment says -/", "namespace Lemmata"]);
  check(block[0].every((t) => t.kind === "comment") && block[1].every((t) => t.kind === "comment"), "a block comment spans its lines, keywords and all");
  check(block[2][0].kind === "kw", "and code resumes after it");
  const src = sourceTokens("    Obtain k : Int such that n = 2 * k from h1");
  check(src[1]?.kind === "kw" && src[1].text === "Obtain" && src.map((t) => t.text).join("") === "    Obtain k : Int such that n = 2 * k from h1", "a source line's keyword is marked and the line kept whole");
  check(leanEditorUrl("theorem t : 1 = 1 := rfl").startsWith("https://live.lean-lang.org/#code=theorem%20t"), "the web editor link carries the code");
  check(leanFilename("even-square.aether") === "even_square.lean" && leanFilename("") === "Proof.lean", "the download is named after the proof");
  check(untranslatedNote([{ line: 2, what: "∞, which is not a real number" }]) === "Not translated, so left as sorry: ∞, which is not a real number (line 2).", "what was not translated is named with its line");
  check(untranslatedNote([]) === "", "and nothing is said when everything translated");
  console.log("Show in Lean checked");
}

// --- sync (js/sync.js, js/remote-memory.js) ------------------------------------
//
// Two devices, one account, one remote.  Each device is a memory store with
// the local adapter's shape; the clock is shared and steps on every read, so
// "newer" is unambiguous.

{
  const { createSync, freeCopyPath } = await moduleAt("js/sync.js");
  const { createMemoryRemote } = await moduleAt("js/remote-memory.js");
  let now = 1000;
  const clock = () => ++now;

  function device(remote, owner = "u1", { mergeLocal = true } = {}) {
    const stores = new Map();
    let state = null;
    const table = (s) => {
      if (!stores.has(s)) stores.set(s, new Map());
      return stores.get(s);
    };
    const applied = [];
    const local = {
      async all(s) {
        return [...table(s).entries()].map(([key, value]) => ({ key, value: structuredClone(value) }));
      },
      async read(s, key) {
        const v = table(s).get(key);
        return v === undefined ? undefined : structuredClone(v);
      },
      async write(s, key, value) {
        table(s).set(key, structuredClone(value));
      },
      async remove(s, key) {
        table(s).delete(key);
      },
      async loadState() {
        return state && structuredClone(state);
      },
      async saveState(s) {
        state = structuredClone(s);
      },
    };
    const sync = createSync({ local, remote, owner, mergeLocal, clock, onApplied: (c) => applied.push(...c) });
    return {
      sync,
      applied,
      table,
      // A local edit: write, then tell sync (as db.js's change bus will).
      async put(s, key, value) {
        table(s).set(key, structuredClone(value));
        await sync.record(s, key, clock());
      },
      async del(s, key) {
        table(s).delete(key);
        await sync.record(s, key, clock());
      },
    };
  }

  const file = (id, path, source) => ({ id, path, source, strict: false, working: false, level: "course", created: 1, updated: clock() });

  // 1. A proof made on one device appears on the other.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    const b = device(remote);
    await a.put("files", "f1", file("f1", "Week 1.aether", "Let x : Real\n"));
    await a.sync.syncNow();
    await b.sync.syncNow();
    check(b.table("files").get("f1")?.source === "Let x : Real\n", "sync: a proof made on one device reaches the other");
    check(b.applied.some((c) => c.store === "files" && c.key === "f1"), "sync: and the views are told what changed");
  }

  // 2. Both edit offline; the newer edit wins everywhere, and the older one
  //    is kept as a snapshot, not lost.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    const b = device(remote);
    await a.put("files", "f1", file("f1", "P.aether", "v0"));
    await a.sync.syncNow();
    await b.sync.syncNow();
    await b.put("files", "f1", { ...b.table("files").get("f1"), source: "older edit on B", updated: clock() });
    await a.put("files", "f1", { ...a.table("files").get("f1"), source: "newer edit on A", updated: clock() });
    await a.sync.syncNow();
    await b.sync.syncNow();
    await a.sync.syncNow();
    check(b.table("files").get("f1").source === "newer edit on A", "sync: the newer of two offline edits wins on both devices");
    check(a.table("files").get("f1").source === "newer edit on A", "sync: and stays on the device that made it");
    const kept = [...b.table("snapshots").values()].find((s) => s.fileId === "f1");
    check(kept?.source === "older edit on B" && kept.name === "Kept from this device", "sync: the losing edit is kept as a snapshot");
    check([...a.table("snapshots").values()].some((s) => s.source === "older edit on B"), "sync: and that snapshot reaches the other device too");
    check((await b.sync.pending()) === 0 && (await a.sync.pending()) === 0, "sync: nothing is left waiting once both have synced");
  }

  // 3. A deletion reaches every device.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    const b = device(remote);
    await a.put("files", "f1", file("f1", "Gone.aether", "x"));
    await a.sync.syncNow();
    await b.sync.syncNow();
    await b.del("files", "f1");
    await b.sync.syncNow();
    await a.sync.syncNow();
    check(!a.table("files").has("f1"), "sync: a proof deleted on one device is deleted on the other");
  }

  // 4. Two workspaces meeting for the first time: both kept, one moved aside.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    await a.table("files").set("fa", file("fa", "Untitled.aether", "from A"));
    await a.sync.syncNow();
    const b = device(remote);
    b.table("files").set("fb", file("fb", "Untitled.aether", "from B"));
    await b.sync.syncNow();
    await a.sync.syncNow();
    const paths = (d) => [...d.table("files").values()].map((f) => f.path).sort();
    check(JSON.stringify(paths(b)) === JSON.stringify(["Untitled (2).aether", "Untitled.aether"]), `sync: a first merge keeps both proofs at one path (${paths(b)})`);
    check(JSON.stringify(paths(a)) === JSON.stringify(paths(b)), `sync: and both devices agree on the paths (${paths(a)})`);
  }

  // 5. Settings and history sync; this device's tabs do not.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    const b = device(remote);
    await a.put("prefs", "aether-theme", "dark");
    await a.put("meta", "timeline", [{ verdict: "VALID", ts: 1 }]);
    await a.put("meta", "tabs", ["f1"]);
    await a.sync.syncNow();
    await b.sync.syncNow();
    check(b.table("prefs").get("aether-theme") === "dark", "sync: settings follow the account");
    check(b.table("meta").get("timeline")?.length === 1, "sync: the check history follows too");
    check(!b.table("meta").has("tabs"), "sync: but which tabs are open stays with the device");
  }

  // 6. Starting from the account's work leaves this device's proofs out.
  {
    const remote = createMemoryRemote();
    const a = device(remote);
    await a.put("files", "f1", file("f1", "Mine.aether", "x"));
    await a.sync.syncNow();
    const b = device(remote, "u1", { mergeLocal: false });
    b.table("files").set("local", file("local", "Scratch.aether", "y"));
    await b.sync.syncNow();
    check(!remote.rows.has("files:local") && b.table("files").has("f1"), "sync: starting from the account's work does not upload this device's proofs");
  }

  check(freeCopyPath("a/Week 1.aether", new Set(["a/Week 1 (2).aether"])) === "a/Week 1 (3).aether", "sync: a moved-aside path finds the next free number");
  console.log("sync checked");
}

console.log();
if (failures.length) {
  console.log(`${failures.length} check(s) failed:`);
  for (const failure of failures) console.log(`  - ${failure}`);
  process.exit(1);
}
console.log("frontend checks passed");
