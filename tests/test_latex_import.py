"""Paste LaTeX: a proof written in LaTeX becomes a Lemmata draft that parses."""

import pytest

from aether import ProofChecker
from aether.core.latex_import import latex_to_lemmata, math


def verdicts(source: str) -> list[str]:
    return [r.status.value for rep in ProofChecker().check_source(source) for r in rep.results]


@pytest.mark.parametrize(
    ("tex", "lemmata"),
    [
        (r"\frac{x^2-4}{x-2}", "((x^(2)-4)/(x-2))"),
        (r"x^{2} + 2k", "x^(2) + 2*k"),
        (r"\sqrt{x^2+1}", "sqrt(x^(2)+1)"),
        (r"\left( x + 1 \right)^2", "( x + 1 )^(2)"),
        (r"3|x - 2|", "3*|x - 2|"),
        (r"x \in \mathbb{R}", r"x \in ℝ"),
        (r"a_{n+1} \leq a_n", r"a(n+1) \leq a(n)"),
        (r"x_1 + x_2", "x_1 + x_2"),
        (r"\sum_{k=1}^{n} (2k-1) = n^2", r"\sum_{k=1}^{n} (2*k-1) = n^(2)"),
        (r"x \cdot y \,=\, y \cdot x.", "x * y = y * x"),
    ],
)
def test_the_maths_is_what_the_parser_reads(tex, lemmata):
    assert math(tex) == lemmata


EVEN_SQUARE = r"""
\documentclass{article}
\begin{document}
\begin{theorem}[Even square]
If $n$ is even, then $n^2$ is divisible by $4$.
\end{theorem}
\begin{proof}
Let $n \in \mathbb{Z}$. Suppose $n = 2k$ for some integer $k$.  % the witness
Then
\begin{align*}
n^2 &= (2k)^2 \\
    &= 4k^2.
\end{align*}
Hence $n^2 = 4k^2$. \qed
\end{proof}
\end{document}
"""


def test_a_theorem_and_its_proof():
    draft = latex_to_lemmata(EVEN_SQUARE)
    lines = draft.source.splitlines()
    assert lines[0] == 'Theorem: "Even square"'
    assert lines[1].startswith("# Statement: If $n$ is even")
    assert "    Let k ∈ ℤ" in lines and "    Assume n = 2*k" in lines
    assert "    Step: n^(2) = (2*k)^(2)" in lines and "    Step: = 4*k^(2)" in lines
    assert lines[-1] == "QED"
    assert verdicts(draft.source) == ["VALID"] * 6


def test_an_epsilon_delta_proof_checks_as_pasted():
    tex = r"""\begin{proof}
Let $\epsilon > 0$ be given. Take $\delta = \epsilon / 3$.
Then $\delta > 0$. Suppose $|x - 2| < \delta$. Then
\[ |3x - 6| = 3|x - 2| < 3\delta = \epsilon. \]
\end{proof}"""
    draft = latex_to_lemmata(tex)
    assert r"    Let \epsilon > 0 be given" in draft.source.splitlines()
    assert set(verdicts(draft.source)) == {"VALID"}


def test_a_sentence_with_two_clauses_and_a_since():
    draft = latex_to_lemmata(r"Let $x \in \mathbb{R}$ and suppose $x > 2$. Since $x > 2$, $x + 2 > 4$.")
    assert draft.source.splitlines()[:3] == [r"Let x \in ℝ", "Assume x > 2", "Since x > 2, x + 2 > 4"]


def test_what_it_cannot_place_is_a_comment_saying_why():
    draft = latex_to_lemmata(r"Let $x \in \mathbb{R}$. Consider the function $f$.")
    assert "# Consider the function $f$ ." in draft.source
    assert draft.comments and draft.comments[-1]["why"]


def test_a_line_the_parser_refuses_is_commented_out_so_the_draft_parses():
    draft = latex_to_lemmata(r"Then $x = 3 @@ 4$.")
    ProofChecker().check_source(draft.source)  # parses
    assert any("could not read" in c["why"] for c in draft.comments)


def test_the_same_input_gives_the_same_draft():
    assert latex_to_lemmata(EVEN_SQUARE).source == latex_to_lemmata(EVEN_SQUARE).source
