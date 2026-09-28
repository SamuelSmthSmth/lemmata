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
  if (stream.match(/\\[a-zA-Z]+/)) return "typeName"; // \mathbb{N}, \epsilon, ...
  if (stream.match(/\d+(\.\d+)?/)) return "number";

  // Use the match result rather than stream.current(): `current()` is not
  // scoped to this token, so keyword lookups would silently miss.
  const word = stream.match(/[a-zA-Z_][a-zA-Z0-9_]*/);
  if (word) {
    const text = word[0];
    const lower = text.toLowerCase();
    if (STRUCTURE_KW.has(lower)) return "structure";
    if (INTRO_KW.has(lower)) return "intro";
    if (FLOW_KW.has(lower)) return "flow";
    if (JOIN_KW.has(lower)) return "join";
    if (LOGIC_KW.has(lower)) return "logicKw";
    if (MATH_FN_KW.has(lower)) return "intro";
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

// One style per theme, selected alongside the matching editor theme so the
// syntax colours always sit on the right background.
const DARK_TOKENS = [
  { tag: tags.definitionKeyword, color: "#c792ea", fontWeight: "600" },
  { tag: tags.keyword, color: "#82aaff" },
  { tag: tags.controlKeyword, color: "#f78c6c", fontWeight: "600" },
  { tag: tags.operatorKeyword, color: "#89ddff" },
  { tag: tags.modifier, color: "#7f8896" },
  { tag: tags.operator, color: "#89ddff" },
  { tag: tags.typeName, color: "#ffcb6b" },
  { tag: tags.number, color: "#f78c6c" },
  { tag: tags.string, color: "#c3e88d" },
  { tag: tags.variableName, color: "#e7e9ee" },
  { tag: tags.comment, color: "#5f6b7c", fontStyle: "italic" },
];

const LIGHT_TOKENS = [
  { tag: tags.definitionKeyword, color: "#8250df", fontWeight: "600" },
  { tag: tags.keyword, color: "#0550ae" },
  { tag: tags.controlKeyword, color: "#953800", fontWeight: "600" },
  { tag: tags.operatorKeyword, color: "#0550ae" },
  { tag: tags.modifier, color: "#6e7781" },
  { tag: tags.operator, color: "#0550ae" },
  { tag: tags.typeName, color: "#953800" },
  { tag: tags.number, color: "#0550ae" },
  { tag: tags.string, color: "#0a3069" },
  { tag: tags.variableName, color: "#1f2328" },
  { tag: tags.comment, color: "#6e7781", fontStyle: "italic" },
];

export const aetherHighlightStyles = {
  dark: HighlightStyle.define(DARK_TOKENS),
  light: HighlightStyle.define(LIGHT_TOKENS),
};
