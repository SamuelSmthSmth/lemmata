"""Real-browser regression tests for the Aether UI.

Drives a headless Chrome through the `agent-browser` CLI and asserts the
behaviours that are awkward to catch any other way: editor key bindings, the
debounced round-trip, the client-side step inspector, auditor keyboard
navigation, and the app around them -- the workspace of many proofs kept in
IndexedDB, imports between them, the Library and its exercises, the palette,
settings, and a workspace .zip that survives a round trip.

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
  toast: (() => { const items = document.querySelectorAll('#toast wa-toast-item');
    return items.length ? items[items.length - 1].textContent : null; })(),
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
EXAMPLES: dict[str, str] = {}


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
    """Load the starting example in a guaranteed-fresh page.

    Waits for the editor to hold that source as well as for a verdict: boot is
    asynchronous (storage, then the Library, then the file), and a click that
    lands before the editor is filled hits a line that is about to be replaced.
    """
    ab("open", permalink(STARTING_SOURCE))
    expected = STARTING_SOURCE.rstrip("\n").split("\n")
    deadline = time.time() + 10
    state = settle()
    while time.time() < deadline and state["lines"][: len(expected)] != expected:
        time.sleep(0.2)
        state = settle()
    time.sleep(0.3)
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


def click_step(selector: str) -> None:
    """Click an auditor row, bringing it into view first.

    The auditor is its own scroll container, and selecting a later step scrolls
    it -- which can leave an earlier row positioned above the viewport, at a
    negative y.  A click at those coordinates hits nothing and, because
    agent-browser reports success either way, fails silently.  Scrolling first
    is also what a person does, since the row has to be visible to be clicked.
    """
    ab("scrollintoview", selector)
    ab("click", selector)


def load_example(example_id: str) -> dict:
    """Open a bundled example as its own proof.

    The examples now live in the Library rather than a menu; a permalink is
    the shortest path to one, and it reuses the workspace file when the same
    source is already open.
    """
    ab("open", permalink(EXAMPLES[example_id]))
    return settle()


def wipe() -> None:
    """Forget every proof, snapshot and preference this origin has stored.

    Done from a same-origin page that is not the app, so no open connection
    can block the IndexedDB delete.
    """
    ab("open", f"{BASE}/api/health")
    js(
        "(() => { window.__wiped = false; localStorage.clear();"
        " const r = indexedDB.deleteDatabase('aether');"
        " r.onsuccess = r.onerror = r.onblocked = () => { window.__wiped = true; }; return 'ok'; })()"
    )
    deadline = time.time() + 5
    while time.time() < deadline and js("window.__wiped") is not True:
        time.sleep(0.1)


def fresh() -> dict:
    """A first visit: empty storage, the app's own starting point."""
    wipe()
    ab("open", BASE)
    return settle()


def saved() -> None:
    """Let the debounced autosave (400ms) land before reloading."""
    time.sleep(0.8)


def files_in_workspace() -> list[str]:
    return js("JSON.stringify([...document.querySelectorAll('#explorer .tree-row--file .tree-label')].map(e => e.textContent))")


def drop_file(name: str, text: str) -> None:
    js(
        "(() => { const file = new File([" + json.dumps(text) + "], " + json.dumps(name) + ","
        " { type: 'text/plain' }); const dt = new DataTransfer(); dt.items.add(file);"
        " window.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true,"
        " cancelable: true })); return 'dropped'; })()"
    )


def set_strict(on: bool) -> None:
    """Flip the strict-domain switch through its own control.

    #strict is a <wa-switch>: the host is a custom element and the real
    <input role="switch"> lives in its shadow root.  The clickable area is only
    the label line, and the host's vertical centre falls in the gap between the
    label and the hint, so clicking the host by coordinates hits nothing.
    Activating the shadow <label> is the same path a user's click takes.  The
    label also holds the two-line label + hint, so it is wider than the
    visible track -- coordinates are simply the wrong tool here.
    """
    js(
        "(() => { const s = document.querySelector('#strict');"
        f" if (s.checked !== {str(on).lower()}) s.shadowRoot.querySelector('label').click();"
        " return s.checked; })()"
    )


