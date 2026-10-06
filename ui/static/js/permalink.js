// Shareable links: the proof travels in the URL fragment, so a link reproduces
// a document without the server storing anything.
//
//   #p=<base64url of the UTF-8 source>&s=1&w=1  (s = strict domain checking,
//                                               w = show your working)
//
// base64url over TextEncoder bytes rather than btoa(source): btoa() throws on
// any code point above U+00FF, which a proof hits immediately with "≤", "∀" or
// a non-ASCII theorem name.

const PARAM = "p";
const STRICT_PARAM = "s";
const WORKING_PARAM = "w";
const LEVEL_PARAM = "l";

function bytesToBase64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function base64UrlToBytes(token) {
  const padded = token.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded.padEnd(padded.length + ((4 - (padded.length % 4)) % 4), "="));
  return Uint8Array.from(binary, (char) => char.charCodeAt(0));
}

export function encodeSource(source) {
  return bytesToBase64Url(new TextEncoder().encode(source));
}

export function decodeSource(token) {
  return new TextDecoder().decode(base64UrlToBytes(token));
}

/** Parse the current fragment, or null when it carries no proof. */
export function readPermalink() {
  const raw = window.location.hash.startsWith("#")
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!raw) return null;
  const params = new URLSearchParams(raw);
  const token = params.get(PARAM);
  if (!token) return null;
  try {
    return {
      source: decodeSource(token),
      strict: params.get(STRICT_PARAM) === "1",
      working: params.get(WORKING_PARAM) === "1",
      // A link from before levels was checked without the kernel: Off.
      level: params.get(LEVEL_PARAM) ?? "off",
    };
  } catch (error) {
    // A mangled fragment is not worth failing over; fall back to saved work.
    return null;
  }
}

/**
 * Mirror the buffer into the address bar.
 *
 * replaceState, not pushState: the fragment tracks the current proof, so it
 * must not fill the back stack with one entry per keystroke pause.
 */
export function writePermalink(source, strict, working = false, level = "off") {
  const params = new URLSearchParams();
  params.set(PARAM, encodeSource(source));
  if (strict) params.set(STRICT_PARAM, "1");
  if (working) params.set(WORKING_PARAM, "1");
  if (level && level !== "off") params.set(LEVEL_PARAM, level);
  const url = `${window.location.pathname}${window.location.search}#${params.toString()}`;
  try {
    window.history.replaceState(null, "", url);
  } catch (error) {
    // Some browsers restrict replaceState on file:// or sandboxed frames.
  }
}

/** The URL that reproduces the current buffer. */
export function permalinkFor(source, strict, working = false, level = "off") {
  const params = new URLSearchParams();
  params.set(PARAM, encodeSource(source));
  if (strict) params.set(STRICT_PARAM, "1");
  if (working) params.set(WORKING_PARAM, "1");
  if (level && level !== "off") params.set(LEVEL_PARAM, level);
  return `${window.location.origin}${window.location.pathname}#${params.toString()}`;
}
