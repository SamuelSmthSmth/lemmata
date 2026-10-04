// Typeset maths for the editor's visual mode.
//
// Deliberately free of DOM imports, like aether-language.js, so it can be
// unit-tested in Node -- see ui/verify_frontend.mjs.  Two jobs:
//
//   mathSpans(line)  where the mathematics sits in one line of a proof: the
//                    statement's expressions, never its keywords, labels or
//                    justifications ("Assume h1: |x| < 1" -> "|x| < 1").
//   renderSpan(span) the span as MathML, or null when it does not parse.
//
// The parser mirrors the expression half of src/aether/parser/grammar.lark,
// and the notation follows aether.core.latex_export, so what the editor shows
// is what the LaTeX export prints.  It only ever decides how to *show* a span;
// anything it does not understand stays as the source the student typed.

// ---------------------------------------------------------------------------
// Tokens
// ---------------------------------------------------------------------------

const TYPE_NAMES = {
  nat: "ℕ", natural: "ℕ", naturals: "ℕ", n: "ℕ",
  int: "ℤ", integer: "ℤ", integers: "ℤ", z: "ℤ",
  rat: "ℚ", rational: "ℚ", rationals: "ℚ", q: "ℚ",
  real: "ℝ", reals: "ℝ", r: "ℝ",
  complex: "ℂ", c: "ℂ",
};
// `n : N` is too ambiguous to set as ℕ; only the spelled-out names and the
// blackboard letters count as types, so the one-letter keys above apply to
// \mathbb{N} alone.
const SPELLED_TYPES = new Set(Object.keys(TYPE_NAMES).filter((k) => k.length > 1));

const GREEK = {
  alpha: "α", beta: "β", gamma: "γ", delta: "δ", epsilon: "ϵ", varepsilon: "ε", zeta: "ζ",
  eta: "η", theta: "θ", iota: "ι", kappa: "κ", lambda: "λ", mu: "μ", nu: "ν", xi: "ξ",
  pi: "π", rho: "ρ", sigma: "σ", tau: "τ", upsilon: "υ", phi: "ϕ", varphi: "φ", chi: "χ",
  psi: "ψ", omega: "ω", Delta: "Δ", Gamma: "Γ", Theta: "Θ", Lambda: "Λ", Xi: "Ξ", Pi: "Π",
  Sigma: "Σ", Phi: "Φ", Psi: "Ψ", Omega: "Ω",
};

// Every spelling the grammar accepts, folded onto the one sign it prints as.
const RELATIONS = {
  "<=": "≤", "\\le": "≤", "\\leq": "≤", "≤": "≤",
  ">=": "≥", "\\ge": "≥", "\\geq": "≥", "≥": "≥",
  "!=": "≠", "/=": "≠", "\\neq": "≠", "≠": "≠",
  "<": "<", ">": ">", "=": "=",
  "\\equiv": "≡", "≡": "≡",
  in: "∈", "\\in": "∈", "∈": "∈",
  "not in": "∉", "\\notin": "∉", "∉": "∉",
  subset: "⊂", "\\subset": "⊂", "⊂": "⊂",
  subseteq: "⊆", "\\subseteq": "⊆", "⊆": "⊆",
};
const IFF = new Set(["<=>", "<->", "\\iff", "iff", "⇔", "⟺", "↔"]);
const IMPLIES = new Set(["=>", "->", "\\implies", "implies", "⇒", "⟹", "\\to", "\\rightarrow", "→"]);
const OR = new Set(["\\lor", "\\/", "or", "∨"]);
const AND = new Set(["\\land", "/\\", "and", "∧"]);
const NOT = new Set(["\\neg", "~", "not", "¬"]);
const ADD = { "+": "+", "-": "−", "−": "−", "\\cup": "∪", union: "∪", "∪": "∪", "\\setminus": "∖", setminus: "∖" };
const MUL = {
  "*": "*", "·": "·", "\\cdot": "·", "/": "/",
  "\\cap": "∩", intersect: "∩", "∩": "∩", "\\circ": "∘", "∘": "∘", "\\times": "×", "×": "×",
};
const QUANTIFIERS = { forall: "∀", "\\forall": "∀", "∀": "∀", exists: "∃", "\\exists": "∃", "∃": "∃" };
const INFINITY = new Set(["\\infty", "∞", "oo", "infinity"]);
const EMPTY = new Set(["\\emptyset", "\\empty", "\\varnothing", "emptyset", "EmptySet", "∅"]);
// The words that are operators, matched whole and case-insensitively as the grammar does.
const WORD_OPS = new Set(["in", "subset", "subseteq", "iff", "implies", "or", "and", "not", "union", "intersect", "setminus"]);

