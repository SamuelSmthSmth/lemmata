// Persistent workspace state.
//
// Two keys, deliberately: the buffer is written on every edit, while the
// timeline is written on every check.  Keeping them apart means a check does
// not rewrite every saved snapshot with it.
//
//   aether:workspace -> { v, source, strict, exampleId, snapshots: [...] }
//   aether:timeline  -> { v, entries: [...] }
//
// Every read and write is guarded: localStorage throws in private browsing
// modes and when the quota is exhausted.  A failure is reported to the caller
// (persist() returns false) rather than swallowed, because silently losing a
// user's proof is the one outcome worth being loud about.

const WORKSPACE_KEY = "aether:workspace";
const TIMELINE_KEY = "aether:timeline";
const VERSION = 1;

// Snapshots embed a full copy of the source, so they are capped tightly.
const MAX_SNAPSHOTS = 20;
const MAX_TIMELINE = 120;

function emptyWorkspace() {
  // `saved` distinguishes "never stored anything" from "stored an empty
  // buffer", which are different states on boot: the first loads the example,
  // the second must stay empty.
  return { v: VERSION, saved: false, source: "", strict: false, exampleId: null, snapshots: [] };
}

function emptyTimeline() {
  return { v: VERSION, entries: [] };
}

function readJson(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" && parsed.v === VERSION ? parsed : null;
  } catch (error) {
    return null;
  }
}

const storedWorkspace = readJson(WORKSPACE_KEY);
const storedTimeline = readJson(TIMELINE_KEY);

export const workspace = {
  ...emptyWorkspace(),
  ...(storedWorkspace ?? {}),
  saved: Boolean(storedWorkspace?.saved),
  source: typeof storedWorkspace?.source === "string" ? storedWorkspace.source : "",
  snapshots: Array.isArray(storedWorkspace?.snapshots) ? storedWorkspace.snapshots : [],
};

export const timeline = {
  ...emptyTimeline(),
  ...(storedTimeline ?? {}),
  entries: Array.isArray(storedTimeline?.entries) ? storedTimeline.entries : [],
};

// Flips to false the first time a write fails, so the UI only warns once.
export let storageHealthy = true;

export function persistWorkspace() {
  try {
    localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace));
    storageHealthy = true;
    return true;
  } catch (error) {
    storageHealthy = false;
    return false;
  }
}

export function persistTimeline() {
  try {
    localStorage.setItem(TIMELINE_KEY, JSON.stringify(timeline));
    return true;
  } catch (error) {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Snapshots
// ---------------------------------------------------------------------------

let snapshotSeq = 0;

export function addSnapshot({ name, source, strict, auto = false }) {
  if (!source || !source.trim()) return null;
  const snapshot = {
    id: `${Date.now().toString(36)}-${snapshotSeq++}`,
    name,
    ts: Date.now(),
    source,
    strict: Boolean(strict),
    auto: Boolean(auto),
  };
  workspace.snapshots.unshift(snapshot);
  if (workspace.snapshots.length > MAX_SNAPSHOTS) {
    workspace.snapshots.length = MAX_SNAPSHOTS;
  }
  persistWorkspace();
  return snapshot;
}

export function removeSnapshot(id) {
  const index = workspace.snapshots.findIndex((snapshot) => snapshot.id === id);
  if (index === -1) return false;
  workspace.snapshots.splice(index, 1);
  persistWorkspace();
  return true;
}

// ---------------------------------------------------------------------------
// Verdict timeline
//
// Consecutive identical verdicts are coalesced into one entry with a run count.
// Checking on every pause while typing mostly produces the same verdict
// repeatedly, and a run-length strip reads far better than 40 identical dots.
// ---------------------------------------------------------------------------

export function recordOutcome({ verdict, invalid = 0, warnings = 0 }) {
  const entries = timeline.entries;
  const last = entries[entries.length - 1];
  if (last && last.verdict === verdict) {
    last.ts = Date.now();
    last.invalid = invalid;
    last.warnings = warnings;
    last.n = (last.n ?? 1) + 1;
  } else {
    entries.push({ verdict, invalid, warnings, ts: Date.now(), n: 1 });
  }
  if (entries.length > MAX_TIMELINE) {
    entries.splice(0, entries.length - MAX_TIMELINE);
  }
  persistTimeline();
}

export function clearTimeline() {
  timeline.entries.length = 0;
  persistTimeline();
}

export function clearSnapshots() {
  workspace.snapshots.length = 0;
  persistWorkspace();
}
