"""Real-browser regression tests for the Aether UI.

Drives a headless Chrome through the `agent-browser` CLI and asserts the
behaviours that are awkward to catch any other way: editor key bindings, the
debounced round-trip, the client-side step inspector, and auditor keyboard
navigation.

Starts its own server on a free port and cleans up afterwards.

Run with:  uv run python ui/verify_browser.py

Requires the `agent-browser` CLI and a Chrome/Chromium binary. If either is
missing the script reports SKIPPED and exits 0.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent

failures: list[str] = []


def check(condition: bool, message: str) -> bool:
    print(f"  [{'ok ' if condition else 'FAIL'}] {message}")
    if not condition:
        failures.append(message)
    return condition


AB = shutil.which("agent-browser")
CHROME = next(
    (
        shutil.which(name)
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chrome", "chromium-browser")
        if shutil.which(name)
    ),
    None,
)

if AB is None or CHROME is None:
    print("SKIPPED: agent-browser and/or Chrome are not installed.")
    print("Install with: npm i -g agent-browser && agent-browser install")
    sys.exit(0)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
# A dedicated session so we never hijack whatever the shared default is doing.
SESSION = f"aether-verify-{PORT}"

_env = {**os.environ, "AGENT_BROWSER_SESSION": SESSION}


def ab(*args: str, stdin: str | None = None) -> str:
    result = subprocess.run(
        [AB, *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=_env,
        timeout=180,
    )
    return result.stdout.strip()


def js(script: str):
    """Evaluate JS and return the parsed result."""
    out = ab("eval", "--stdin", stdin=script)
    try:
        value = json.loads(out)
    except json.JSONDecodeError:
        return out
    if isinstance(value, str) and value[:1] in "[{":
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


PROBE = """JSON.stringify({
  verdict: (document.querySelector('#verdict')||{}).textContent ?? null,
  stale: (document.querySelector('#verdict')||{}).dataset?.stale ?? null,
  meta: (document.querySelector('#verdict-meta')||{}).textContent ?? null,
  selected: (document.querySelector('.step.is-selected')||{}).dataset?.index ?? null,
  ctxTitle: (document.querySelector('#context .ctx-title')||{}).textContent ?? null,
  ctxHas: (document.querySelector('#context')||{}).textContent ?? '',
  activeLine: (document.querySelector('.cm-activeLineGutter')||{}).textContent ?? null,
  focus: (document.activeElement.className || '').split(' ')[0],
  steps: document.querySelectorAll('.step').length,
  lines: [...document.querySelectorAll('.cm-line')].map(l => l.textContent),
  hash: location.hash,
  toast: document.querySelector('#toast').hidden ? null : document.querySelector('#toast').textContent,
})"""


def probe() -> dict:
    return js(PROBE)


def settle(timeout: float = 12.0) -> dict:
    """Wait until the verdict describes the current buffer again.

    Both conditions matter.  "Checking…" covers an in-flight request, and the
    `stale` flag covers the debounce window before it -- without that second
    check, an edit would be read against the *previous* buffer's verdict,
    which looks exactly like a re-check that did not happen.
    """
    deadline = time.time() + timeout
    state = probe()
    while time.time() < deadline and (
        state["verdict"] in ("Checking…", "Ready", None) or state["stale"]
    ):
        time.sleep(0.2)
        state = probe()
    return state


# Filled in once the server is up; see main().
STARTING_SOURCE = ""


def permalink(source: str, strict: bool = False) -> str:
    """A URL that loads *source*, forcing a real navigation.

    Two separate traps here.  A navigation that only changes the fragment is a
    same-document change and does not reload, so the URL always carries a
    unique query string.  And the app's own unload flush rewrites storage
    during a navigation, so clearing storage can never be relied on -- the
    fragment has to be what decides the starting point.
    """
    token = base64.urlsafe_b64encode(source.encode("utf-8")).decode().rstrip("=")
    return f"{BASE}/?r={time.time_ns()}#p={token}" + ("&s=1" if strict else "")


def reset_page() -> dict:
    """Load the starting example in a guaranteed-fresh page."""
    ab("open", permalink(STARTING_SOURCE))
    return settle()


def append_to_line(line_number: int, text: str) -> None:
    """Put the caret at the end of a line and type into it for real."""
    ab("click", f".cm-line:nth-child({line_number})")
    ab("press", "End")
    ab("keyboard", "type", text)


def timeline_checks() -> int:
    """How many checks the timeline accounts for.

    Not the number of segments: consecutive identical verdicts are coalesced
    into one segment with a run count, which is exactly what happens when you
    keep typing into a proof that stays valid.
    """
    return int(
        js(
            "[...document.querySelectorAll('#timeline .tl-bar')]"
            ".reduce((sum, bar) => sum + Number(bar.style.flexGrow), 0)"
        )
    )


def load_example(example_id: str) -> dict:
    ab("select", "#examples", example_id)
    time.sleep(0.4)
    return settle()


def run_checks() -> None:
    print("== open the page ==")
    ab("open", BASE)
    state = settle()
    check(state["verdict"] == "VALID", f"starts on a valid proof ({state['verdict']})")
    check(state["steps"] == 8, f"auditor lists {state['steps']} steps")

    print("== editor key bindings ==")
    state = load_example("parse-error")
    check(state["verdict"] == "PARSE ERROR", f"unindented body errors ({state['verdict']})")

    ab("click", ".cm-line:nth-child(3)")  # "Given n : Int", unindented
    ab("press", "Home")
    ab("press", "Tab")
    time.sleep(0.4)
    lines = probe()["lines"]
    check(
        lines[2] == "    Given n : Int",
        f"Tab inserts 4 spaces, not a tab ({lines[2]!r})",
    )

    print("== debounced re-check ==")
    # Indenting that line gives the proof body a real statement, so the
    # debounced re-check should now accept the document.
    state = settle()
    check(
        state["verdict"] == "VALID",
        f"auto re-check flips PARSE ERROR -> {state['verdict']}",
    )
    check(state["steps"] == 2, f"re-check audited {state['steps']} steps")

    ab("press", "Home")
    ab("press", "Shift+Tab")  # agent-browser spells chords with '+'
    time.sleep(0.4)
    check(probe()["lines"][2] == "Given n : Int", "Shift+Tab removes the indent")

    ab("click", ".cm-line:nth-child(2)")  # "Proof:"
    ab("press", "End")
    ab("press", "Enter")
    time.sleep(0.4)
    # Note: this leaves a whitespace-only line.  Lark's indenter does not treat
    # that as an indented block, so the document stays a parse error -- that is
    # correct behaviour, which is why no verdict assertion follows here.
    check(
        probe()["lines"][2] == "    ",
        "Enter after a ':' line auto-indents by one level",
    )

    print("== clicking a step must not re-run the solver ==")
    reset_page()
    ab("network", "requests", "--clear")
    ab("click", ".report-group button.step:nth-of-type(3)")
    time.sleep(0.8)
    state = probe()
    check(state["selected"] == "2", f"step 3 selected (index {state['selected']})")
    check("Obtain" in state["ctxTitle"], f"inspector shows the step ({state['ctxTitle'][:40]!r})")
    check("k : Int" in state["ctxHas"], "inspector lists a declared variable")
    requests = ab("network", "requests", "--filter", "api/check")
    check("No requests captured" in requests, "zero /api/check requests on click")

    print("== clicking a line in the editor selects that step ==")
    reset_page()
    ab("network", "requests", "--clear")
    # Line 7 of the even-square sample is "Step: = 4 * k^2", i.e. step index 4.
    ab("click", ".cm-line:nth-child(7)")
    time.sleep(0.6)
    state = probe()
    check(state["selected"] == "4", f"editor line 7 selected step index {state['selected']}")
    check("4 *" in (state["ctxTitle"] or ""), f"inspector follows the line ({state['ctxTitle']!r})")
    check(state["focus"].startswith("cm"), f"focus stays in the editor ({state['focus']})")
    requests = ab("network", "requests", "--filter", "api/check")
    check("No requests captured" in requests, "zero /api/check requests on editor click")

    print("== caret movement drives the context panel ==")
    reset_page()
    ab("click", ".cm-line:nth-child(5)")  # "Obtain k ..." -> step index 2
    time.sleep(0.5)
    check(probe()["selected"] == "2", f"caret on line 5 -> index {probe()['selected']}")
    ab("press", "ArrowDown")
    time.sleep(0.4)
    check(probe()["selected"] == "3", "ArrowDown moves the panel to the next statement")
    ab("press", "ArrowUp")
    time.sleep(0.4)
    check(probe()["selected"] == "2", "ArrowUp moves it back")
    check(probe()["focus"].startswith("cm"), "focus stays in the editor throughout")

    # QED on line 11 is not an audited statement, so the panel must hold still.
    ab("click", ".cm-line:nth-child(10)")  # last step -> index 7
    time.sleep(0.5)
    check(probe()["selected"] == "7", f"caret on line 10 -> index {probe()['selected']}")
    ab("press", "ArrowDown")
    time.sleep(0.4)
    check(probe()["selected"] == "7", "an unaudited line (QED) leaves the selection alone")

    print("== auditor keyboard navigation ==")
    ab("click", ".report-group button.step:nth-of-type(1)")
    time.sleep(0.5)
    check(probe()["selected"] == "0", "click step 1 selects index 0")
    ab("press", "ArrowDown")
    time.sleep(0.4)
    state = probe()
    check(state["selected"] == "1", f"ArrowDown -> index {state['selected']}")
    check("Assume" in state["ctxTitle"], f"inspector follows arrows ({state['ctxTitle']!r})")
    ab("press", "End")
    time.sleep(0.4)
    check(probe()["selected"] == "7", "End jumps to the last step")
    ab("press", "Home")
    time.sleep(0.4)
    check(probe()["selected"] == "0", "Home jumps to the first step")
    check(probe()["focus"] == "step", "focus stays on the auditor row")

    print("== the auditor's arrow keys must not hijack the editor ==")
    reset_page()
    ab("click", ".cm-line:nth-child(5)")
    time.sleep(0.5)
    start = probe()
    for _ in range(3):
        ab("press", "ArrowDown")
        time.sleep(0.35)
    after = probe()
    check(after["focus"] == "cm-content", f"focus is in the editor ({after['focus']})")
    # The auditor's listener is scoped to its own pane, so the editor must still
    # receive the key and move the caret.  (That the panel then follows the
    # caret is intended, and is covered by the caret section above.)
    check(
        after["activeLine"] != start["activeLine"],
        f"the editor still receives them (line {start['activeLine']} -> {after['activeLine']})",
    )

    print("== strict domain checking toggle ==")
    load_example("unguarded-division")
    state = probe()
    check(
        state["verdict"] == "VALID (with domain warnings)",
        f"lenient verdict is {state['verdict']}",
    )
    ab("check", "#strict")
    state = settle()
    check(state["verdict"] == "INVALID", f"strict verdict is {state['verdict']}")
    check("strict domains" in (state["meta"] or ""), "meta line reflects strict mode")
    ab("uncheck", "#strict")

    print("== autosave survives a reload ==")
    state = reset_page()
    check(
        state["verdict"] == "VALID" and state["steps"] == 8,
        f"reset lands on the starting example ({state['verdict']}, {state['steps']} steps)",
    )

    append_to_line(11, " -- AUTOSAVE")
    state = settle()
    check(
        state["lines"][10] == "QED -- AUTOSAVE",
        f"the edit landed ({state['lines'][10]!r})",
    )

    ab("reload")
    state = settle()
    check(
        state["lines"][10] == "QED -- AUTOSAVE",
        "the buffer is restored after a reload, without re-picking an example",
    )
    check("#p=" in (state["hash"] or ""), f"the URL carries the proof ({state['hash'][:22]}…)")

    print("== a permalink reproduces the proof in a clean browser ==")
    # Vary the query, or this is a fragment-only change and would not reload.
    shared = f"{BASE}/?r={time.time_ns()}{state['hash']}"
    state = reset_page()
    check("-- AUTOSAVE" not in state["lines"][10], "the reset really did discard the edit")
    ab("open", shared)
    state = settle()
    check(
        state["lines"][10] == "QED -- AUTOSAVE",
        "opening the fragment restores the exact proof",
    )

    print("== workspace panel: snapshots, reset, timeline ==")
    reset_page()
    ab("click", "#history-toggle")
    time.sleep(0.4)
    check(js("!document.querySelector('#history-panel').hidden"), "the workspace panel opens")

    # Earlier sections load examples, and loading an example snapshots the buffer
    # it replaced, so the snapshot list does not start empty.  Clear it rather
    # than assert against whatever the previous sections happened to leave.
    ab("click", "#clear-history")
    time.sleep(0.3)
    check(js("document.querySelectorAll('#snapshots .snapshot').length") == 0, "snapshots can be cleared")

    # The panel overlays the top of the editor, so the edit goes through a line
    # at the bottom -- clicking a covered line would just hit the panel.
    before = timeline_checks()
    append_to_line(11, " -- SNAP")
    state = settle()
    after = timeline_checks()
    check(state["lines"][10].endswith("-- SNAP"), f"the edit landed ({state['lines'][10]!r})")
    check(after > before, f"the timeline records the check ({before} -> {after})")

    ab("click", "#snapshot-now")
    time.sleep(0.4)
    check(
        js("document.querySelectorAll('#snapshots .snapshot').length") == 1,
        "'Snapshot now' adds one snapshot",
    )

    ab("click", "#reset-workspace")
    state = settle()
    check("-- SNAP" not in state["lines"][10], f"reset drops the edit ({state['lines'][10]!r})")
    check(
        js("document.querySelectorAll('#snapshots .snapshot').length") == 2,
        "reset snapshots the buffer it replaced, so nothing is lost",
    )

    # Newest first, so the hand-made snapshot is at index 1.
    js(
        "document.querySelectorAll('#snapshots .snapshot')[1]"
        ".querySelector('button.mini').click(); 'clicked'"
    )
    state = settle()
    check(
        state["lines"][10].endswith("-- SNAP"),
        f"restoring a snapshot brings its buffer back ({state['lines'][10]!r})",
    )

    ab("click", "#clear-history")
    time.sleep(0.4)
    state = probe()
    check(js("document.querySelectorAll('#timeline .tl-bar').length") == 0, "clearing empties the timeline")
    check(js("document.querySelectorAll('#snapshots .snapshot').length") == 0, "clearing empties the snapshots")
    check("-- SNAP" in state["lines"][10], "clearing leaves the proof itself alone")

    print("== download and drag-and-drop ==")
    buffer_head = probe()["lines"][0]
    target = Path("/tmp/aether-verify-download.aether")
    target.unlink(missing_ok=True)
    ab("download", "#download-proof", str(target))
    time.sleep(0.6)
    check(target.exists(), "the download button writes a file")
    if target.exists():
        text = target.read_text()
        check(text.lstrip().startswith("Theorem"), f"the file is the proof ({text[:20]!r}…)")
        check(buffer_head in text, "the download contains the current buffer, not an example")

    js(
        "(() => { const file = new File(['Let z : Real\\nStep: z = z\\n'], 'dropped.aether',"
        " { type: 'text/plain' }); const dt = new DataTransfer(); dt.items.add(file);"
        " window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true,"
        " cancelable: true })); return 'dropped'; })()"
    )
    state = settle()
    check("dropped.aether" in (state["toast"] or ""), f"dropping a file reports it ({state['toast']!r})")
    check(state["lines"][0] == "Let z : Real", f"the dropped proof is loaded ({state['lines'][0]!r})")
    check(state["verdict"] == "VALID", f"the dropped proof is checked ({state['verdict']})")

    print("== the strict setting is remembered ==")
    reset_page()
    ab("check", "#strict")
    time.sleep(0.6)
    ab("reload")
    settle()
    check(
        js("document.querySelector('#strict').checked") is True,
        "strict domain checking survives a reload",
    )

    print("== light / dark theme ==")
    ab("reload")
    settle()
    before_theme = js("document.documentElement.dataset.theme")
    before_bg = js("getComputedStyle(document.querySelector('.cm-editor')).backgroundColor")
    check(before_theme in ("light", "dark"), f"a theme is resolved on boot ({before_theme})")

    ab("click", "#theme-toggle")
    time.sleep(0.6)
    after_theme = js("document.documentElement.dataset.theme")
    after_bg = js("getComputedStyle(document.querySelector('.cm-editor')).backgroundColor")
    check(
        after_theme != before_theme,
        f"toggle switches the theme ({before_theme} -> {after_theme})",
    )
    check(
        before_bg != after_bg,
        f"the editor surface repaints, not just the chrome ({before_bg} -> {after_bg})",
    )

    ab("reload")
    settle()
    check(
        js("document.documentElement.dataset.theme") == after_theme,
        "the theme choice survives a reload",
    )


def main() -> int:
    server = subprocess.Popen(
        [sys.executable, "-m", "ui", "--port", str(PORT)],
        cwd=str(PROJECT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(80):
            try:
                urllib.request.urlopen(f"{BASE}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.25)
        else:
            print("server did not start")
            return 1

        global STARTING_SOURCE
        with urllib.request.urlopen(f"{BASE}/api/examples", timeout=5) as resp:
            examples = json.loads(resp.read())
        STARTING_SOURCE = next(e for e in examples if e["id"] == "even-square")["source"]

        run_checks()
    finally:
        ab("close")
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all browser checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
