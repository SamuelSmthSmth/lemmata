# Tooling: driving a browser from an agent

`ui/verify_browser.py` drives a real Chrome, so UI behaviour that only exists in
a browser (keybindings, the check round-trip, the client-side inspector, theme
swapping) is testable. Underneath it is the `agent-browser` CLI, and this file
records what that CLI can and cannot do, established by sweeping it on
2026-09-29 against **agent-browser 0.36.0** (Chrome for Testing, Linux).

The sweep used a purpose-built fixture (a page with a form, a select, checkboxes,
a table, a list, a file input, a download link, a delayed element, localStorage
and a console error) plus this repo's own UI served on a port. `agent-browser
doctor` reports 13 pass / 0 warn / 0 fail on this machine, and a headless launch
takes about 0.75s.

## Sessions: always name yours

The unnamed session is a single shared browser. Two sessions were run at once
during the sweep and kept separate pages, so isolation is real -- use it:

```bash
export AGENT_BROWSER_SESSION="$(agent-browser session id --prefix aether --scope worktree)"
agent-browser open http://127.0.0.1:8765/
agent-browser close            # closes this session only; --all closes every one
```

`agent-browser session list` shows every live session, which is useful when an
old one is holding a page open.

## What works

| Area | Commands | Notes |
| --- | --- | --- |
| Navigation | `open`, `back`, `forward`, `reload`, `pushstate` | local files via `file://` and http(s) both work |
| Reading | `get text|html|value|attr|title|url|count|box|styles|cdp-url` | `get attr` takes the **selector first, then the attribute name** |
| Structure | `snapshot [-i] [-c] [-d n] [-s sel]`, `find role|text|label|placeholder|alt|title|testid|first|last|nth` | `-i` (interactive only) is the cheap loop: ~200-400 tokens |
| Acting | `click`, `dblclick`, `type`, `fill`, `press`, `keyboard type|inserttext`, `hover`, `focus`, `check`, `uncheck`, `select`, `scroll`, `scrollintoview`, `drag`, `upload`, `download` | refs (`@e3`) and CSS selectors both work; `download` writes the file where you say |
| Waiting | `wait <ms>`, `wait <selector>` | default timeout 25s, then it exits non-zero ("Wait timed out after 25000ms") |
| State | `is visible|enabled|checked`, `get box` | an element that exists but is empty still resolves (height 0) |
| Screenshots | `screenshot [path]`, `screenshot <selector> <path>`, `pdf <path>` | PNG and full-page PDF both verified on disk |
| Debug | `console`, `errors`, `highlight`, `eval`, `inspect`, `clipboard`, `trace`, `profiler`, `record` | `trace`/`profiler`/`record` write real JSON/WebM artefacts |
| Network | `network requests`, `network route --abort|--body`, `network unroute`, `network har start|stop` | request log, request blocking/rewriting, and a HAR file |
| Storage | `storage local|session`, `cookies get|set|clear` | cookies need an **http(s) origin**; `file://` gives "Invalid cookie fields" |
| Emulation | `set viewport|device|geo|media|offline|headers|credentials` | `device` accepts a fixed list: iPhone 15/16/16 Pro/17, iPad, iPad Pro, Pixel 9, Galaxy S25 |
| Analysis | `a11y`, `vitals`, `diff snapshot`, `diff screenshot --baseline`, `diff url` | axe-core 4.12.1, Core Web Vitals, and three kinds of diff |
| Batch | `batch [--bail] "cmd" ...` | `--bail` stops at the first failure and exits non-zero |
| Ops | `session list`, `session id`, `doctor [--fix]`, `plugin list`, `auth list`, `dashboard start|stop`, `stream status|enable|disable`, `webmcp list` | the dashboard serves on a local port; runtime streaming is on by default |

Errors are signalled the way a script wants them: a bad selector, a URL that will
not resolve, a JS exception and a wait timeout all exit non-zero with a
one-line explanation.

## Footguns found

- **`get attr` argument order.** The help text reads `attr <name>`, but the
  call is `get attr <selector> <name>`; the other order reports
  "Element not found: href".
- **`find nth` argument order.** `find nth <index> <selector> <action>`, not
  selector-then-index. `find first|last <selector>` take no index.
- **Tabs are not numeric.** `tab 0` is rejected: use the stable ids that
  `tab list` prints (`t0`, `t1`) or a tab label.
- **`errors` prints bare bullets.** On 0.36.0 the page-error list comes out as
  `✗` with no message. Use `console`, or read the message yourself with
  `eval "window.__err"` / an `error` listener.
- **`eval` is not async and not awaited.** `await` is a syntax error, and an
  exception in the snippet fails the command. `eval "({a:1})"` returns pretty
  JSON, which is the easiest way to get structured data back.
- **Clipboard access is refused by default.** `clipboard read|write` fail with
  `NotAllowedError` unless the browser is granted permission.
- **`stream enable` fails when streaming is already on** ("Streaming is already
  enabled for this session") -- check `stream status` instead, which also prints
  the WebSocket URL.
- **A selector that "is not found" is usually the DOM, not the tool.** During the
  sweep a hand-written fixture had one unbalanced quote, which made the parser
  swallow half the page; every probe against those elements failed honestly.
  `eval "document.body.innerHTML"` and `eval "[...document.querySelectorAll('[id]')]"`
  are the fastest way to tell a broken page from a broken selector.
- **Unavailable here.** `react tree` needs `open --enable react-devtools`;
  `profiles` needs a Chrome user-data directory (this machine has none); `chat`
  needs `AI_GATEWAY_API_KEY`; `install`/`upgrade` and the cloud-browser skills
  want network access we do not need.

## Recipes for this repo

```bash
# Serve the UI, then drive it by hand
setsid nohup uv run python -m ui --port 8765 > /tmp/ui.log 2>&1 < /dev/null &
export AGENT_BROWSER_SESSION=ui-scratch
agent-browser open http://127.0.0.1:8765/
agent-browser snapshot -i                  # refs for the toolbar and panels
agent-browser screenshot /tmp/ui.png

# Accessibility audit of the real page (axe-core, JSON for a machine to read)
agent-browser a11y --json | jq '.data.counts, .data.violations[] | {id, impact, nodeCount}'

# Watch a layout change: baseline, change, compare
agent-browser screenshot /tmp/before.png
# ... edit ui/static/styles.css, reload ...
agent-browser reload && agent-browser screenshot /tmp/after.png
agent-browser diff screenshot --baseline /tmp/before.png

# Trace one interaction end to end
agent-browser network har start
agent-browser click "#run" && agent-browser wait "#audit"
agent-browser network har stop /tmp/run.har

# Kill the dev server by port, not by name: pkill -f "python -m ui" kills its own shell
ss -lptn "sport = :8765" | tail -1 | grep -o 'pid=[0-9]*' | cut -d= -f2 | xargs -r kill
```

The two npm-installed skills that matter here are `core` (the
snapshot-and-ref workflow) and `dogfood` (systematic exploratory testing);
`agent-browser skills get core --full` prints the complete command reference
shipped with the installed version, which is the authoritative source when this
file and the CLI disagree.
