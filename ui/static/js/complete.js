// Completion, proof templates and the symbol palette.
//
// Three sources feed one completion list:
//   - the language: statement keywords, types, prelude predicates, functions
//     (each with its signature), structures and constants;
//   - templates: whole proof shapes as snippets with tab stops;
//   - the proof itself: the variables the last check saw in scope at the
//     caret's line, so names you declared complete with their types.
//
// Nothing here talks to the server.  `setScopeSource` hands in a function that
// answers "what was in scope at line n" from the report already on screen.

import {
  autocompletion,
  completionKeymap,
  snippet,
  snippetCompletion,
} from "../vendor/esm/@codemirror/autocomplete@6.mjs";

// --- Templates ---------------------------------------------------------------
//
// `${name}` is a tab stop; `${}` an empty one.  Indentation is four spaces,
// the grammar's unit.  Each is a shape from the notes, not an invented one.

export const TEMPLATES = [
  {
    id: "theorem",
    label: "Theorem with a claim",
    detail: "Theorem / Claim / Proof / QED",
    body: 'Theorem: "${Name}"\nClaim: ${forall x : Real, x = x}\nProof:\n    Given ${x : Real}\n    ${}\nQED\n',
  },
  {
    id: "epsilon-delta",
    label: "ε–δ limit (Definition 2.6)",
    detail: "for every ε > 0 there is a δ > 0",
    body:
      'Theorem: "${Limit of f at x0}"\nProof:\n    Let ${x0} : Real\n    Given \\epsilon : Real where \\epsilon > 0\n' +
      "    Let \\delta = ${\\epsilon / 3}\n    Step: \\delta > 0\n    Subproof:\n        Given x : Real\n" +
      "        Assume |x - x0| < \\delta\n        Step: |${f(x) - L}| = ${}\n        Step: < \\epsilon\n" +
      "    Therefore exists \\delta : Real, \\delta > 0 and (forall x : Real, |x - x0| < \\delta => |${f(x) - L}| < \\epsilon) [witness: ${\\epsilon / 3}]\nQED\n",
  },
  {
    id: "induction",
    label: "Proof by induction",
    detail: "Base case / Inductive step",
    body:
      'Theorem: "${Name}"\nClaim: forall n : Nat, ${P(n)}\nProof:\n    Base case n = 0:\n        Step: ${}\n' +
      "    Inductive step:\n        Given k : Nat\n        Assume ih: ${P(k)}\n        Step: ${}\n" +
      "    Therefore forall n : Nat, ${P(n)}\nQED\n",
  },
  {
    id: "cases",
    label: "Proof by cases",
    detail: "exhaustive Case blocks",
    body: "Given ${x} : Real\nCase ${x >= 0}:\n    Step: ${}\nCase ${x < 0}:\n    Step: ${}\nTherefore ${}\n",
  },
  {
    id: "contradiction",
    label: "Proof by contradiction",
    detail: "assume the negation, reach Contradiction",
    body: "Subproof:\n    Assume ${not P}\n    Step: ${}\n    Therefore Contradiction\nTherefore ${P}\n",
  },
  {
    id: "group",
    label: "Group-theory proof",
    detail: "Assume Group(G, op, e, inv); Given a : G",
    body: 'Theorem: "${Name}"\nProof:\n    Assume Group(G, op, e, inv)\n    Given ${a, b} : G\n    Step: ${(a * b)^-1 = b^-1 * a^-1}\nQED\n',
  },
  {
    id: "obtain",
    label: "Unpack an existential",
    detail: "Assume … ; Obtain k such that …",
    body: "Given ${n} : Int\nAssume ${h}: ${Even(n)}\nObtain ${k} : Int such that ${n = 2 * k} from ${h}\n${}",
  },
];

// --- The language ------------------------------------------------------------

const KEYWORDS = [
  ["Theorem", "a named theorem; follow with a string"],
  ["Lemma", "a named lemma"],
  ["Claim", "the goal QED checks"],
  ["Proof", "opens the indented proof"],
  ["QED", "closes the proof and checks the claim"],
  ["Let", "declare variables: Let x, y : Real"],
  ["Given", "declare variables: Given n : Int"],
  ["Fix", "declare a variable with a condition"],
  ["Assume", "a hypothesis: Assume h1: x > 0"],
  ["Suppose", "a hypothesis"],
  ["Obtain", "unpack an existential: Obtain k : Int such that … from h1"],
  ["Step", "an algebraic or inequality step; leave out the left side to chain"],
  ["Therefore", "deduce a new fact"],
  ["Hence", "deduce a new fact"],
  ["Thus", "deduce a new fact"],
  ["Case", "one case of an exhaustive split"],
  ["Subproof", "a nested scope (implication, ∀-introduction)"],
  ["Base case", "induction: the base"],
  ["Inductive step", "induction: P(k) ⇒ P(k + 1)"],
  ["Define", "a reusable predicate: Define P(x) <=> …"],
  ["import", 'another file\'s theorems: import "lemmas.aether"'],
  ["forall", "∀"],
  ["exists", "∃"],
  ["such that", ""],
  ["where", ""],
  ["from", ""],
];

