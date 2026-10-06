"""The command line: the audit, and with --used and --trace, what each line used and what was asked."""

import sys

import pytest

from aether import main

SCRATCH = """\
Let x : Real
Assume hx: x > 2
Step: x^2 > 4
"""


def run(monkeypatch, capsys, tmp_path, *flags):
    proof = tmp_path / "scratch.aether"
    proof.write_text(SCRATCH)
    monkeypatch.setattr(sys, "argv", ["lemmata", *flags, str(proof)])
    main()
    return capsys.readouterr().out


def test_the_audit_alone_is_unchanged(monkeypatch, capsys, tmp_path):
    out = run(monkeypatch, capsys, tmp_path)
    assert "Result: VALID" in out
    assert "used" not in out and "Trace" not in out


def test_used_names_the_premise(monkeypatch, capsys, tmp_path):
    out = run(monkeypatch, capsys, tmp_path, "--used")
    assert "What each line used" in out
    assert "used L2 hx: x > 2" in out


def test_trace_lists_the_calls(monkeypatch, capsys, tmp_path):
    out = run(monkeypatch, capsys, tmp_path, "--trace")
    assert "\nTrace\n" in out
    assert "Z3" in out and "entails" in out and "-> holds" in out


def test_the_flags_are_in_the_help(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["lemmata", "--help"])
    main()
    out = capsys.readouterr().out
    assert "--used" in out and "--trace" in out


def test_a_failing_proof_still_exits_1(monkeypatch, capsys, tmp_path):
    proof = tmp_path / "bad.aether"
    proof.write_text("Let x : Real\nStep: (x + 1)^2 = x^2 + 1\n")
    monkeypatch.setattr(sys, "argv", ["lemmata", "--trace", str(proof)])
    with pytest.raises(SystemExit) as exit_:
        main()
    assert exit_.value.code == 1