def run_checks() -> None:
    print("== open the page ==")
    state = fresh()
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
    click_step(".report-group button.step:nth-of-type(3)")
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
    click_step(".report-group button.step:nth-of-type(1)")
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
    set_strict(True)
    state = settle()
    check(state["verdict"] == "INVALID", f"strict verdict is {state['verdict']}")
    check("strict domains" in (state["meta"] or ""), "meta line reflects strict mode")
    set_strict(False)

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
    saved()

    ab("open", BASE)
    restored = settle()
    check(
        restored["lines"][10] == "QED -- AUTOSAVE",
        "the workspace reopens the edited proof with no link at all (IndexedDB)",
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
    wipe()
    ab("open", shared)
    state = settle()
    check(
        state["lines"][10] == "QED -- AUTOSAVE",
        "opening the fragment restores the exact proof",
    )

    print("== history: snapshots, reset, timeline ==")
    wipe()
    reset_page()
    ab("click", "#desk-tab-history")
    time.sleep(0.4)
    check(js("!document.querySelector('#desk-history').hidden") is True, "the History tab opens in the reading pane")

    ab("click", "#clear-history")
    time.sleep(0.3)
    check(js("document.querySelectorAll('#snapshots .snapshot').length") == 0, "snapshots can be cleared")

    before = timeline_checks()
    append_to_line(11, " -- SNAP")
    state = settle()
    time.sleep(0.3)
    after = timeline_checks()
    check(state["lines"][10].endswith("-- SNAP"), f"the edit landed ({state['lines'][10]!r})")
    check(after > before, f"the timeline records the check ({before} -> {after})")

    ab("click", "#snapshot-now")
    time.sleep(0.5)
    check(
        js("document.querySelectorAll('#snapshots .snapshot').length") == 1,
        "'Snapshot now' adds one snapshot",
    )

    ab("click", "#reset-workspace")
    state = settle()
    time.sleep(0.4)
    check("-- SNAP" not in state["lines"][10], f"reset drops the edit ({state['lines'][10]!r})")
    check(
        js("document.querySelectorAll('#snapshots .snapshot').length") == 2,
        "reset snapshots the buffer it replaced, so nothing is lost",
    )

    # Newest first, so the hand-made snapshot is at index 1.
    js(
        "document.querySelectorAll('#snapshots .snapshot')[1]"
        ".querySelector('.text-button').click(); 'clicked'"
    )
    state = settle()
    check(
        state["lines"][10].endswith("-- SNAP"),
        f"restoring a snapshot brings its buffer back ({state['lines'][10]!r})",
    )

    ab("click", "#clear-history")
    time.sleep(0.5)
    state = probe()
    check(js("document.querySelectorAll('#timeline .tl-bar').length") == 0, "clearing empties the timeline")
    check(js("document.querySelectorAll('#snapshots .snapshot').length") == 0, "clearing empties the snapshots")
    check("-- SNAP" in state["lines"][10], "clearing leaves the proof itself alone")
    ab("click", "#desk-tab-files")

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

    drop_file("dropped.aether", "Let z : Real\nStep: z = z\n")
    time.sleep(0.4)
    state = settle()
    check("dropped.aether" in (state["toast"] or ""), f"dropping a file reports it ({state['toast']!r})")
    check(state["lines"][0] == "Let z : Real", f"the dropped proof is opened ({state['lines'][0]!r})")
    check("dropped.aether" in files_in_workspace(), "and kept as a file of its own in the workspace")
    check(state["verdict"] == "VALID", f"the dropped proof is checked ({state['verdict']})")

    print("== the strict setting is remembered ==")
    reset_page()
    set_strict(True)
    settle()
    saved()
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

    panel_checks()
    syntax_checks()
    workspace_checks()
    import_checks()
    migration_checks()
    lint_and_template_checks()
    palette_checks()
    library_checks()
    settings_checks()
    zip_checks()


PANEL_PROBE = """(() => {
  const name = (p) => p.className.split(' ').find(c => c.startsWith('pane--')).slice(6);
  const grid = document.querySelector('main.layout');
  const panes = [...grid.querySelectorAll('.pane')];
  return JSON.stringify({
    layout: grid.dataset.layout,
    order: panes.map(name),
    slotOf: Object.fromEntries(panes.map(p => [name(p), p.dataset.slot])),
    slots: Object.fromEntries(panes.map(p => [p.dataset.slot, name(p)])),
    grips: grid.querySelectorAll('.pane-grip').length,
    areas: getComputedStyle(grid).gridTemplateAreas,
    focused: (document.activeElement.className || '').split(' ')[0],
    pressed: document.querySelector('#layout-toggle').getAttribute('aria-expanded'),
  });
})()"""

SYNTAX_PROBE = """(() => {
  const hues = new Set();
  for (const span of document.querySelectorAll('.cm-line span')) {
    if (!span.textContent.trim()) continue;
    hues.add(getComputedStyle(span).color);
  }
  return JSON.stringify({
    scheme: document.documentElement.dataset.syntax,
    hues: [...hues].sort(),
    pressed: document.querySelector('#syntax-toggle').getAttribute('aria-pressed'),
  });
})()"""


def panel_checks() -> None:
    print("== panel arrangement: presets, keyboard, and it is remembered ==")
    js("localStorage.removeItem('aether:layout')")
    ab("open", permalink(STARTING_SOURCE))
    settle()

    start = js(PANEL_PROBE)
    check(start["layout"] == "split", f"the default arrangement is Split ({start['layout']})")
    check(
        start["order"] == ["editor", "audit", "context"],
        f"the panes start in reading order ({start['order']})",
    )
    check(
        start["slots"] == {"a": "editor", "b": "audit", "c": "context"},
        f"slot a is the editor ({start['slots']})",
    )
    check(start["grips"] == 3, f"every pane carries a grip ({start['grips']})")

    ab("click", "#layout-toggle")
    time.sleep(0.4)
    check(js(PANEL_PROBE)["pressed"] == "true", "the toolbar button reports the menu is open")
    ab("click", "#layout-options [data-arrangement='focus']")
    time.sleep(0.4)

    split = js(PANEL_PROBE)
    check(split["layout"] == "focus", f"the menu switches to Focus ({split['layout']})")
    check(split["areas"] not in ("", "none"), "Focus lays the grid out with real template areas")
    check(
        split["order"] == ["editor", "audit", "context"],
        "choosing an arrangement leaves the pane order alone",
    )

    # Keyboard: focus a grip, then step that pane along the order.  A drag does
    # the same swap, but driving HTML5 drag-and-drop through CDP is unreliable;
    # the swap itself is unit-tested in verify_frontend.mjs.
    ab("click", ".pane--editor .pane-grip")
    check(js(PANEL_PROBE)["focused"] == "pane-grip", "a grip can take focus")
    ab("press", "ArrowRight")
    time.sleep(0.4)
    moved = js(PANEL_PROBE)
    check(
        moved["order"] == ["audit", "editor", "context"],
        f"an arrow key moves the focused pane one slot ({moved['order']})",
    )
    check(js(PANEL_PROBE)["focused"] == "pane-grip", "focus stays on the grip, so a key can be pressed twice")

    for _ in range(2):
        ab("press", "ArrowRight")
        time.sleep(0.3)
    clamped = js(PANEL_PROBE)
    check(
        clamped["order"] == ["audit", "context", "editor"],
        f"movement is clamped at the end, not wrapped ({clamped['order']})",
    )

    ab("reload")
    settle()
    remembered = js(PANEL_PROBE)
    check(remembered["layout"] == "focus", "the arrangement survives a reload")
    check(
        remembered["order"] == ["audit", "context", "editor"],
        f"so does the pane order ({remembered['order']})",
    )
    check(
        remembered["slots"] == {"a": "audit", "b": "context", "c": "editor"},
        "the panes are reordered in the DOM, so tab order follows the screen",
    )

    js("localStorage.removeItem('aether:layout')")


def syntax_checks() -> None:
    print("== syntax colours: mono, vivid, and it is remembered ==")
    js("localStorage.removeItem('aether-syntax')")
    ab("open", permalink(STARTING_SOURCE))
    settle()

    mono = js(SYNTAX_PROBE)
    check(mono["scheme"] == "mono", f"the editor starts near-monochrome ({mono['scheme']})")
    check(mono["pressed"] == "false", f"the button says which scheme it is in ({mono['pressed']})")

    ab("click", "#syntax-toggle")
    time.sleep(0.5)
    vivid = js(SYNTAX_PROBE)
    check(vivid["scheme"] == "vivid", "the toolbar button switches to vivid")
    check(vivid["pressed"] == "true", "the button reports the new scheme")
    check(
        len(vivid["hues"]) > len(mono["hues"]),
        f"vivid colours the tokens apart ({len(mono['hues'])} hues -> {len(vivid['hues'])})",
    )

    ab("reload")
    settle()
    check(
        js(SYNTAX_PROBE)["scheme"] == "vivid",
        "the scheme survives a reload",
    )
    check(
        len(js(SYNTAX_PROBE)["hues"]) == len(vivid["hues"]),
        "and the editor is re-coloured on boot, not left plain",
    )

    js("localStorage.removeItem('aether-syntax')")


LEMMA = """\
Theorem: "Even times even is even"
Claim: forall a : Int, Even(a) => Even(a * 2)
Proof:
    Given a : Int
    Assume h: Even(a)
    Obtain k : Int such that a = 2 * k from h
    Step: a * 2 = 2 * (2 * k)
    Hence Even(a * 2)
QED
"""

USES_LEMMA = """\
import "lemmas.aether"

Theorem: "Uses the lemma"
Proof:
    Given n : Int
    Assume h: Even(n)
    Therefore Even(n * 2)
QED
"""

WORKSPACE_PROBE = """JSON.stringify({
  tabs: [...document.querySelectorAll('#tabs .tab .tab-label')].map(e => e.textContent),
  active: (document.querySelector('#tabs .tab.is-active .tab-label')||{}).textContent ?? null,
  path: document.querySelector('#editor-path').textContent,
  files: [...document.querySelectorAll('#explorer .tree-row--file .tree-label')].map(e => e.textContent),
  folders: [...document.querySelectorAll('#explorer .tree-row--folder .tree-label')].map(e => e.textContent),
})"""


def workspace() -> dict:
    return js(WORKSPACE_PROBE)


def workspace_checks() -> None:
    print("== the workspace: many proofs, tabs, rename, delete with undo ==")
    fresh()
    # A first visit shows the starting example's notes; the file tools are
    # on the Files tab.
    ab("click", "#desk-tab-files")
    start = workspace()
    check(start["path"] == "Examples/Even square theorem.aether", f"a first visit opens the starting example ({start['path']!r})")
    check(start["files"] == ["Even square theorem.aether"], f"and the explorer lists it ({start['files']})")

    ab("click", "#file-new")
    state = settle()
    after = workspace()
    check(len(after["tabs"]) == 2, f"'New proof' opens a second tab ({after['tabs']})")
    check(after["path"] == "Examples/Untitled.aether", f"next to the open proof ({after['path']!r})")
    check(state["lines"][0].startswith("Theorem"), "starting from a proof skeleton")

    ab("focus", "#explorer .tree-row.is-active")
    ab("press", "F2")
    time.sleep(0.3)
    check(js("document.activeElement.classList.contains('tree-rename')") is True, "F2 on a file starts renaming it in place")
    ab("fill", ".tree-rename", "week1")
    ab("press", "Enter")
    time.sleep(0.5)
    renamed = workspace()
    check(renamed["path"] == "Examples/week1.aether", f"the extension is kept ({renamed['path']!r})")
    check("week1" in renamed["tabs"], f"the tab follows the rename ({renamed['tabs']})")

    ab("click", "#folder-new")
    time.sleep(0.4)
    ab("fill", ".tree-rename", "Sheets")
    ab("press", "Enter")
    time.sleep(0.4)
    check("Sheets" in workspace()["folders"], f"a folder can be made and named ({workspace()['folders']})")

    ab("focus", "#explorer .tree-row.is-active")
    ab("press", "Delete")
    time.sleep(0.5)
    gone = workspace()
    check("week1.aether" not in gone["files"], f"Delete removes the proof ({gone['files']})")
    check(js("!!document.querySelector('#toast .toast-action')") is True, "and offers an Undo")
    js("document.querySelector('#toast .toast-action').click(); 'undone'")
    time.sleep(0.6)
    check("week1.aether" in workspace()["files"], "Undo brings it back")

    saved()
    ab("reload")
    settle()
    kept = workspace()
    check(
        sorted(kept["files"]) == ["Even square theorem.aether", "week1.aether"] and "Sheets" in kept["folders"],
        f"files and folders survive a reload ({kept['files']}, {kept['folders']})",
    )

    ab("click", "#tabs .tab.is-active .tab-close")
    time.sleep(0.4)
    check(len(workspace()["tabs"]) == 1, "closing a tab closes the tab, not the file")
    check("week1.aether" in workspace()["files"], "the file stays in the explorer")


def import_checks() -> None:
    print("== imports between proofs in the workspace ==")
    fresh()
    drop_file("lemmas.aether", LEMMA)
    time.sleep(0.5)
    settle()
    drop_file("uses.aether", USES_LEMMA)
    time.sleep(0.5)
    state = settle()
    check(state["verdict"] == "VALID", f"a proof importing another workspace file checks ({state['verdict']})")
    check("Imported 'lemmas.aether'" in js("document.querySelector('#audit').textContent"), "the auditor names the import")

    drop_file("orphan.aether", USES_LEMMA.replace("lemmas.aether", "missing.aether"))
    time.sleep(0.5)
    settle()
    audit = js("document.querySelector('#audit').textContent")
    check("Import not found" in audit and "missing.aether" in audit, "a missing import is named, not silently ignored")


def migration_checks() -> None:
    print("== the old single-buffer workspace migrates ==")
    wipe()
    legacy = {
        "source": "Let q : Real\nStep: q = q\n",
        "strict": False,
        "snapshots": [{"name": "Old snapshot", "ts": 1700000000000, "source": "Let q : Real\n", "strict": False}],
    }
    js(f"localStorage.setItem('aether:workspace', {json.dumps(json.dumps(legacy))}); 'set'")
    ab("open", BASE)
    state = settle()
    check(workspace()["files"] == ["My proof.aether"], f"the old buffer becomes a file ({workspace()['files']})")
    check(state["lines"][0] == "Let q : Real", "with its source")
    ab("click", "#desk-tab-history")
    time.sleep(0.5)
    check(js("document.querySelectorAll('#snapshots .snapshot').length") == 1, "and its snapshots")
    ab("click", "#desk-tab-files")


def lint_and_template_checks() -> None:
    print("== diagnostics in the editor, problem keys, templates ==")
    ab("open", permalink("Let x : Real\nStep: (x + 1)^2 = x^2 + 1\n"))
    settle()
    time.sleep(0.3)
    check(js("document.querySelectorAll('.cm-lint-marker-error').length") == 1, "a failing step gets a gutter mark")
    check(js("document.querySelectorAll('.cm-lintRange-error').length") >= 1, "and its source range is underlined")
    check(
        "first on line 2" in js("document.querySelector('#status-problem').textContent"),
        "the status bar points to the first problem",
    )
    ab("click", ".cm-line:nth-child(1)")
    ab("press", "F8")
    time.sleep(0.3)
    check(probe()["activeLine"] == "2", f"F8 moves to the next problem (line {probe()['activeLine']})")

    ab("click", "#file-new")
    settle()
    before = len(probe()["lines"])
    ab("click", "#templates-menu > button")
    time.sleep(0.4)
    js("[...document.querySelectorAll('#templates-menu wa-dropdown-item')].find(i => i.value === 'induction').click(); 'ok'")
    time.sleep(0.5)
    lines = probe()["lines"]
    check(len(lines) > before, f"a template inserts a whole proof shape ({before} -> {len(lines)} lines)")


def palette_checks() -> None:
    print("== the command palette ==")
    reset_page()
    ab("click", ".cm-line:nth-child(1)")
    ab("press", "Control+k")
    time.sleep(0.3)
    check(js("document.querySelector('#palette').open") is True, "Ctrl+K opens the palette")
    ab("keyboard", "type", "go to library")
    time.sleep(0.2)
    ab("press", "Enter")
    time.sleep(0.5)
    check(js("document.body.dataset.view") == "library", "running a command closes it and acts")

    ab("press", "Control+k")
    time.sleep(0.3)
    ab("keyboard", "type", "2.18")
    time.sleep(0.2)
    first = js("(document.querySelector('#palette-list .palette-row.is-selected .palette-label')||{}).textContent ?? ''")
    check(first.startswith("Example 2.18") or "2.18" in first, f"a reference finds the Library entry ({first!r})")
    ab("press", "Enter")
    settle()
    time.sleep(0.4)
    check(js("document.body.dataset.view") == "workspace", "opening an entry returns to the workspace")
    check("2.18" in workspace()["path"], f"as a copy of the entry ({workspace()['path']!r})")
    check("2.18" in js("document.querySelector('#notes').textContent"), "with the entry beside it in Notes")
    ab("press", "Escape")


def library_checks() -> None:
    print("== the Library: search, open beside, spot the error ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    time.sleep(0.4)
    check(js("new URLSearchParams(location.search).get('view')") == "library", "the view is in the URL")
    js("(() => { const s = document.querySelector('#library-search'); s.value = 'Lagrange'; s.dispatchEvent(new Event('input')); return 1; })()")
    time.sleep(0.3)
    titles = js("JSON.stringify([...document.querySelectorAll('.entry-title')].map(e => e.textContent))")
    check(bool(titles) and all("Lagrange" in t or "lagrange" in t.lower() for t in titles) or any("Lagrange" in t for t in titles),
          f"search looks across every pack ({titles[:3]})")
    js("(() => { const s = document.querySelector('#library-search'); s.value = ''; s.dispatchEvent(new Event('input')); return 1; })()")

    ab("click", "#library-filters [data-filter='trap']")
    time.sleep(0.3)
    kinds = js("document.querySelectorAll('.entry').length === document.querySelectorAll('.entry--trap').length")
    check(kinds is True, "the Traps filter shows only traps")
    ab("click", ".entry--trap .entry-head")
    time.sleep(0.3)
    ab("click", ".entry.is-open .entry-actions .text-button--primary")
    state = settle()
    time.sleep(0.3)
    check(state["verdict"] == "Exercise", f"a trap opens as an exercise ({state['verdict']})")
    check(js("document.body.dataset.exercise") == "hidden", "with the answer hidden")
    visible_meta = js("[...document.querySelectorAll('.step-meta')].filter(e => e.offsetParent).length")
    check(visible_meta == 0, f"no step verdicts are visible ({visible_meta})")
    check(js("document.querySelectorAll('.cm-lint-marker').length") == 0, "and no gutter marks give it away")

    js("document.querySelector('.note-pick .text-button:not(.text-button--primary)').click(); 'shown'")
    time.sleep(0.6)
    check(js("document.body.dataset.exercise") == "revealed", "'Show the answer' reveals it")
    check(js("!!document.querySelector('.note-verdict')") is True, "and the Notes say which line fails")
    check(js("document.querySelector('#verdict').textContent") == "INVALID", "the real verdict comes back")


def settings_checks() -> None:
    print("== settings apply live and persist ==")
    fresh()
    ab("click", ".rail-button[data-view='settings']")
    time.sleep(0.4)
    ab("click", "#setting-editor-size-label + .filters [data-value='15'], .filters[aria-labelledby='setting-editor-size-label'] [data-value='15']")
    time.sleep(0.3)
    size = js("document.documentElement.style.getPropertyValue('--editor-size')")
    check(size == "15px", f"the editor size applies at once ({size!r})")
    js("document.querySelector('#setting-wrap').shadowRoot.querySelector('label').click(); 'ok'")
    time.sleep(0.3)
    ab("reload")
    settle()
    check(js("document.body.dataset.view") == "settings", "a reload stays on the same view")
    check(js("document.documentElement.style.getPropertyValue('--editor-size')") == "15px", "the editor size survives a reload")
    ab("click", ".rail-button[data-view='workspace']")
    time.sleep(0.4)
    check(js("!!document.querySelector('.cm-editor .cm-lineWrapping')") is True, "line wrapping survives too")


def zip_checks() -> None:
    print("== the workspace as a .zip, out and back in ==")
    import zipfile

    fresh()
    drop_file("lemmas.aether", LEMMA)
    time.sleep(0.5)
    settle()
    ab("click", "#desk-tab-files")
    target = Path("/tmp/aether-verify-workspace.zip")
    target.unlink(missing_ok=True)
    ab("download", "#workspace-export", str(target))
    time.sleep(0.8)
    check(target.exists(), "the export button writes a .zip")
    if not target.exists():
        return
    with zipfile.ZipFile(target) as archive:
        names = sorted(archive.namelist())
        lemma = archive.read("lemmas.aether").decode() if "lemmas.aether" in names else ""
    check(names == ["Examples/Even square theorem.aether", "lemmas.aether"], f"it holds every proof, with folders ({names})")
    check(lemma == LEMMA, "byte for byte")

    wipe()
    ab("open", BASE)
    settle()
    ab("click", "#desk-tab-files")
    ab("upload", "#workspace-import-input", str(target))
    time.sleep(1.0)
    settle()
    files = workspace()["files"]
    check("lemmas.aether" in files, f"importing it restores the proofs ({files})")
    check(len(files) == 3, "and a clash with an existing file is renamed, not overwritten")


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
        EXAMPLES.update({e["id"]: e["source"] for e in examples})
        STARTING_SOURCE = EXAMPLES["even-square"]

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