const SUPERSCRIPT_DIGITS = { "⁰": "0", "¹": "1", "²": "2", "³": "3", "⁴": "4", "⁵": "5", "⁶": "6", "⁷": "7", "⁸": "8", "⁹": "9" };

// The notes' big operators, each followed by `_` and its limits.
const BIG_OPERATORS = new Set(["\\sum", "\\int", "\\lim"]);

class Unsupported extends Error {}

function tokenize(text) {
  const tokens = [];
  let i = 0;
  const push = (kind, value) => tokens.push({ kind, value });
  while (i < text.length) {
    const rest = text.slice(i);
    let m;
    // `\,` is a thin space, as `\int f(t) \,dt` writes it.
    if ((m = rest.match(/^(\s|\\,|\\;)+/))) {
      i += m[0].length;
      continue;
    }
    if ((m = rest.match(/^(<=>|<->|=>|->|\*\*|<=|>=|!=|\/=|\/\\|\\\/)/))) {
      push("op", m[0]);
    } else if ((m = rest.match(/^\\mathbb\s*\{\s*([A-Za-z])\s*\}/))) {
      const type = TYPE_NAMES[m[1].toLowerCase()];
      if (!type) throw new Unsupported(m[0]);
      push("type", type);
    } else if ((m = rest.match(/^\\(mathrm|operatorname)\s*\{\s*d\s*\}/))) {
      push("ident", "d");
    } else if ((m = rest.match(/^_/)) && BIG_OPERATORS.has(tokens.at(-1)?.value)) {
      push("_", "_");
    } else if ((m = rest.match(/^\\[a-zA-Z]+/))) {
      const name = m[0].slice(1);
      if (name in GREEK) push("greek", GREEK[name]);
      else if (INFINITY.has(m[0])) push("infty", "∞");
      else if (EMPTY.has(m[0])) push("empty", "∅");
      else push("op", m[0]);
    } else if ((m = rest.match(/^[⁺⁻]?[⁰¹²³⁴-⁹]+/))) {
      push("sup", m[0]);
    } else if ((m = rest.match(/^[0-9]+(\.[0-9]+)?/))) {
      push("num", m[0]);
    } else if ((m = rest.match(/^not\s+in\b/i))) {
      push("op", "not in");
    } else if ((m = rest.match(/^[a-zA-Z_][a-zA-Z0-9_]*/))) {
      const word = m[0];
      const lower = word.toLowerCase();
      if (lower in QUANTIFIERS) push("quant", QUANTIFIERS[lower]);
      else if (WORD_OPS.has(lower)) push("op", lower);
      else if (INFINITY.has(lower)) push("infty", "∞");
      else if (EMPTY.has(word) || lower === "emptyset") push("empty", "∅");
      else if (lower === "mod") push("mod", word);
      else push("ident", word);
    } else if ((m = rest.match(/^"[^"]*"/))) {
      push("str", m[0]);
    } else if ((m = rest.match(/^[α-ωϵϕΓΔΘΛΞΠΣΦΨΩ]/))) {
      push("greek", m[0]);
    } else if ((m = rest.match(/^[ℝℤℕℚℂ]/))) {
      push("type", m[0]);
    } else if ((m = rest.match(/^[∀∃]/))) {
      push("quant", m[0]);
    } else if ((m = rest.match(/^[∞]/))) {
      push("infty", "∞");
    } else if ((m = rest.match(/^[∅]/))) {
      push("empty", "∅");
    } else if ((m = rest.match(/^√/))) {
      push("sqrt", m[0]);
    } else if ((m = rest.match(/^!/))) {
      push("bang", m[0]);
    } else if ((m = rest.match(/^[()[\]{},:|]/))) {
      push(m[0], m[0]);
    } else if ((m = rest.match(/^[+\-*/^=<>~·×−∪∩∘≤≥≠≡∈∉⊂⊆∧∨¬⇒⇔⟹⟺↔→]/))) {
      push("op", m[0]);
    } else {
      // `$…$`, `_`, `\sum_{…}` and anything else the editor would have to
      // guess at: leave the span as source.
      throw new Unsupported(rest[0]);
    }
    i += m[0].length;
  }
  return tokens;
}

// ---------------------------------------------------------------------------
// Parser (grammar.lark, from `expr` down)
// ---------------------------------------------------------------------------

class Parser {
  constructor(tokens) {
    this.tokens = tokens;
    this.i = 0;
  }

  peek(offset = 0) {
    return this.tokens[this.i + offset];
  }

  next() {
    return this.tokens[this.i++];
  }

  expect(kind) {
    const token = this.next();
    if (!token || token.kind !== kind) throw new Unsupported(`expected ${kind}`);
    return token;
  }

  done() {
    return this.i >= this.tokens.length;
  }

  isOp(set) {
    const t = this.peek();
    if (!t || t.kind !== "op") return false;
    return set instanceof Set ? set.has(t.value) : t.value in set;
  }

  expr() {
    const t = this.peek();
    if (t?.kind === "quant") return this.quantifier();
    return this.iff();
  }

  quantifier() {
    const q = this.next().value;
    const v = this.variable();
    let type = null;
    let bound = null;
    if (this.peek()?.kind === ":") {
      this.next();
      type = this.typeName();
    } else if (this.isOp(RELATIONS)) {
      const op = RELATIONS[this.next().value];
      const rhs = this.arith();
      // `forall x in Real` is a type, as `forall x : Real` is.
      bound = { op, rhs: op === "∈" && rhs.t === "id" ? typeNode(rhs.name) : rhs };
    }
    this.expect(",");
    return { t: "quant", q, v, type, bound, body: this.expr() };
  }

  variable() {
    const t = this.next();
    if (t?.kind === "ident") return { t: "id", name: t.value };
    if (t?.kind === "greek") return { t: "sym", text: t.value, cls: "var" };
    throw new Unsupported("variable");
  }

  typeName() {
    const t = this.next();
    if (t?.kind === "type") return { t: "type", text: t.value };
    if (t?.kind === "ident") return typeNode(t.value);
    throw new Unsupported("type");
  }

  // iff / implies take a whole quantifier on the right, as in the grammar.
  iff() {
    const left = this.implies();
    if (this.isOp(IFF)) {
      this.next();
      return { t: "bin", op: "⇔", l: left, r: this.expr(), cls: "logic" };
    }
    return left;
  }

  implies() {
    const left = this.or();
    if (this.isOp(IMPLIES)) {
      this.next();
      return { t: "bin", op: "⇒", l: left, r: this.expr(), cls: "logic" };
    }
    return left;
  }

  or() {
    let left = this.and();
    while (this.isOp(OR)) {
      this.next();
      left = { t: "bin", op: "∨", l: left, r: this.and(), cls: "logic" };
    }
    return left;
  }

  and() {
    let left = this.not();
    while (this.isOp(AND)) {
      this.next();
      left = { t: "bin", op: "∧", l: left, r: this.not(), cls: "logic" };
    }
    return left;
  }

  not() {
    if (this.isOp(NOT)) {
      this.next();
      return { t: "un", op: "¬", e: this.not(), cls: "logic" };
    }
    return this.relation();
  }

  relation() {
    const args = [this.arith()];
    const ops = [];
    while (this.isOp(RELATIONS)) {
      ops.push(RELATIONS[this.next().value]);
      args.push(this.arith());
    }
    const node = ops.length ? { t: "rel", ops, args } : args[0];
    const mod = this.modSpec();
    return mod ? { t: "mod", e: node, m: mod } : node;
  }

  // `(mod n)`, `\pmod{n}`, `\pmod n`, `mod n`
  modSpec() {
    const t = this.peek();
    if (t?.kind === "(" && this.peek(1)?.kind === "mod") {
      this.next();
      this.next();
      const m = this.arith();
      this.expect(")");
      return m;
    }
    if (t?.kind === "op" && t.value === "\\pmod") {
      this.next();
      if (this.peek()?.kind === "{") {
        this.next();
        const m = this.arith();
        this.expect("}");
        return m;
      }
      return this.atom();
    }
    if (t?.kind === "mod") {
      this.next();
      return this.atom();
    }
    return null;
  }

  arith() {
    let left = this.term();
    while (this.isOp(ADD)) {
      const op = ADD[this.next().value];
      left = { t: "bin", op, l: left, r: this.term() };
    }
    return left;
  }

  term() {
    let left = this.unary();
    while (this.isOp(MUL)) {
      const op = MUL[this.next().value];
      left = { t: "bin", op, l: left, r: this.unary() };
    }
    return left;
  }

  unary() {
    if (this.isOp({ "+": 1, "-": 1, "−": 1 })) {
      const op = this.next().value === "+" ? "+" : "−";
      return { t: "un", op, e: this.unary() };
    }
    return this.power();
  }

  power() {
    const base = this.postfix();
    if (this.isOp({ "^": 1, "**": 1 })) {
      this.next();
      return { t: "pow", b: base, e: this.unary() };
    }
    return base;
  }

  postfix() {
    let node = this.atom();
    for (;;) {
      const t = this.peek();
      if (t?.kind === "bang") {
        this.next();
        node = { t: "fact", e: node };
      } else if (t?.kind === "sup") {
        this.next();
        node = { t: "pow", b: node, e: superscriptNode(t.value) };
      } else {
        return node;
      }
    }
  }

  atom() {
    const t = this.next();
    if (!t) throw new Unsupported("end");
    switch (t.kind) {
      case "num":
        return { t: "num", v: t.value };
      case "str":
        return { t: "str", v: t.value };
      case "infty":
        return { t: "sym", text: "∞", cls: "num" };
      case "empty":
        return { t: "sym", text: "∅", cls: "num" };
      case "type":
        return { t: "type", text: t.value };
      case "greek":
        return { t: "sym", text: t.value, cls: "var" };
      case "sqrt":
        return { t: "sqrt", e: this.atom() };
      case "|": {
        const e = this.arith();
        this.expect("|");
        return { t: "abs", e };
      }
      case "[": {
        const items = this.list("]");
        return { t: "vec", items };
      }
      case "(": {
        const e = this.expr();
        this.expect(")");
        return { t: "paren", e };
      }
      case "ident":
        // `k (mod n)` closes a congruence; it is not a call of k.
        if (this.peek()?.kind === "(" && this.peek(1)?.kind !== "mod") {
          this.next();
          return { t: "call", f: t.value, args: this.list(")") };
        }
        return { t: "id", name: t.value };
      case "op":
        if (t.value === "\\sum") return this.sum();
        if (t.value === "\\int") return this.integral();
        if (t.value === "\\lim") return this.limit();
        throw new Unsupported(t.value);
      default:
        throw new Unsupported(t.kind);
    }
  }

  // `{arith}` or a lone atom, after `_` or `^`.
  braced() {
    if (this.peek()?.kind !== "{") return this.atom();
    this.next();
    const e = this.arith();
    this.expect("}");
    return e;
  }

  // \sum_{k=0}^{n} body
  sum() {
    this.expect("_");
    this.expect("{");
    const v = this.variable();
    if (!this.isOp(RELATIONS)) throw new Unsupported("sum");
    const op = RELATIONS[this.next().value];
    const from = this.arith();
    this.expect("}");
    if (!this.isOp({ "^": 1 })) throw new Unsupported("sum");
    this.next();
    const to = this.braced();
    return { t: "sum", v, op, from, to, body: this.unary() };
  }

  // \int_{a}^{b} body dt, \int body dx
  integral() {
    let lower = null;
    let upper = null;
    if (this.peek()?.kind === "_") {
      this.next();
      lower = this.braced();
      if (!this.isOp({ "^": 1 })) throw new Unsupported("integral");
      this.next();
      upper = this.braced();
    }
    const body = this.arith();
    // The differential: `dt`, `d t`, `\mathrm{d}t`.  arith stops in front of
    // it, since a name never follows a term without an operator.
    const t = this.next();
    let v;
    if (t?.kind === "ident" && t.value === "d") v = this.variable();
    else if (t?.kind === "ident" && /^d[a-zA-Z]$/.test(t.value)) v = { t: "id", name: t.value.slice(1) };
    else if (t?.kind === "op" && t.value === "\\d") v = this.variable();
    else throw new Unsupported("differential");
    return { t: "int", lower, upper, body, v };
  }

  // \lim_{x \to a} body, with `0^+` / `0^-` for a one-sided limit
  limit() {
    this.expect("_");
    this.expect("{");
    const v = this.variable();
    if (!this.isOp(IMPLIES)) throw new Unsupported("limit");
    this.next();
    const close = this.tokens.findIndex((tok, k) => k >= this.i && tok.kind === "}");
    if (close < 0) throw new Unsupported("limit");
    let inner = this.tokens.slice(this.i, close);
    let dir = null;
    const [caret, sign] = inner.slice(-2);
    if (caret?.value === "^" && (sign?.value === "+" || sign?.value === "-")) {
      dir = sign.value === "+" ? "+" : "−";
      inner = inner.slice(0, -2);
    }
    const sub = new Parser(inner);
    const target = sub.expr();
    if (!sub.done()) throw new Unsupported("limit");
    this.i = close + 1;
    return { t: "lim", v, target, dir, body: this.term() };
  }

  list(close) {
    const items = [];
    if (this.peek()?.kind === close) {
      this.next();
      return items;
    }
    for (;;) {
      items.push(this.expr());
      const t = this.next();
      if (t?.kind === close) return items;
      if (t?.kind !== ",") throw new Unsupported("list");
    }
  }
}

function typeNode(name) {
  const lower = name.toLowerCase();
  if (SPELLED_TYPES.has(lower)) return { t: "type", text: TYPE_NAMES[lower] };
  // A structure's carrier (`a : G`) is the set it names.
  return { t: "id", name };
}

function superscriptNode(text) {
  const negative = text.startsWith("⁻");
  const digits = [...text.replace(/^[⁺⁻]/, "")].map((c) => SUPERSCRIPT_DIGITS[c]).join("");
  const num = { t: "num", v: digits };
  return negative ? { t: "un", op: "−", e: num } : num;
}

/** Parse *text* as an expression (or, for `kind: "chain"`, as `rel rhs`); null if it does not. */
export function parseMath(text, kind = "expr") {
  try {
    const parser = new Parser(tokenize(text));
    if (!parser.tokens.length) return null;
    let node;
    if (kind === "chain") {
      if (!parser.isOp(RELATIONS)) return null;
      const op = RELATIONS[parser.next().value];
      node = { t: "chain", op, rhs: parser.arith() };
    } else if (kind === "decl") {
      node = parseDecl(parser);
    } else {
      node = parser.expr();
    }
    return parser.done() ? node : null;
  } catch (error) {
    if (error instanceof Unsupported) return null;
    throw error;
  }
}

// `x, y : Real`, `k : Int`, `f : Real -> Real`, `a : G`
function parseDecl(parser) {
  const names = [parser.variable()];
  while (parser.peek()?.kind === ",") {
    parser.next();
    names.push(parser.variable());
  }
  if (parser.peek()?.kind !== ":") throw new Unsupported("decl");
  parser.next();
  const types = [parser.typeName()];
  while (parser.isOp(IMPLIES)) {
    parser.next();
    types.push(parser.typeName());
  }
  return { t: "decl", names, types };
}

// ---------------------------------------------------------------------------
// MathML
// ---------------------------------------------------------------------------

const escapeXml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const mi = (text, cls = "var") => `<mi class="vm-${cls}">${escapeXml(text)}</mi>`;
const mn = (text) => `<mn class="vm-num">${escapeXml(text)}</mn>`;
const mo = (text, cls = "op", attrs = "") => `<mo class="vm-${cls}"${attrs}>${escapeXml(text)}</mo>`;
const row = (...parts) => `<mrow>${parts.join("")}</mrow>`;
// Brackets round something taller than a line (a fraction, a sum) have to
// grow with it, and only Latin Modern's glyphs can: the CSS sets `vm-tall`
// fences in that face, and every other bracket in the editor's mono.
const fenced = (open, inner, close, tall = false) => {
  const cls = tall ? "op vm-tall" : "op";
  return row(mo(open, cls, ' fence="true"'), inner, mo(close, cls, ' fence="true"'));
};

function isTall(node) {
  if (!node || typeof node !== "object") return false;
  if (node.t === "bin" && node.op === "/") return true;
  if (["sum", "int", "lim"].includes(node.t)) return true;
  if (node.t === "call" && node.f.toLowerCase() === "binomial") return true;
  return Object.values(node).some((v) => (Array.isArray(v) ? v.some(isTall) : isTall(v)));
}

// Functions set upright as named operators, as \sin and \log are.
const NAMED_FUNCTIONS = new Set([
  "sin", "cos", "tan", "sec", "csc", "cot", "sinh", "cosh", "tanh", "arcsin", "arccos", "arctan",
  "asin", "acos", "atan", "exp", "log", "ln", "min", "max", "gcd", "lcm", "det", "tr", "lim",
  "sup", "inf", "deg", "dim", "ker", "sign", "Re", "Im",
]);

/** A name as the notes print it: Greek spelled out becomes the letter, `x_1` a subscript. */
function identifier(name, cls = "var") {
  if (name in GREEK) return mi(GREEK[name], cls);
  const sub = name.match(/^([A-Za-z]+)_([A-Za-z0-9]+)$/);
  if (sub) {
    const base = sub[1] in GREEK ? GREEK[sub[1]] : sub[1];
    const index = /^\d+$/.test(sub[2]) ? mn(sub[2]) : identifier(sub[2]);
    return `<msub>${mi(base, cls)}${index}</msub>`;
  }
  return mi(name, cls);
}

// Where a pair of brackets is only grouping -- a fraction's numerator, an
// exponent, a root -- the layout already groups it, so the brackets go.
const ungroup = (node) => (node?.t === "paren" ? node.e : node);

// `2 * k` prints as 2k, as the notes write it; anything else keeps its dot.
function juxtaposes(l, r) {
  if (l.t !== "num") return false;
  let head = r;
  while (head.t === "pow" || head.t === "fact") head = head.b ?? head.e;
  return ["id", "sym", "call", "paren", "sqrt", "abs"].includes(head.t) && !(head.t === "sym" && head.cls === "num");
}

function render(node) {
  switch (node.t) {
    case "num":
      return mn(node.v);
    case "str":
      return `<mtext class="vm-str">${escapeXml(node.v)}</mtext>`;
    case "id":
      return identifier(node.name);
    case "sym":
      return mi(node.text, node.cls);
    case "type":
      return mi(node.text, "type");
    case "paren":
      return fenced("(", render(node.e), ")", isTall(node.e));
    case "abs":
      return fenced("|", render(node.e), "|", isTall(node.e));
    case "vec":
      return fenced("[", node.items.map(render).join(mo(",", "op", ' separator="true"')), "]", node.items.some(isTall));
    case "sqrt":
      return `<msqrt>${render(ungroup(node.e))}</msqrt>`;
    case "fact":
      return row(render(node.e), mo("!", "op", ' lspace="0" rspace="0"'));
    case "pow":
      return `<msup>${row(render(node.b))}${row(render(ungroup(node.e)))}</msup>`;
    case "un":
      return row(mo(node.op, node.cls ?? "op", ' form="prefix"'), render(node.e));
    case "bin": {
      if (node.op === "/") return `<mfrac>${row(render(ungroup(node.l)))}${row(render(ungroup(node.r)))}</mfrac>`;
      if (node.op === "*") {
        const sign = juxtaposes(node.l, node.r) ? mo("⁢") : mo("·");
        return row(render(node.l), sign, render(node.r));
      }
      return row(render(node.l), mo(node.op, node.cls ?? "op"), render(node.r));
    }
    case "rel": {
      const parts = [render(node.args[0])];
      node.ops.forEach((op, i) => parts.push(mo(op, "rel"), render(node.args[i + 1])));
      return row(...parts);
    }
    case "chain":
      return row(mo(node.op, "rel", ' lspace="0"'), render(node.rhs));
    case "mod":
      return row(render(node.e), '<mspace width="0.6em"/>', mo("("), mi("mod", "fn"), '<mspace width="0.3em"/>', render(node.m), mo(")"));
    case "quant": {
      const parts = [mo(node.q, "logic", ' rspace="0"'), render(node.v)];
      if (node.type) parts.push(mo("∈", "rel"), render(node.type));
      if (node.bound) parts.push(mo(node.bound.op, "rel"), render(node.bound.rhs));
      parts.push(mo(",", "op", ' separator="true"'), '<mspace width="0.4em"/>', render(node.body));
      return row(...parts);
    }
    case "decl": {
      const names = node.names.map(render).join(mo(",", "op", ' separator="true"'));
      if (node.types.length === 1) return row(names, mo("∈", "rel"), render(node.types[0]));
      return row(names, mo(":", "rel"), node.types.map(render).join(mo("→", "rel")));
    }
    case "call":
      return renderCall(node);
    case "sum":
      return row(
        `<munderover>${mo("∑", "fn vm-big", ' largeop="true" movablelimits="true"')}${row(render(node.v), mo(node.op, "rel"), render(node.from))}${row(render(node.to))}</munderover>`,
        render(node.body),
      );
    case "int": {
      // ∫ and its d are one notation, as `integrate` is one word in the source.
      const sign = mo("∫", "fn vm-big", ' largeop="true"');
      const head = node.lower ? `<msubsup>${sign}${row(render(node.lower))}${row(render(node.upper))}</msubsup>` : sign;
      return row(head, render(node.body), '<mspace width="0.2em"/>', mi("d", "fn"), render(node.v));
    }
    case "lim": {
      const target = node.dir ? `<msup>${row(render(node.target))}${mo(node.dir)}</msup>` : render(node.target);
      return row(`<munder>${mo("lim", "fn", ' movablelimits="true"')}${row(render(node.v), mo("→", "rel"), target)}</munder>`, render(node.body));
    }
    default:
      throw new Error(`unknown node ${node.t}`);
  }
}

function renderCall(node) {
  const fn = node.f.toLowerCase();
  const [a, b] = node.args;
  if (node.args.length === 1) {
    if (fn === "sqrt") return `<msqrt>${render(a)}</msqrt>`;
    if (fn === "abs") return fenced("|", render(a), "|", isTall(a));
    if (fn === "norm") return fenced("‖", render(a), "‖", isTall(a));
    if (fn === "factorial") return row(render(a), mo("!", "op", ' lspace="0" rspace="0"'));
    if (fn === "inv" || fn === "inverse") return `<msup>${row(render(a))}${row(mo("−", "op", ' form="prefix"'), mn("1"))}</msup>`;
    if (fn === "floor") return fenced("⌊", render(a), "⌋", isTall(a));
    if (fn === "ceil" || fn === "ceiling") return fenced("⌈", render(a), "⌉", isTall(a));
    if (fn === "conj" || fn === "conjugate") return `<mover>${row(render(a))}${mo("‾", "op", ' stretchy="true"')}</mover>`;
  }
  if (node.args.length === 2 && fn === "binomial") return fenced("(", `<mfrac linethickness="0">${row(render(a))}${row(render(b))}</mfrac>`, ")", true);
  const named = NAMED_FUNCTIONS.has(node.f) || NAMED_FUNCTIONS.has(fn);
  const name = identifier(node.f, named ? "fn" : /^[A-Z]/.test(node.f) ? "type" : "var");
  const args = node.args.map(render).join(mo(",", "op", ' separator="true"'));
  return row(name, mo("⁡"), fenced("(", args, ")", node.args.some(isTall)));
}

/** The MathML for one parsed node, wrapped as an inline <math> element. */
export function toMathML(node) {
  return `<math class="vm" display="inline">${render(node)}</math>`;
}

// ---------------------------------------------------------------------------
// Where the mathematics is in a line
// ---------------------------------------------------------------------------

// Openers whose rest of line is one statement, by grammar rule.
const DEDUCE = /^(therefore|thus|hence|so|then|conclude|it\s+follows\s+that|we\s+(?:have|get)|we\s+see\s+that|(?:note|observe)\s+that|now,?|clearly,?)(?![a-zA-Z0-9_])\s*/i;
const SEPARATOR = /^\s*(such\s+that|where|satisfying|with)\s+/i;

/** One span of mathematics: [from, to) offsets into the line, and how to read it. */
function span(line, from, to, kind = "expr") {
  while (from < to && /\s/.test(line[from])) from++;
  while (to > from && /\s/.test(line[to - 1])) to--;
  return to > from ? { from, to, kind, text: line.slice(from, to) } : null;
}

// Where the statement stops: before a comment, a `[justification]`, a
// `[witness: …]` (returned separately) or a trailing `using …` / `by …`.
function statementEnd(line, start) {
  let end = line.length;
  const comment = line.slice(start).search(/#|(^|\s)--/);
  if (comment >= 0) end = start + comment;
  return end;
}

function trailing(line, from, to) {
  const extra = [];
  let text = line.slice(from, to);
  // [witness: e] carries an expression of its own.
  let m = text.match(/\[\s*witness\s*:\s*([^\]]*)\]\s*$/i);
  if (m) {
    const at = from + m.index;
    const inner = at + m[0].indexOf(m[1]);
    extra.push(span(line, inner, inner + m[1].length));
    to = at;
    text = line.slice(from, to);
  }
  m = text.match(/\[[^\]]*\]\s*$/);
  // A justification, not a vector: words, not a comma-separated list.
  if (m && (!m[0].includes(",") || /[a-zA-Z]{2,}\s+[a-zA-Z]/.test(m[0])) && /[a-zA-Z]{2}/.test(m[0])) {
    to = from + m.index;
    text = line.slice(from, to);
  }
  m = text.match(/\s(using|by)\s+[a-zA-Z0-9_,.^+*\-\\/"' \t]+$/i);
  if (m) to = from + m.index;
  return { to, extra };
}

/**
 * The spans of one line that are mathematics.  Each is `{from, to, kind,
 * text}` with `kind` one of "expr", "chain" (`= rhs`, continuing the step
 * above) or "decl" (`x, y : Real`).  Keywords, labels, names and
 * justifications are never inside a span.
 */
export function mathSpans(line) {
  const start = line.length - line.trimStart().length;
  const end = statementEnd(line, start);
  const body = line.slice(start, end);
  const out = [];
  const add = (s) => s && out.push(s);
  let m;

  const expression = (from, to) => {
    const { to: stop, extra } = trailing(line, from, to);
    const s = span(line, from, stop);
    if (s && /^\s*(=|<|>|!=|\/=|\\le|\\ge|\\neq|[≤≥≠≡])/.test(s.text) && !/^\s*(=>|<=>|->)/.test(s.text)) s.kind = "chain";
    add(s);
    for (const e of extra) add(e);
  };

  if (!body || /^(theorem|lemma|proposition|proof|qed|import)\b/i.test(body)) return out;

  if ((m = body.match(/^claim\s*:/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^(definition(\s+\d+(\.\d+)*[a-z]?)?(\s*\([^)\n]*\))?\s*:|define\b)/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^(let|given|fix|take)\s+/i))) {
    const from = start + m[0].length;
    const rest = line.slice(from, end);
    const decl = rest.match(/^([^:]+:[^:]*?)(?=\s+(?:with|such\s+that|where|satisfying)\s+|$)/i);
    if (decl && !/[=<(]|[^-]>/.test(decl[1])) {
      add(span(line, from, from + decl[1].length, "decl"));
      const sep = line.slice(from + decl[1].length, end).match(SEPARATOR);
      if (sep) expression(from + decl[1].length + sep[0].length, end);
    } else {
      const given = rest.match(/\s+be\s+given\s*$/i);
      expression(from, given ? from + given.index : end);
    }
  } else if ((m = body.match(/^(set|put)\s+(?=\S+\s*=)/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^(assume|suppose|hypothesize)\s+([A-Za-z_][A-Za-z0-9_]*\s*:(?!=)\s*)?/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^(obtain|choose|pick)\s+/i))) {
    const from = start + m[0].length;
    const rest = line.slice(from, end);
    const sep = rest.match(/\s+(such\s+that|where|satisfying)\s+/i);
    if (sep) {
      add(span(line, from, from + sep.index, /:/.test(rest.slice(0, sep.index)) ? "decl" : "expr"));
      const exprFrom = from + sep.index + sep[0].length;
      const source = line.slice(exprFrom, end).match(/\s+from\s+[A-Za-z_][A-Za-z0-9_]*\s*$/i);
      expression(exprFrom, source ? exprFrom + source.index : end);
    }
  } else if ((m = body.match(/^step\s*:/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^since(?![a-zA-Z0-9_])\s*/i))) {
    // `Since P, Q`: the comma that splits it is the first one with a whole
    // expression on either side (P itself may hold commas: `forall x, …`).
    const from = start + m[0].length;
    const { to } = trailing(line, from, end);
    for (let i = from; i < to; i++) {
      if (line[i] !== "," || !parseMath(line.slice(from, i))) continue;
      if (!parseMath(line.slice(i + 1, to).replace(/\[\s*witness[^\]]*\]\s*$/i, ""))) continue;
      add(span(line, from, i));
      expression(i + 1, end);
      break;
    }
  } else if ((m = body.match(/^by(?![a-zA-Z0-9_])[^,\n[\]]+,/i))) {
    expression(start + m[0].length, end);
  } else if ((m = body.match(/^(base\s+case|induct(?:ive|ion)\s+step|case)\b(.*):\s*$/i))) {
    if (m[2].trim()) add(span(line, start + m[1].length, start + m[1].length + m[2].length));
  } else if ((m = body.match(DEDUCE))) {
    expression(start + m[0].length, end);
  }
  return out;
}

/** The MathML for a span, or null when it is not something the editor can typeset. */
export function renderSpan(s) {
  const node = parseMath(s.text, s.kind);
  // A lone name or number is already what it prints as; replacing it would
  // only make it harder to click into.
  if (!node || node.t === "id" || node.t === "num") return null;
  return toMathML(node);
}