const TYPES = ["Nat", "Int", "Rat", "Real", "Complex", "Bool", "Set"];

const PREDICATES = [
  ["Even", "Even(x)", "∃ k ∈ ℤ, x = 2k"],
  ["Odd", "Odd(x)", "∃ k ∈ ℤ, x = 2k + 1"],
  ["MultipleOf", "MultipleOf(a, b)", "∃ k ∈ ℤ, a = b·k"],
  ["Divides", "Divides(b, a)", "∃ k ∈ ℤ, a = b·k"],
  ["Positive", "Positive(x)", "x > 0"],
  ["NonNegative", "NonNegative(x)", "x ≥ 0"],
  ["Congruent", "Congruent(a, b, m)", "a ≡ b (mod m)"],
  ["Prime", "Prime(p)", "p > 1 with no divisor strictly between 1 and p"],
  ["Coprime", "Coprime(a, b)", "every common divisor is ±1"],
  ["Rational", "Rational(x)", "x = p/q in lowest terms, q > 0"],
  ["Irrational", "Irrational(x)", "not Rational(x)"],
];

const STRUCTURES = [
  ["Group", "Group(${G}, ${op}, ${e}, ${inv})", "a group; then Given a : G"],
  ["AbelianGroup", "AbelianGroup(${G}, ${op}, ${e}, ${inv})", "a commutative group"],
  ["Subgroup", "Subgroup(${H}, ${G}, ${op}, ${e}, ${inv})", "H ≤ G"],
  ["NormalSubgroup", "NormalSubgroup(${N}, ${G}, ${op}, ${e}, ${inv})", "N ⊴ G"],
  ["Ring", "Ring(${R}, ${add}, ${mul}, ${zero}, ${one}, ${neg})", "a ring"],
  ["Field", "Field(${F}, ${add}, ${mul}, ${zero}, ${one}, ${neg}, ${inv})", "a field"],
];

const FUNCTIONS = [
  ["sqrt", "sqrt(x)", "√x; requires x ≥ 0"],
  ["abs", "abs(x)", "|x|"],
  ["min", "min(a, b)", ""],
  ["max", "max(a, b)", ""],
  ["exp", "exp(x)", "eˣ"],
  ["ln", "ln(x)", "natural log"],
  ["log", "log(x)", "natural log; log(x, b) for base b"],
  ["sin", "sin(x)", ""],
  ["cos", "cos(x)", ""],
  ["tan", "tan(x)", ""],
  ["sinh", "sinh(x)", ""],
  ["cosh", "cosh(x)", ""],
  ["atan", "atan(x)", "arctan"],
  ["floor", "floor(x)", "⌊x⌋"],
  ["ceil", "ceil(x)", "⌈x⌉"],
  ["factorial", "factorial(n)", "n!"],
  ["binomial", "binomial(n, k)", "n choose k"],
  ["gcd", "gcd(a, b)", "numbers only"],
  ["lcm", "lcm(a, b)", "numbers only"],
  ["diff", "diff(${f}, ${x})", "derivative; diff(f, x, 2) for the second"],
  ["integrate", "integrate(${f}, ${x}, ${a}, ${b})", "definite integral; two arguments for indefinite"],
  ["lim", "lim(${f}, ${x}, ${a})", 'limit; add "+" or "-" for one side'],
  ["sum", "sum(${k}, ${1}, ${n}, ${body})", "Σ from 1 to n"],
  ["det", "det(A)", ""],
  ["transpose", "transpose(A)", ""],
];

const CONSTANTS = [
  ["oo", "∞ (also \\infty)"],
  ["pi", "π"],
  ["e", "Euler's number (unless a structure binds e)"],
];

// --- The symbol palette ----------------------------------------------------------
//
// What a student copies off the page of notes.  Each inserts the symbol the
// grammar accepts directly; `ascii` is shown in the tooltip as the keyboard way.

export const SYMBOLS = [
  { symbol: "∀", ascii: "forall", label: "for all" },
  { symbol: "∃", ascii: "exists", label: "there exists" },
  { symbol: "∈", ascii: "in", label: "element of" },
  { symbol: "∉", ascii: "notin", label: "not an element of" },
  { symbol: "⊆", ascii: "subseteq", label: "subset" },
  { symbol: "≤", ascii: "<=", label: "less or equal" },
  { symbol: "≥", ascii: ">=", label: "greater or equal" },
  { symbol: "≠", ascii: "!=", label: "not equal" },
  { symbol: "⇒", ascii: "=>", label: "implies" },
  { symbol: "⇔", ascii: "<=>", label: "if and only if" },
  { symbol: "ε", ascii: "\\epsilon", label: "epsilon" },
  { symbol: "δ", ascii: "\\delta", label: "delta" },
  { symbol: "∞", ascii: "oo", label: "infinity" },
  { symbol: "√", ascii: "sqrt(x)", label: "square root" },
  { symbol: "⁻¹", ascii: "^-1", label: "inverse" },
  { symbol: "ℝ", ascii: "Real", label: "the reals" },
  { symbol: "ℤ", ascii: "Int", label: "the integers" },
  { symbol: "ℕ", ascii: "Nat", label: "the naturals" },
];

