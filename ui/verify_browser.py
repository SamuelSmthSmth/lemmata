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


# --static runs a subset against the static build (dist/, ui/build_static.py),
# where the checker runs in the browser and there is no /api at all.
STATIC = "--static" in sys.argv
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


def settle(timeout: float | None = None) -> dict:
    """Wait until the verdict describes the current buffer again.

    Both conditions matter.  "Checking…" covers an in-flight request, and the
    `stale` flag covers the debounce window before it -- without that second
    check, an edit would be read against the *previous* buffer's verdict,
    which looks exactly like a re-check that did not happen.
    """
    # In the static build a page load starts the checker afresh (from cache).
    deadline = time.time() + (timeout or (60.0 if STATIC else 12.0))
    state = probe()
    while time.time() < deadline and (
        state["verdict"] in ("Checking…", "Loading…", "Ready", None) or state["stale"]
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
    ab("open", f"{BASE}{'/static/data/site.json' if STATIC else '/api/health'}")
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
    hint_and_citation_checks()
    lean_checks()
    palette_checks()
    library_checks()
    pack_checks()
    pack_author_checks()
    settings_checks()
    boot_checks()
    working_checks()
    graph_checks()
    level_checks()
    visual_checks()
    zip_checks()


PANEL_PROBE = """(() => {
  const name = (p) => p.className.split(' ').find(c => c.startsWith('pane--')).slice(6);
  const grid = document.querySelector('.layout');
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

    # A tab holds no second control (it would be a nested interactive), so
    # from the keyboard Delete closes the focused tab.
    ab("focus", "#tabs .tab.is-active")
    ab("press", "Delete")
    time.sleep(0.4)
    check(len(workspace()["tabs"]) == 0, "Delete on a focused tab closes it")
    check(len(workspace()["files"]) == 2, "and keeps its file")


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


def lean_checks() -> None:
    print("== Show in Lean: the proof beside its skeleton ==")
    ab("open", permalink("Let x : Real\nAssume x > 2\nStep: x^2 > 4\nStep: (x + 1)^2 = x^2 + 1"))
    settle()
    js("(document.getElementById('show-lean').click(), 'ok')")
    for _ in range(80):
        if js("document.querySelectorAll('#lean-rows .lean-row').length") > 0:
            break
        time.sleep(0.25)
    rows = js("[...document.querySelectorAll('#lean-rows .lean-row')].map(r => [r.querySelector('.lean-src .lean-n')?.textContent ?? '', r.querySelector('.lean-out').textContent, r.className])")
    check(any(src == "1" and "intro x" in out for src, out, _ in rows), "the declaration's row holds its intro")
    check(any(src == "4" and "is-invalid" in cls and "did not check" in out for src, out, cls in rows), "the failing step keeps its rail and says so")
    check(not js("document.getElementById('copy-lean').disabled"), "the actions wake once there is Lean")
    url = js("(() => { let u = ''; const o = window.open; window.open = (h) => { u = h; return null; }; document.getElementById('open-lean').click(); window.open = o; return u; })()")
    check(url.startswith("https://live.lean-lang.org/#code=import%20Mathlib"), "Open in Lean's web editor carries the code")
    js("(document.getElementById('lean-dialog').open = false, 'ok')")
    time.sleep(0.3)


def hint_and_citation_checks() -> None:
    print("== hints: a fix applies, re-checks, and undoes ==")
    ab("open", permalink("Let x : Real\nStep: (x^2 - 1) / (x - 1) = x + 1"))
    state = settle()
    check(state["verdict"] == "VALID (with domain warnings)", f"an unguarded division warns ({state['verdict']})")
    check("which nothing before it guarantees" in js("document.querySelector('#audit').textContent"), "the auditor says what the step needs")
    js("(document.querySelector('.step.step--warning').click(), 'ok')")
    time.sleep(0.3)
    fix = js("[...document.querySelectorAll('.ctx-hint .text-button--primary')].map(b => b.textContent).join('|')")
    check(fix == "Add Assume x - 1 \u2260 0", f"Context & state offers the fix ({fix!r})")
    js("(document.querySelector('.ctx-hint .text-button--primary').click(), 'ok')")
    state = settle()
    check(state["lines"][:2] == ["Let x : Real", "Assume x - 1 != 0"], f"the fix inserts the assumption ({state['lines'][:3]})")
    check(state["verdict"] == "VALID", f"and the proof re-checks clean ({state['verdict']})")
    ab("click", ".cm-line:nth-child(3)")
    ab("press", "Control+z")
    state = settle()
    check(state["verdict"] == "VALID (with domain warnings)" and len(state["lines"]) == 2, f"Ctrl+Z takes the fix back ({state['verdict']}, {len(state['lines'])} lines)")

    print("== citing an installed result by name ==")
    ab("open", permalink("Let x, y : Real\nStep: abs(x - y) <= abs(x) + abs(-y) by MTH2008 Theorem 1.1"))
    state = settle()
    audit = js("document.querySelector('#audit').textContent")
    check(state["verdict"] == "VALID" and "by MTH2008 Theorem 1.1 (the triangle inequality)" in audit, f"a pack theorem is cited with no import ({state['verdict']})")
    js("([...document.querySelectorAll('.step')].find(s => s.textContent.includes('by MTH2008 Theorem 1.1')).click(), 'ok')")
    time.sleep(0.2)
    js("([...document.querySelectorAll('.ctx-cite .text-button')].find(b => b.textContent === 'Open in the Library').click(), 'ok')")
    time.sleep(0.6)
    opened = js("document.querySelector('.entry.is-open .entry-ref')?.textContent ?? ''")
    check(js("document.body.dataset.view") == "library" and opened == "Theorem 1.1", f"Open in the Library lands on the cited entry ({opened!r})")
    ab("open", permalink("Let x, y : Real\nStep: abs(x - y) <= abs(x) + abs(-y) by Theorem 9.9"))
    state = settle()
    check(state["verdict"] == "INVALID" and "No result called 'Theorem 9.9'" in js("document.querySelector('#audit').textContent"), "an unknown citation is reported, not guessed")

    print("== completion offers what may be cited ==")
    ab("open", permalink("Let x, y : Real\nStep: abs(x - y) <= abs(x) + abs(-y)"))
    settle()
    append_to_line(2, " by MTH2008 Th")
    time.sleep(0.8)
    offered = js("[...document.querySelectorAll('.cm-tooltip-autocomplete li')].map(li => li.textContent).join('|')")
    check("MTH2008 Theorem 1.1" in offered, f"typing after 'by' offers installed results ({offered[:120]!r})")
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
    js("document.querySelector('.entry.is-open .entry-actions').scrollIntoView({ block: 'center' }); 'ok'")
    time.sleep(0.2)
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


def rail() -> str:
    return js("document.getElementById('library-packs').innerText")


def toasts() -> str:
    return js("[...document.querySelectorAll('#toast wa-toast-item')].map(t => t.textContent).join(' / ')")


def available_packs() -> list[str]:
    """The packs listed under "Available" in the rail."""
    return js(
        "(() => { const out = []; let after = false; for (const node of document.getElementById('library-packs').children) {"
        " if (node.classList.contains('packs-group')) after = node.textContent === 'Available';"
        " else if (after && node.dataset.pack) out.push(node.dataset.pack); } return JSON.stringify(out); })()"
    )


def pack_action(label: str) -> None:
    js(
        "[...document.querySelectorAll('.pack-actions .text-button')].find(b => b.textContent.startsWith("
        + json.dumps(label) + ")).click(); 'ok'"
    )


def open_pack(name: str) -> None:
    js(f"document.querySelector('.pack-button[data-pack=\"{name}\"]').click(); 'ok'")
    time.sleep(0.3)


def pack_checks() -> None:
    print("== packs: install, uninstall, update, import from them ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    time.sleep(0.5)
    text = rail()
    check(all(label in text for label in ("Worked examples", "MTH2008", "MTH2010", "Notation and traps")), "a first visit installs the bundled packs")
    check("Available" not in text and "AVAILABLE" not in text, "so none are left to install")

    open_pack("core/mth2010")
    pack_action("Uninstall")
    time.sleep(0.5)
    check(available_packs() == ["core/mth2010"], f"an uninstalled pack moves to Available ({available_packs()})")
    check("still in your workspace" in toasts(), "the toast says the copies are kept")
    ab("reload")
    time.sleep(1.5)
    check(available_packs() == ["core/mth2010"], "and a reload does not put it back")

    open_pack("core/mth2010")
    pack_action("Install")
    time.sleep(0.6)
    check(available_packs() == [], "Install puts it back")

    with urllib.request.urlopen(f"{BASE}/api/library", timeout=5) as resp:
        mth2010 = next(p for p in json.loads(resp.read()) if p["name"] == "core/mth2010")
    newer = json.loads(json.dumps(mth2010))
    newer["version"] = "1.1.0"
    newer["entries"][0]["title"] += " (revised)"
    drop_file("core-mth2010.pack.json", json.dumps(newer))
    time.sleep(1.2)
    check("Updated MTH2010 to v1.1.0 — 1 changed" in toasts(), f"dropping a newer .pack.json updates it and says what changed ({toasts()[-90:]!r})")
    check(js("document.querySelector('.pack-meta').textContent").startswith("v1.1.0"), "the pack page shows the new version")
    check("update" not in rail().replace("Update", ""), "an older bundled copy is not offered as an update")

    broken = dict(newer, version="soon")
    drop_file("broken.pack.json", json.dumps(broken))
    time.sleep(1.0)
    check("is not a pack: version" in toasts(), "a bad pack is refused, naming the field")

    drifting = {
        "format": 1, "name": "someone/drift", "version": "1.0.0", "title": "Drift", "summary": "One entry recorded wrongly.",
        "license": "CC-BY-SA-4.0", "chapters": [{"id": "1", "title": "Only"}],
        "entries": [{"id": "sum", "chapter": "1", "ref": "1", "title": "x + x", "kind": "proof", "expected": "INVALID",
                     "source": "Let x : Real\nStep: x + x = 2 * x\n"}],
    }
    drop_file("someone-drift.pack.json", json.dumps(drifting))
    time.sleep(1.0)
    check("Drift" in rail() and "courses" not in json.dumps(js("document.querySelector('.pack-meta').textContent")), "a topic pack with no course code installs")
    pack_action("Check all entries")
    time.sleep(2.5)
    check("no longer give the verdict" in js("(document.querySelector('.pack-check')||{}).textContent ?? ''"), "Check all entries flags an entry that drifted from its recorded verdict")
    check("pack says invalid" in js("(document.querySelector('.entry-tag--check.is-invalid')||{}).textContent ?? ''"), "and says which, and how")

    entry = next(e for e in mth2010["entries"] if e["kind"] == "proof" and "Theorem:" in e["source"])
    reset_page()
    js(
        "(async () => { document.querySelector(\".rail-button[data-view='library']\").click();"
        " await new Promise(r => setTimeout(r, 300));"
        " document.querySelector('.pack-button[data-pack=\"core/mth2010\"]').click();"
        " await new Promise(r => setTimeout(r, 200));"
        f" document.querySelector('.entry[data-entry=\"core/mth2010/{entry['id']}\"] .entry-head').click();"
        " await new Promise(r => setTimeout(r, 200));"
        " [...document.querySelectorAll('.entry-actions .text-button')].find(b => b.textContent === 'Use in a proof').click();"
        " return 'ok'; })()"
    )
    time.sleep(0.6)
    state = settle()
    check(state["lines"][0] == f'import "@core/mth2010/{entry["id"]}"', f"'Use in a proof' adds the import line ({state['lines'][0]!r})")
    check(state["verdict"] == "VALID", f"and the proof still checks with it ({state['verdict']})")
    check("Imported '@core/mth2010/" in js("document.querySelector('#audit').textContent"), "the auditor names the pack import")

    print("== an old origin finds its entry again ==")
    fresh()
    js(
        "(async () => { const db = await new Promise(r => { const q = indexedDB.open('aether'); q.onsuccess = () => r(q.result); });"
        " const tx = db.transaction('files', 'readwrite'); const store = tx.objectStore('files');"
        " const all = await new Promise(r => { const q = store.getAll(); q.onsuccess = () => r(q.result); });"
        " for (const f of all) { f.origin = 'examples/even-square'; store.put(f); }"
        " await new Promise(r => tx.oncomplete = r); db.close(); window.__set = true; return 'ok'; })()"
    )
    time.sleep(0.5)
    ab("reload")
    settle()
    ab("click", "#desk-tab-notes")
    time.sleep(0.5)
    check("Even square" in js("document.querySelector('#notes').textContent"), "a file opened from the old 'examples' pack still shows its entry")


def pack_author_checks() -> None:
    print("== a workspace folder becomes a pack ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    time.sleep(0.4)
    js("[...document.querySelectorAll('.packs-actions .text-button')].find(b => b.textContent === 'New pack…').click(); 'ok'")
    time.sleep(1.2)
    check(js("document.getElementById('pack-dialog').open") is True, "New pack… opens the pack's details")
    check("New pack/First proof.aether" in workspace()["path"], f"beside a first proof in a new folder ({workspace()['path']!r})")

    ab("click", "#pack-install")
    time.sleep(2.0)
    check("does not parse" in js("document.getElementById('pack-status').textContent"), "a proof that does not parse keeps the pack from installing")

    js("document.getElementById('pack-dialog').open = false; 'ok'")
    time.sleep(0.5)
    append_to_line(3, "Let x : Real")
    ab("press", "Enter")
    ab("keyboard", "type", "Step: x + x = 2 * x")
    state = settle()
    check(state["verdict"] == "VALID", f"once it checks ({state['verdict']})")
    saved()
    check(js("[...document.querySelectorAll('#explorer .tree-tag')].map(e => e.textContent).join()") == "pack", "the folder is marked as a pack")
    js("document.querySelector('#explorer .tree-row--folder[data-folder=\"New pack\"] .tree-action[aria-label^=\"Pack\"]').click(); 'ok'")
    time.sleep(0.8)
    check(js("document.getElementById('pack-dialog').open") is True, "the folder's pack button reopens the details")

    target = Path("/tmp/aether-verify-pack.json")
    target.unlink(missing_ok=True)
    ab("download", "#pack-export", str(target))
    time.sleep(1.0)
    check(target.exists(), "Export writes a .pack.json")
    if target.exists():
        exported = json.loads(target.read_text())
        check(exported["name"] == "me/new-pack" and exported["entries"][0]["expected"] == "VALID", "recording each entry's real verdict")
        check(exported.get("courses", []) == [], "with no course code unless one was given")

    ab("click", "#pack-install")
    time.sleep(2.5)
    check(js("document.body.dataset.view") == "library", "Install in this browser goes to the Library")
    check("made in this browser" in js("document.querySelector('.pack-meta').textContent"), "where the pack is listed as made here")
    pack_action("Check all entries")
    time.sleep(2.5)
    check("gives the verdict this pack records" in js("(document.querySelector('.pack-check')||{}).textContent ?? ''"), "and its entry still gives its recorded verdict")

    print("== a backup keeps a folder's pack details ==")
    import zipfile

    ab("click", ".rail-button[data-view='workspace']")
    time.sleep(0.4)
    ab("click", "#desk-tab-files")
    target = Path("/tmp/aether-verify-pack-workspace.zip")
    target.unlink(missing_ok=True)
    ab("download", "#workspace-export", str(target))
    time.sleep(0.8)
    with zipfile.ZipFile(target) as archive:
        manifests = json.loads(archive.read("packs/manifests.json")) if "packs/manifests.json" in archive.namelist() else {}
    check(manifests.get("New pack", {}).get("name") == "me/new-pack", "the .zip carries the folder's pack details")
    wipe()
    ab("open", BASE)
    settle()
    ab("click", "#desk-tab-files")
    ab("upload", "#workspace-import-input", str(target))
    time.sleep(1.2)
    check(js("[...document.querySelectorAll('#explorer .tree-tag')].map(e => e.textContent).join()") == "pack", "and restoring it makes the folder a pack again")


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


VISUAL_SOURCE = """Theorem: "Typeset"
Proof:
    Let x : Real
    Assume h1: x > 2
    Step: (x^2 - 4) / (x - 2) = x + 2
    Step: (x + 1)^2 = x^2 + 2 * x + 2
QED
"""


def working_checks() -> None:
    print("== show your working: the switch re-checks with the option ==")
    ab("open", permalink("Let x : Real\nStep: diff(x^2 * sin(x), x) = 2 * x * sin(x) + x^2 * cos(x)\n"))
    state = settle()
    check(state["verdict"] == "VALID", f"the product rule in one jump is valid by default ({state['verdict']})")
    js("document.querySelector('#working').shadowRoot.querySelector('label').click(); 'ok'")
    time.sleep(0.4)
    state = settle()
    check(state["verdict"] == "VALID (with warnings)", f"switching on Show working makes it a warning, not a domain one ({state['verdict']})")
    check("product rule" in state["ctxHas"] or "product rule" in js("document.querySelector('#audit').textContent"), "the warning names the product rule")
    check("w=1" in (state["hash"] or ""), f"the proof's link carries Show working ({state['hash'][-12:]})")


GRAPH_PROOF = """\
Let x, y : Real
Assume hx: x > 2
Assume hy: y > 0
Step: x^2 > 4
Step: x^2 + y > 4
Theorem: "n^2 + n is even"
Claim: forall n : Int, Even(n^2 + n)
Proof:
    Given n : Int
    Case Even(n):
        Obtain k : Int such that n = 2 * k
        Step: n^2 + n = 2 * (2 * k^2 + k)
        Therefore Even(n^2 + n)
    Case Odd(n):
        Obtain k : Int such that n = 2 * k + 1
        Step: n^2 + n = 2 * (2 * k^2 + 3 * k + 1)
        Therefore Even(n^2 + n)
    Therefore Even(n^2 + n)
QED
"""


def graph_checks() -> None:
    print("== the proof graph: arcs, Used and Used by, and the Trace tab ==")
    ab("open", permalink(GRAPH_PROOF))
    settle()
    index = js("[...document.querySelectorAll('.step')].findIndex(r => r.textContent.includes('(x ^ 2) + y'))")
    check(index >= 0, f"the step x^2 + y > 4 is in the auditor ({index})")
    # The row is a button: activating it is what a click does, wherever the
    # layout of this run has put it.
    js(f"document.querySelector('.step[data-index=\"{index}\"]').click(); 'ok'")
    time.sleep(0.4)
    state = js(
        "({ graph: document.querySelector('#audit').classList.contains('has-graph'),"
        " arcs: document.querySelectorAll('.arcs-premises path').length,"
        " lit: [...document.querySelectorAll('.step.is-premise .step-line')].map(n => n.textContent),"
        " used: [...document.querySelectorAll('#context .ctx-used')].map(n => n.textContent),"
        " toggle: !document.querySelector('#graph-toggle').hidden })"
    )
    check(state["graph"] and state["toggle"], f"a check with the audit draws the graph and shows its toggle ({state})")
    check(state["arcs"] == 2 and sorted(state["lit"]) == ["3", "4"], f"its premises are drawn and their lines lit ({state['arcs']}, {state['lit']})")
    check(any("the line before" in u for u in state["used"]) and any("hy" in u for u in state["used"]), f"Used names the line before and hy ({state['used']})")
    js("document.querySelector('#context .ctx-used').click(); 'ok'")
    time.sleep(0.3)
    after = js("({ line: document.querySelector('#context-sub').textContent, by: [...document.querySelectorAll('#context .ctx-section h3')].map(h => h.textContent) })")
    check(after["line"] == "Line 4" and "Used by" in after["by"], f"a Used row selects its line, which lists Used by ({after})")
    js("document.querySelector('#graph-toggle').click(); 'ok'")
    time.sleep(0.2)
    check(js("document.querySelectorAll('.arcs-all path').length") > 0, "the toggle draws every line's arcs")
    js("document.querySelector('#graph-toggle').click(); 'ok'")
    js("document.querySelector('#desk-tab-trace').click(); 'ok'")
    time.sleep(0.3)
    trace = js(
        "({ command: document.querySelector('.trace-command')?.textContent ?? '',"
        " blocks: document.querySelectorAll('.trace-block').length,"
        " inner: document.querySelectorAll('.trace-inner').length,"
        " calls: document.querySelectorAll('.trace-event').length,"
        " selected: document.querySelector('.trace-block.is-selected .trace-line')?.textContent })"
    )
    check("lemmata --trace" in trace["command"], f"the Trace tab names the command that prints the same log ({trace['command']})")
    check(trace["blocks"] >= 8 and trace["calls"] > 5, f"it lists each line and its calls ({trace})")
    check(trace["inner"] >= 6, f"a case block's own lines are nested under it ({trace['inner']})")
    check(trace.get("selected") == "L4", f"it follows the selected step ({trace.get('selected')})")
    js("document.querySelector('#desk-tab-files').click(); 'ok'")
    js("localStorage.setItem('aether-audit', 'off'); 'ok'")
    ab("open", permalink(GRAPH_PROOF))
    settle()
    off = js("({ graph: document.querySelector('#audit').classList.contains('has-graph'), arcs: document.querySelectorAll('.arcs path').length })")
    check(not off["graph"] and off["arcs"] == 0, f"with the audit off in Settings, no graph is drawn ({off})")
    js("localStorage.removeItem('aether-audit'); 'ok'")


LEAP = 'Theorem: "3x continuous at 2"\nProof:\n    Therefore forall e : Real, e > 0 => exists d : Real, d > 0 and (forall x : Real, abs(x - 2) < d => abs(3 * x - 6) < e)\nQED\n'


def pick_level(label: str) -> None:
    js(f"[...document.querySelectorAll('#level-menu wa-dropdown-item')].find(i => i.textContent.trim().startsWith('{label}')).click(); 'ok'")
    time.sleep(0.4)


def level_checks() -> None:
    print("== the checking level: the kernel in the app ==")
    ab("open", permalink(LEAP))
    state = settle()
    button = js("document.querySelector('#level-button').textContent")
    check(button == "Level: Off" and state["verdict"] == "VALID", f"a link from before levels opens at Off, as it was checked ({button}, {state['verdict']})")
    pick_level("Course")
    state = settle()
    audit = js("document.querySelector('#audit').textContent")
    check(state["verdict"] == "INVALID" and "too big a step" in audit, f"at Course, the whole epsilon-delta in one line is too big a step ({state['verdict']})")
    check("Kernel: auto" in audit, "and the auditor names what it needed (Kernel: auto)")
    check("l=course" in (state["hash"] or ""), f"the proof's link carries its level ({(state['hash'] or '')[-10:]})")
    pick_level("Off")
    state = settle()
    check(state["verdict"] == "VALID" and "l=" not in (state["hash"] or ""), f"back at Off it checks as it always has ({state['verdict']})")
    check(js("localStorage.getItem('aether-level-default')") in (None, "course"), "new proofs start at the Settings default, Course unless changed")
    # A proof saved before levels existed has no level: it stays Off.
    js("(async () => { const m = await import(new URL('static/js/level.js', document.baseURI).href); window.__lv = [m.levelOf({ source: '' }), m.levelOf({ level: 'exam' }), m.levelOf({ level: null })]; })(); 'ok'")
    time.sleep(0.3)
    levels = js("window.__lv")
    check(levels == ["off", "exam", "off"], f"a proof from before levels stays Off; one with a level keeps it ({levels})")


def boot_checks() -> None:
    print("== boot: the loading line gives way to the workspace ==")
    fresh()
    time.sleep(0.6)
    state = js(
        "({ booting: 'booting' in document.documentElement.dataset,"
        " boot: getComputedStyle(document.querySelector('.boot')).display,"
        " view: getComputedStyle(document.querySelector('#view-workspace')).visibility })"
    )
    check(state["booting"] is False, "the booting flag is cleared once the workspace is ready")
    check(state["boot"] == "none" and state["view"] == "visible", f"the loading line is gone and the workspace shows ({state})")
    paper = js("getComputedStyle(document.documentElement).backgroundColor")
    check(paper in ("rgb(255, 255, 255)", "rgb(14, 16, 19)"), f"the page's paper is set before the stylesheets ({paper})")


def visual_checks() -> None:
    print("== visual mode typesets the maths and opens it under the caret ==")
    fresh()
    ab("click", ".rail-button[data-view='settings']")
    time.sleep(0.4)
    js("document.querySelector('#setting-visual').shadowRoot.querySelector('label').click(); 'ok'")
    time.sleep(0.3)
    check(js("localStorage.getItem('aether-visual')") == "on", "the Settings switch turns visual mode on")
    ab("open", permalink(VISUAL_SOURCE))
    settle()
    time.sleep(0.4)
    lines = [js(f"document.querySelectorAll('.cm-line')[{i}].querySelectorAll('.cm-math').length") for i in range(7)]
    # The caret starts on line 1, so every expression below it is typeset;
    # keywords and labels are not.
    check(lines[2:6] == [1, 1, 1, 1], f"each line's expression is typeset ({lines})")
    check(js("!!document.querySelector('.cm-math mfrac')") is True, "a fraction stacks")
    check(
        js("document.querySelectorAll('.cm-line')[3].textContent.startsWith('    Assume h1: ')") is True,
        "the keyword and the label stay as text",
    )
    # The failing step keeps its squiggle under the typeset maths.
    check(
        js("!!document.querySelectorAll('.cm-line')[5].querySelector('.cm-math.cm-lintRange-error')") is True,
        "a failing step's typeset maths is underlined like the rest of the line",
    )
    # Clicking an expression opens it as source; the document never changed.
    ab("click", ".cm-line:nth-child(5) .cm-math")
    time.sleep(0.3)
    check(
        js("document.querySelectorAll('.cm-line')[4].textContent") == "    Step: (x^2 - 4) / (x - 2) = x + 2",
        "clicking an expression shows the source that was typed",
    )
    check(js("document.querySelectorAll('.cm-line')[2].querySelectorAll('.cm-math').length") == 1, "the other lines stay typeset")
    # And off again, live; with the widgets gone the lines are the document
    # itself, which the typesetting never touched.
    ab("click", ".rail-button[data-view='settings']")
    time.sleep(0.4)
    js("document.querySelector('#setting-visual').shadowRoot.querySelector('label').click(); 'ok'")
    time.sleep(0.3)
    check(js("document.querySelectorAll('.cm-math').length") == 0, "turning it off sets every line back to source")
    check(probe()["lines"][:7] == VISUAL_SOURCE.rstrip("\n").split("\n"), "the proof's text is untouched by the typesetting")


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


def static_checks() -> None:
    print("== the static build: the checker runs in this browser ==")
    state = fresh()
    check(state["verdict"] == "VALID", f"a first visit checks the starting proof in the browser ({state['verdict']}, {state['meta']})")
    check(js("document.querySelectorAll('.step').length") > 0, "with a step-by-step audit")

    ab("open", permalink(EXAMPLES["algebraic-blunder"]))
    state = settle()
    check(state["verdict"] == "INVALID", f"a blunder fails ({state['verdict']})")
    check("Counterexample" in js("document.querySelector('#audit').textContent"), "with its counterexample")

    ab("open", permalink(EXAMPLES["unguarded-division"]))
    state = settle()
    check(state["verdict"] == "VALID (with domain warnings)", f"an unguarded division warns ({state['verdict']})")
    set_strict(True)
    state = settle()
    check(state["verdict"] == "INVALID", f"and strict domains make it an error ({state['verdict']})")

    import_checks()

    print("== packs, LaTeX and the budget, without a server ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    time.sleep(0.5)
    check("MTH2010" in js("document.getElementById('library-packs').innerText"), "the bundled packs install from the static catalogue")
    mth2010 = next(p for p in json.loads((DIST / "static" / "data" / "library.json").read_text()) if p["name"] == "core/mth2010")
    entry = next(e for e in mth2010["entries"] if e["kind"] == "proof" and "Theorem:" in e["source"])
    reset_page()
    js(
        "(async () => { document.querySelector(\".rail-button[data-view='library']\").click();"
        " await new Promise(r => setTimeout(r, 300));"
        " document.querySelector('.pack-button[data-pack=\"core/mth2010\"]').click();"
        " await new Promise(r => setTimeout(r, 200));"
        f" document.querySelector('.entry[data-entry=\"core/mth2010/{entry['id']}\"] .entry-head').click();"
        " await new Promise(r => setTimeout(r, 200));"
        " [...document.querySelectorAll('.entry-actions .text-button')].find(b => b.textContent === 'Use in a proof').click();"
        " return 'ok'; })()"
    )
    time.sleep(0.6)
    state = settle()
    check(state["verdict"] == "VALID" and "Imported '@core/mth2010/" in js("document.querySelector('#audit').textContent"), f"a pack theorem imports and checks ({state['verdict']})")

    ab("click", "#export-latex")
    deadline = time.time() + 60
    while time.time() < deadline and "documentclass" not in (js("document.querySelector('#latex-output').value") or ""):
        time.sleep(0.5)
    check("documentclass" in (js("document.querySelector('#latex-output').value") or ""), "LaTeX export runs in the browser")
    check(js("document.querySelector('#download-pdf').hidden") is True and js("document.querySelector('#pdf-note').hidden") is False, "PDF export says why it is not here")
    js("document.querySelector('#latex-dialog').open = false; 'ok'")

    slow = next(e for p in json.loads((DIST / "static" / "data" / "library.json").read_text()) for e in p["entries"] if e["id"] == "partial-geometric-sum-needs-r-1")
    js("localStorage.setItem('aether:check-budget-ms', '1500'); 'ok'")
    ab("open", permalink(slow["source"]))
    state = settle(90)
    check(state["verdict"] == "TIMEOUT", f"a check that overruns its budget answers TIMEOUT ({state['verdict']}: {state['meta']})")
    js("localStorage.removeItem('aether:check-budget-ms'); 'ok'")
    ab("open", permalink(EXAMPLES["even-square"]))
    state = settle(90)
    check(state["verdict"] == "VALID", f"and the checker restarts for the next proof ({state['verdict']})")


DIST = PROJECT / "dist"


# ---------------------------------------------------------------------------
# A pack registry of our own, served locally, so no check depends on the network
# ---------------------------------------------------------------------------

ACCENT = "#7a1f5c"
ACCENT_DARK = "#e08cc4"

# A static server that, like GitHub Pages, lets any origin read what it serves.
CORS_SERVER = """
import functools, http.server, sys
class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()
    def log_message(self, *args):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), functools.partial(Handler, directory=sys.argv[2])).serve_forever()
