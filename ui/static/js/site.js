// The product's name, tagline and version, from ui/site.json via /api/site.
//
// The name is provisional, so nothing in the frontend spells it out: text
// that names the product reads `site.name`, and static markup marks the spot
// with [data-site-name] for applySiteName() to fill.  The defaults below are
// only what shows if the server cannot be asked.

import { fetchSite } from "./api.js";

export const site = { name: "Lemmata", tagline: "Proof intern", version: "" };

export async function loadSite() {
  try {
    Object.assign(site, await fetchSite());
  } catch {
    // Keep the defaults; the rest of the app reports the unreachable server.
  }
  document.title = `${site.name} · ${site.tagline}`;
  applySiteName(document);
  return site;
}

export function applySiteName(root) {
  for (const node of root.querySelectorAll("[data-site-name]")) node.textContent = site.name;
}