// --- Completion sources ------------------------------------------------------------

let scopeAt = () => ({});

let citations = () => ({});

/** Hand in `() -> {name: [[label, key], …]}`: the results a step may cite (packs.citationIndex). */
export function setCitationSource(fn) {
  citations = fn;
}

/**
 * After `by ` / `using ` (or a `By …,` sentence), offer what may be cited:
 * the installed packs' results and the workspace's theorems.
 */
function citationCompletions(context, lineText, lineFrom) {
  const match = /(?:\b(?:by|using)\s+|^\s*by\s+)([^,\[\]]*)$/i.exec(lineText);
  if (!match) return null;
  const typed = match[1];
  const names = Object.entries(citations() ?? {});
  if (!names.length) return null;
  return {
    from: lineFrom + lineText.length - typed.length,
    options: names.map(([name, targets]) => ({
      label: name,
      type: "text",
      detail: targets.length > 1 ? `${targets.length} results` : "",
      info: targets.map(([label]) => label).join("\n"),
      boost: /\d/.test(name) ? 1 : 0,
    })),
    validFor: /^[^,\[\]]*$/,
  };
}

/** Hand in `(lineNumber) -> {name: type}` from the last check. */
export function setScopeSource(fn) {
  scopeAt = fn;
}

function word(context) {
  return context.matchBefore(/[\\A-Za-z_][\w]*/);
}

const LANGUAGE_OPTIONS = [
  ...KEYWORDS.map(([label, info]) => ({ label, type: "keyword", info: info || undefined, boost: 2 })),
  ...TYPES.map((label) => ({ label, type: "type", detail: "type" })),
  ...PREDICATES.map(([label, sig, info]) => ({ label, type: "function", detail: sig, info })),
  ...STRUCTURES.map(([label, body, info]) =>
    snippetCompletion(body, { label, type: "class", detail: "structure", info }),
  ),
  ...FUNCTIONS.map(([label, sig, info]) =>
    sig.includes("${")
      ? snippetCompletion(sig, { label, type: "function", detail: sig.replace(/\$\{([^}]*)\}/g, "$1"), info: info || undefined })
      : { label, type: "function", detail: sig, info: info || undefined, apply: `${label}(` },
  ),
  ...CONSTANTS.map(([label, info]) => ({ label, type: "constant", info })),
];

const TEMPLATE_OPTIONS = TEMPLATES.map((t) =>
  snippetCompletion(t.body, { label: t.label, type: "text", detail: "template", info: t.detail, boost: -1 }),
);

function aetherCompletions(context) {
  const before = word(context);
  const lineStart = context.state.doc.lineAt(context.pos);
  const citingHere = /(?:\b(?:by|using)\s+|^\s*by\s+)[^,\[\]]*$/i.test(lineStart.text.slice(0, context.pos - lineStart.from));
  if (!before && !context.explicit && !citingHere) return null;
  const line = context.state.doc.lineAt(context.pos);
  const lineText = line.text.slice(0, context.pos - line.from);
  // Inside a string (a theorem name) there is nothing to complete.
  if ((lineText.match(/"/g) ?? []).length % 2 === 1) return null;
  const cite = citationCompletions(context, lineText, line.from);
  if (cite) return cite;

  const scope = scopeAt(line.number) ?? {};
  const variables = Object.entries(scope).map(([name, type]) => ({
    label: name,
    type: "variable",
    detail: type,
    boost: 3,
  }));
  // Templates only where a statement starts, so they never interrupt an expression.
  const atStatementStart = /^\s*[\w ]*$/.test(lineText);
  const options = [...variables, ...LANGUAGE_OPTIONS, ...(atStatementStart ? TEMPLATE_OPTIONS : [])];
  return {
    from: before ? before.from : context.pos,
    options,
    validFor: /^[\\\w]*$/,
  };
}

/** The extensions to add to the editor once. */
export function completionExtensions() {
  return [
    autocompletion({
      override: [aetherCompletions],
      activateOnTyping: true,
      icons: false,
      closeOnBlur: true,
    }),
  ];
}

export { completionKeymap };

/** Insert template *id* at the caret (used by the "New from template" menu). */
export function insertTemplate(view, id) {
  const template = TEMPLATES.find((t) => t.id === id);
  if (!template) return;
  const { from, to } = view.state.selection.main;
  snippet(template.body)(view, null, from, to);
  view.focus();
}

/** Insert a palette symbol at the caret, spaced the way the grammar reads it. */
export function insertSymbol(view, symbol) {
  const { from, to } = view.state.selection.main;
  const before = view.state.doc.sliceString(Math.max(0, from - 1), from);
  const binary = !["⁻¹", "√", "ε", "δ", "∞", "ℝ", "ℤ", "ℕ"].includes(symbol);
  const text = binary && before && !/\s/.test(before) ? ` ${symbol} ` : binary ? `${symbol} ` : symbol;
  view.dispatch({ changes: { from, to, insert: text }, selection: { anchor: from + text.length }, scrollIntoView: true });
  view.focus();
}
