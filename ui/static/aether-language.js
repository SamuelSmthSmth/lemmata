// Aether syntax mode for CodeMirror 6.
//
// Deliberately free of DOM imports so it can be unit-tested in Node -- see
// ui/verify_frontend.mjs.

import { HighlightStyle, StreamLanguage } from "./vendor/esm/@codemirror/language@6.mjs";
import { tags } from "./vendor/esm/@lezer/highlight@1.mjs";

// Keyword sets transcribed from src/aether/parser/grammar.lark.
const STRUCTURE_KW = new Set([
  "theorem", "lemma", "proposition", "claim", "proof", "qed", "case", "define", "definition",
]);
const INTRO_KW = new Set([
  "let", "given", "fix", "take",
  "assume", "suppose", "hypothesize",
  "obtain", "choose", "pick", "step",
]);
const FLOW_KW = new Set([
  "therefore", "thus", "hence", "so", "then", "conclude", "exists", "forall",
]);
const JOIN_KW = new Set(["such", "that", "where", "satisfying", "from", "with", "using", "by", "as"]);
const LOGIC_KW = new Set([
  "and", "or", "not", "iff", "in", "subset", "subseteq", "union", "intersect", "setminus", "mod",
]);
const MATH_FN_KW = new Set([
  "diff", "det", "tr", "norm", "dot", "transpose", "conj", "re", "im", "abs", "sqrt", "sum",
  "cauchyriemann", "orthogonal", "integrate", "lim", "inv",
]);

// Token names are custom and mapped explicitly.  StreamLanguage's built-in
// table only knows CM5-style names and warns ("Unknown highlighting tag") for
// anything else, which would silently drop styling.
export const AETHER_TOKENS = {
  structure: tags.definitionKeyword,
  intro: tags.keyword,
  flow: tags.controlKeyword,
  join: tags.modifier,
  logicKw: tags.operatorKeyword,
  // `tags.function` is a *modifier*: on its own it is not a tag.  Math
  // functions are call-shaped, so this is the tag that means "a name you
  // apply", which is exactly what sqrt/lim/det are.
  mathFn: tags.function(tags.variableName),
  // LaTeX-ish escapes (\mathbb{N}, \epsilon) get the macro tag so a vivid
  // scheme can lift them out of the type colour.
  macro: tags.macroName,
  operator: tags.operator,
  variableName: tags.variableName,
  typeName: tags.typeName,
  number: tags.number,
  string: tags.string,
  comment: tags.comment,
};

export function aetherToken(stream) {
  if (stream.eatSpace()) return null;

  // `#` and `--` are ignored by the grammar, so treat them as comments.
  if (stream.match("#") || stream.match("--")) {
    stream.skipToEnd();
    return "comment";
  }

  // Multi-word keywords matched before bare identifiers
  if (stream.match(/base\s+case/i)) return "structure";
  if (stream.match(/inductive\s+step|induction\s+step/i)) return "structure";
  if (stream.match(/such\s+that/i)) return "join";
  if (stream.match(/not\s+in/i)) return "logicKw";

  if (stream.match(/"[^"]*"/)) return "string";
  if (stream.match(/\\[a-zA-Z]+/)) return "macro"; // \mathbb{N}, \epsilon, ...
  if (stream.match(/\d+(\.\d+)?/)) return "number";

  // Use the match result rather than stream.current(): `current()` is not
  // scoped to this token, so keyword lookups would silently miss.
  const word = stream.match(/[a-zA-Z_][a-zA-Z0-9_]*/);
  if (word) {
    const text = word[0];
    const lower = text.toLowerCase();
    if (STRUCTURE_KW.has(lower)) return "structure";
    if (MATH_FN_KW.has(lower)) return "mathFn";
    if (INTRO_KW.has(lower)) return "intro";
    if (FLOW_KW.has(lower)) return "flow";
    if (JOIN_KW.has(lower)) return "join";
    if (LOGIC_KW.has(lower)) return "logicKw";
    // Capitalised identifiers are types and prelude predicates: Int, Real,
    // Even, MultipleOf.  Keywords above are matched first, so Theorem/QED keep
    // their structure colouring.
    return /^[A-Z]/.test(text) ? "typeName" : "variableName";
  }

  if (stream.match(/<=>|<=|>=|!=|\/=|=>|->/)) return "operator";
  if (stream.match(/[+\-*/^=<>:,()[\]{}|]/)) return "operator";

  stream.next();
  return null;
}

export const aetherLanguage = StreamLanguage.define({
  name: "aether",
  token: aetherToken,
  tokenTable: AETHER_TOKENS,
});

/**
 * Every key `makeHighlightStyle` reads.
 *
 * Exported so the three files that have to agree about it -- this one, the
 * CSS that supplies the values, and js/editor.js which resolves them out of
 * the custom properties -- can be checked against each other.  They live in
 * different files and a typo in any of them fails silently, as a token that is
 * simply not coloured.
 */
export const PALETTE_KEYS = [
  "structure",
  "intro",
  "flow",
  "join",
  "logic",
  "mathFn",
  "macro",
  "type",
  "ink",
  "number",
  "operator",
  "string",
  "comment",
];

/** The custom property a palette key is stored under: mathFn -> --cm-token-math-fn. */
export function tokenVariable(key) {
  return `--cm-token-${key.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)}`;
}

/**
 * Build the syntax colours from a palette of already-resolved CSS values.
 *
 * This module stays DOM-free so it can be unit-tested in Node, which means it
 * cannot read custom properties itself -- editor.js resolves the tokens and
 * passes them in.  The upshot is one palette for the whole app rather than a
 * syntax theme maintained separately from it.
 *
 * Two schemes are expressed here, chosen entirely by the palette:
 *
 *   "mono"  (default) Collapses most keys onto the accent: the
 *                     controlled-natural-language keywords are the skeleton of
 *                     a proof, so they carry the colour; types are inked and
 *                     separated by weight; everything else recedes.  A proof
 *                     reads as text with a structure rather than a rainbow.
 *   "vivid" Gives every category its own hue, the way a general-purpose
 *                     language colours calls, strings and keywords apart.
 *
 * Nothing branches on the scheme: the palette supplies either one accent for
 * most keys or a different colour for each, and the list below is the same.
 */
export function makeHighlightStyle(p) {
  return HighlightStyle.define([
    { tag: tags.definitionKeyword, color: p.structure, fontWeight: "600" },
    { tag: tags.controlKeyword, color: p.flow, fontWeight: "600" },
    { tag: tags.keyword, color: p.intro },
    { tag: tags.operatorKeyword, color: p.logic },
    { tag: tags.function(tags.variableName), color: p.mathFn },
    { tag: tags.macroName, color: p.macro },
    { tag: tags.typeName, color: p.type, fontWeight: "600" },
    { tag: tags.variableName, color: p.ink },
    { tag: tags.number, color: p.number },
    { tag: tags.operator, color: p.operator },
    { tag: tags.modifier, color: p.join },
    { tag: tags.string, color: p.string },
    // No italics: the vendored subsets ship no italic file, and a synthesised
    // slant on a monospace face reads as a rendering fault rather than emphasis.
    { tag: tags.comment, color: p.comment },
  ]);
}
