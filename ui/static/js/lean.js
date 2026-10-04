// "Show in Lean": the proof beside the Lean 4 + Mathlib skeleton it states.
//
// The engine (aether.core.lean_export) answers {lean, rows, untranslated}:
// `rows` runs through the Lean in order, each run of Lean lines with the
// source line it came from (null for Lean's own scaffolding) and that line's
// verdict.  This module lays the two out row by row, so "this line became
// this tactic" reads straight across.
//
// `leanTokens`, `sourceTokens` and `leanEditorUrl` are pure, so
// verify_frontend.mjs tests them in Node.

/** Lean's own words in a skeleton: declarations and tactics. */
const LEAN_KEYWORDS = new Set([
  "import", "namespace", "end", "theorem", "example", "def", "noncomputable", "fun", "by",
  "have", "obtain", "intro", "set", "with", "calc", "exact", "induction", "let", "trivial",
]);

/** The words a Lemmata proof is built from, as the editor colours them. */
const SOURCE_KEYWORD =
  /^(\s*)(Theorem|Lemma|Proposition|Claim|Proof|QED|Let|Given|Fix|Take|Set|Put|Assume|Suppose|Obtain|Choose|Pick|Step|Therefore|Thus|Hence|So|Then|Since|By|Case|Base case|Inductive step|Induction step|Subproof|Definition|Define|import|We have|We get|Note that|Observe that|It follows that|Now|Clearly)\b/i;

/**
 * Lean lines as [[{text, kind}]], kind "kw", "sorry", "comment" or "".  A `--`
 * comment runs to the end of its line; a `/- … -/` block spans lines.
 */
export function leanTokenLines(lines) {
  let inBlock = false;
  return lines.map((line) => {
    const out = [];
    const push = (text, kind = "") => {
      if (!text) return;
      const last = out[out.length - 1];
      if (last && last.kind === kind) last.text += text;
      else out.push({ text, kind });
    };
    let rest = line;
    while (rest) {
      if (inBlock) {
        const end = rest.indexOf("-/");
        if (end < 0) {
          push(rest, "comment");
          break;
        }
        push(rest.slice(0, end + 2), "comment");
        rest = rest.slice(end + 2);
        inBlock = false;
        continue;
      }
      const block = rest.indexOf("/-");
      const dash = rest.indexOf("--");
      const cut = [block, dash].filter((i) => i >= 0).sort((a, b) => a - b)[0] ?? -1;
      const code = cut >= 0 ? rest.slice(0, cut) : rest;
      for (const part of code.split(/([A-Za-z_][A-Za-z0-9_'.]*)/)) {
        if (part === "sorry") push(part, "sorry");
        else if (LEAN_KEYWORDS.has(part)) push(part, "kw");
        else push(part);
      }
      if (cut < 0) break;
      if (cut === dash) {
        push(rest.slice(cut), "comment");
        break;
      }
      inBlock = true;
      rest = rest.slice(cut);
    }
    return out;
  });
}

/** One Lean line, outside any block comment, as [{text, kind}]. */
export function leanTokens(line) {
  return leanTokenLines([line])[0];
}

/** A source line as [{text, kind}]: its leading keyword, then the rest. */
export function sourceTokens(line) {
  const m = SOURCE_KEYWORD.exec(line);
  if (!m) return line ? [{ text: line, kind: "" }] : [];
  const out = [];
  if (m[1]) out.push({ text: m[1], kind: "" });
  out.push({ text: m[2], kind: "kw" });
  const rest = line.slice(m[0].length);
  if (rest) out.push({ text: rest, kind: "" });
  return out;
}

/** Lean's web editor (it has Mathlib), opened on *code*. */
export function leanEditorUrl(code) {
  return `https://live.lean-lang.org/#code=${encodeURIComponent(code)}`;
}

/** The skeleton's file name for *stem* (a proof's file name or theorem). */
export function leanFilename(stem) {
  const slug = String(stem ?? "")
    .replace(/\.aether$/, "")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return `${slug || "Proof"}.lean`;
}

/** "Not translated, so stated as `sorry`: …", or "" when everything translated. */
export function untranslatedNote(items) {
  if (!items?.length) return "";
  const parts = items.map(({ line, what }) => (line ? `${what} (line ${line})` : what));
  return `Not translated, so left as sorry: ${parts.join("; ")}.`;
}

function tokenNodes(tokens) {
  const frag = document.createDocumentFragment();
  for (const { text, kind } of tokens) {
    if (!kind) {
      frag.append(text);
      continue;
    }
    const span = document.createElement("span");
    span.className = `lean-tok lean-tok--${kind}`;
    span.textContent = text;
    frag.append(span);
  }
  return frag;
}

function cell(className) {
  const el = document.createElement("div");
  el.className = `lean-cell ${className}`;
  el.setAttribute("role", "cell");
  return el;
}

function numberedLine(n, tokens) {
  const line = document.createElement("span");
  line.className = "lean-line";
  const num = document.createElement("span");
  num.className = "lean-n";
  num.textContent = n == null ? "" : String(n);
  num.setAttribute("aria-hidden", "true");
  const text = document.createElement("code");
  text.className = "lean-text";
  text.append(tokenNodes(tokens));
  line.append(num, text);
  return line;
}

/**
 * Lay *result* out in *container*: one row per run of Lean lines.  *source*
 * is the proof's text, so the lines that became no Lean (`Proof:`, a blank)
 * still show, quietly, in the row before them.
 */
export function renderLeanRows(container, result, source = "") {
  container.replaceChildren();
  const lean = leanTokenLines(result.lean.split("\n"));
  const sourceLines = source.split("\n");
  const owned = result.rows.map((r) => r.line).filter((n) => n != null);
  const last = Math.max(0, ...owned);
  const shown = new Set();
  for (const row of result.rows) {
    const el = document.createElement("div");
    el.className = "lean-row";
    el.setAttribute("role", "row");
    if (row.status === "INVALID") el.classList.add("is-invalid");
    else if (row.status === "WARNING") el.classList.add("is-warning");

    const src = cell("lean-src");
    if (row.line == null) {
      el.classList.add("is-scaffold");
    } else {
      // A line whose Lean is split around other lines appears again, quietly.
      if (shown.has(row.line)) el.classList.add("is-repeat");
      shown.add(row.line);
      src.append(numberedLine(row.line, sourceTokens(row.source)));
      // The lines up to the next one that became Lean belong here.
      if (!el.classList.contains("is-repeat")) {
        for (let n = row.line + 1; n <= last && !owned.includes(n); n += 1) {
          const gap = numberedLine(n, sourceTokens(sourceLines[n - 1] ?? ""));
          gap.classList.add("is-quiet");
          src.append(gap);
        }
      }
    }

    const out = cell("lean-out");
    for (let n = row.lean_from; n <= row.lean_to; n += 1) out.append(numberedLine(n, lean[n - 1] ?? []));
    el.append(src, out);
    container.append(el);
  }
}

/** A one-row message in place of the rows: loading, or why there is no Lean. */
export function renderLeanMessage(container, text, { error = false } = {}) {
  const el = document.createElement("div");
  el.className = `lean-message${error ? " is-error" : ""}`;
  el.setAttribute("role", "row");
  const inner = document.createElement("span");
  inner.setAttribute("role", "cell");
  inner.textContent = text;
  el.append(inner);
  container.replaceChildren(el);
}
