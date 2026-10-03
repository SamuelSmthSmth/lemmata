// This site's identity and configuration, from ui/site.json (via /api/site, or
// the static build's static/data/site.json): name, tagline, accent, registry,
// preinstalled packs.
//
// Nothing in the frontend spells the name out: text that names the product
// reads `site.name`, and static markup marks the spot with [data-site-name]
// for applySiteName() to fill.  The defaults below are only what shows if the
// site details cannot be read.

import { fetchSite } from "./api.js";

export const site = {
  name: "Lemmata",
  tagline: "Proof intern",
  version: "",
  accent: { light: "#0a5fbf", dark: "#6cb0ff" },
  registry: "",
  preinstall: null,
};

const DEFAULT_ACCENT = { ...site.accent };

export async function loadSite() {
  try {
    Object.assign(site, await fetchSite());
  } catch {
    // Keep the defaults; the rest of the app reports the unreachable server.
  }
  document.title = `${site.name} · ${site.tagline}`;
  applySiteName(document);
  applyAccent(site.accent);
  return site;
}

/**
 * Brand the one colour a site may brand.  The accent is the link and focus
 * colour Web Awesome and styles.css both derive from; site.py has already
 * refused any accent below 4.5:1 on its theme's paper.
 */
export function applyAccent(accent) {
  if (!accent || (accent.light === DEFAULT_ACCENT.light && accent.dark === DEFAULT_ACCENT.dark)) return;
  const tokens = (colour, fill) =>
    `--wa-color-text-link: ${colour}; --wa-color-focus: ${colour}; --wa-color-brand-on-quiet: ${colour};` +
    ` --wa-color-brand-fill-loud: ${fill}; --wa-color-brand-fill-quiet: color-mix(in oklab, ${colour} 9%, transparent);`;
  const style = document.getElementById("site-accent") ?? document.head.appendChild(Object.assign(document.createElement("style"), { id: "site-accent" }));
  style.textContent =
    `:root { ${tokens(accent.light, accent.light)} }\n` +
    `[data-theme="dark"] { ${tokens(accent.dark, `color-mix(in oklab, ${accent.dark} 70%, #000)`)} }`;
}

export function applySiteName(root) {
  for (const node of root.querySelectorAll("[data-site-name]")) node.textContent = site.name;
}