"""


def make_registry(root: Path) -> None:
    """index.json and pack files shaped exactly as the registry's build writes them."""
    import hashlib

    library = json.loads(urllib.request.urlopen(f"{BASE}/api/library", timeout=10).read()) if not STATIC else json.loads((DIST / "static" / "data" / "library.json").read_text())
    mth2010 = next(p for p in library if p["name"] == "core/mth2010")
    newer = json.loads(json.dumps(mth2010))
    newer["version"] = "1.1.0"
    newer["entries"][0]["title"] += " (revised)"
    template = json.loads((PROJECT / "courses" / "mth2010.json").read_text())  # a known-good source of entries
    group = {
        "format": 1, "name": "fixture/group-basics", "version": "1.0.0", "title": "Group basics", "summary": "First facts about groups.",
        "authors": ["Fixture Author"], "license": "CC-BY-SA-4.0", "chapters": [{"id": "1", "title": "Groups"}],
        "entries": [dict(template["entries"][0], chapter="1")],
    }
    preview = dict(group, name="fixture/preview-me", title="Preview me", summary="A pack to look inside before installing.")
    tampered = dict(group, name="fixture/tampered", title="Tampered with", summary="Its file does not match the index.")
    rows = []
    for pack, honest in ((newer, True), (group, True), (preview, True), (tampered, False)):
        raw = json.dumps(pack).encode()
        path = root / "packs" / f"{pack['name']}.pack.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        # The tampered file differs from the bytes the index's sha256 vouches for.
        path.write_bytes(raw if honest else raw.replace(b'"Tampered with"', b'"Tampered with!"'))
        rows.append({
            "name": pack["name"], "version": pack["version"], "title": pack["title"], "courses": pack.get("courses", []),
            "summary": pack["summary"], "authors": pack["authors"], "license": pack["license"], "entries": len(pack["entries"]),
            "traps": sum(e["kind"] == "trap" for e in pack["entries"]), "chapters": [c["title"] for c in pack["chapters"]],
            "search": " ".join(e["title"] for e in pack["entries"]), "url": f"packs/{pack['name']}.pack.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    (root / "index.json").write_text(json.dumps({"format": 1, "generated": "2026-10-03T00:00:00+00:00", "engine": "0.1.0", "contribute": "https://github.com/example/packs", "packs": rows}))


def registry_checks(registry_server: subprocess.Popen) -> None:
    print("== the pack registry: search, install, update, preview, offline ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    deadline = time.time() + 10
    while time.time() < deadline and "Registry · 4 packs" not in rail():
        time.sleep(0.3)
    check("Registry · 4 packs" in rail(), f"the rail says what the registry offers ({rail().splitlines()[-1]!r})")

    print("== site.json: preinstall and accent ==")
    check(available_packs()[:2] == ["core/mth2008", "core/notation"], f"only the packs site.json preinstalls are installed ({available_packs()})")
    colour = js("getComputedStyle(document.documentElement).getPropertyValue('--wa-color-text-link').trim()")
    want = ACCENT_DARK if js("document.documentElement.dataset.theme") == "dark" else ACCENT
    check(colour.lower() == want, f"the site's accent replaces the link colour in this theme ({colour})")

    js("(() => { const s = document.querySelector('#library-search'); s.value = 'group basics'; s.dispatchEvent(new Event('input')); return 1; })()")
    time.sleep(0.4)
    found = js("[...document.querySelectorAll('.registry-row .registry-title')].map(e => e.textContent).join(' | ')")
    check("Group basics" in found, f"a search finds a registry pack ({found!r})")
    js("[...document.querySelectorAll('.registry-row')].find(r => r.textContent.includes('Group basics')).querySelector('.text-button--primary').click(); 'ok'")
    time.sleep(1.5)
    check("Installed Group basics" in toasts(), f"Install fetches, checks and installs it ({toasts()[-80:]!r})")
    check("fixture/group-basics" not in available_packs() and "Group basics" in rail(), "it moves to Installed")

    js("(() => { const s = document.querySelector('#library-search'); s.value = 'tampered'; s.dispatchEvent(new Event('input')); return 1; })()")
    time.sleep(0.4)
    js("document.querySelector('.registry-row .text-button--primary').click(); 'ok'")
    time.sleep(1.5)
    check("checksum" in toasts(), "a file that does not match the index's sha256 is refused")
    js("(() => { const s = document.querySelector('#library-search'); s.value = ''; s.dispatchEvent(new Event('input')); return 1; })()")

    open_pack("core/mth2010")
    check("update" in js("document.querySelector('.pack-button[data-pack=\"core/mth2010\"]').textContent"), "a newer registry version of an installed pack is an update")
    pack_action("Update to v1.1.0")
    time.sleep(1.5)
    check("Updated MTH2010 to v1.1.0 — 1 changed" in toasts(), f"updating from the registry says what changed ({toasts()[-80:]!r})")

    open_pack("fixture/preview-me")
    pack_action("Preview entries")
    time.sleep(1.2)
    check(js("document.querySelectorAll('.pack[data-pack=\"fixture/preview-me\"] .entry').length") == 1, "Preview lists a registry pack's entries before installing")

    print("== ?install=: the registry site's Open in Lemmata link ==")
    ab("open", f"{BASE}/?install=fixture/preview-me&r={time.time_ns()}")
    deadline = time.time() + 15
    while time.time() < deadline and js("document.querySelectorAll('.pack[data-pack=\"fixture/preview-me\"] .entry').length") != 1:
        time.sleep(0.3)
    check(js("document.body.dataset.view") == "library", "the link opens the Library")
    check(js("document.querySelectorAll('.pack[data-pack=\"fixture/preview-me\"] .entry').length") == 1, "on that registry pack, previewed")
    check("fixture/preview-me" in available_packs(), "and nothing is installed until the student clicks Install")
    check("install=" not in js("location.search"), "the link's install= is dropped, so a reload does not repeat it")

    registry_server.terminate()
    registry_server.wait(timeout=10)
    # Past the 10-minute freshness window, so the Library asks again and fails.
    js(
        "(async () => { const db = await new Promise(r => { const q = indexedDB.open('aether'); q.onsuccess = () => r(q.result); });"
        " const tx = db.transaction('meta', 'readwrite'); const store = tx.objectStore('meta');"
        " const row = await new Promise(r => { const q = store.get('registryIndex'); q.onsuccess = () => r(q.result); });"
        " row.value.fetched -= 3600000; store.put(row); await new Promise(r => tx.oncomplete = r); db.close(); return 'ok'; })()"
    )
    ab("reload")
    settle()
    ab("click", ".rail-button[data-view='library']")
    deadline = time.time() + 10
    while time.time() < deadline and "Registry offline" not in rail():
        time.sleep(0.3)
    check("Registry offline · showing what it offered" in rail(), f"offline, the Library says so ({rail().splitlines()[-1]!r})")
    check("fixture/preview-me" in available_packs(), "and still lists what the registry offered")


def start_ui(env: dict[str, str]) -> subprocess.Popen:
    server = subprocess.Popen(
        [sys.executable, "-m", "ui", "--port", str(PORT)],
        cwd=str(PROJECT),
        env={**os.environ, **env},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        try:
            urllib.request.urlopen(f"{BASE}/api/health", timeout=1)
            return server
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("server did not start")


def main() -> int:
    if STATIC:
        return static_main()
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="aether-verify-"))
    # The main run has no registry: its checks are about the app's own packs.
    (tmp / "no-registry.json").write_text(json.dumps({"registry": ""}))
    server = subprocess.Popen(
        [sys.executable, "-m", "ui", "--port", str(PORT)],
        cwd=str(PROJECT),
        env={**os.environ, "LEMMATA_SITE": str(tmp / "no-registry.json")},
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

        # Then the registry, against one of our own, with a branded site.json.
        reg_port = free_port()
        make_registry(tmp / "registry")
        registry_server = subprocess.Popen(
            [sys.executable, "-c", CORS_SERVER, str(reg_port), str(tmp / "registry")],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        (tmp / "registry-site.json").write_text(json.dumps({
            "registry": f"http://127.0.0.1:{reg_port}/",
            "accent": {"light": ACCENT, "dark": ACCENT_DARK},
            "preinstall": ["core/examples", "core/mth2010"],
        }))
        server.terminate()
        server.wait(timeout=10)
        server = start_ui({"LEMMATA_SITE": str(tmp / "registry-site.json")})
        try:
            registry_checks(registry_server)
        finally:
            registry_server.terminate()
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


def static_registry_checks() -> None:
    print("== the registry in the static build: validated by the browser's own engine ==")
    fresh()
    ab("click", ".rail-button[data-view='library']")
    deadline = time.time() + 15
    while time.time() < deadline and "Registry · 4 packs" not in rail():
        time.sleep(0.3)
    js("(() => { const s = document.querySelector('#library-search'); s.value = 'group basics'; s.dispatchEvent(new Event('input')); return 1; })()")
    time.sleep(0.4)
    js("[...document.querySelectorAll('.registry-row')].find(r => r.textContent.includes('Group basics')).querySelector('.text-button--primary').click(); 'ok'")
    deadline = time.time() + 60
    while time.time() < deadline and "Installed Group basics" not in toasts():
        time.sleep(0.5)
    check("Installed Group basics" in toasts(), f"a registry pack installs with no server ({toasts()[-80:]!r})")


def static_main() -> int:
    global DIST, STARTING_SOURCE, BASE
    import tempfile

    if not (ROOT / "static" / "vendor" / "pyodide" / "pyodide.mjs").exists():
        print("Pyodide is not vendored: run `uv run python ui/vendor_pyodide.py` first.")
        return 1
    # A build of our own, pointed at a local registry, so nothing depends on the network.
    tmp = Path(tempfile.mkdtemp(prefix="aether-verify-static-"))
    reg_port = free_port()
    (tmp / "site.json").write_text(json.dumps({"registry": f"http://127.0.0.1:{reg_port}/"}))
    # Built where the public site puts it, under /app/ (ui/build_site.py).
    DIST = tmp / "site" / "app"
    BASE = f"http://127.0.0.1:{PORT}/app"
    subprocess.run(
        [sys.executable, str(ROOT / "build_static.py"), "--out", str(DIST)],
        env={**os.environ, "LEMMATA_SITE": str(tmp / "site.json")},
        check=True,
        stdout=subprocess.DEVNULL,
    )
    make_registry(tmp / "registry")
    registry_server = subprocess.Popen([sys.executable, "-c", CORS_SERVER, str(reg_port), str(tmp / "registry")])
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PORT), "--bind", "127.0.0.1", "--directory", str(DIST.parent)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.0)
        examples = next(p for p in json.loads((DIST / "static" / "data" / "library.json").read_text()) if p["name"] == "core/examples")
        EXAMPLES.update({e["id"]: e["source"] for e in examples["entries"]})
        STARTING_SOURCE = EXAMPLES["even-square"]
        static_checks()
        lean_checks()
        static_registry_checks()
    finally:
        ab("close")
        server.terminate()
        server.wait(timeout=10)
        registry_server.terminate()
    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("all static-build browser checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
