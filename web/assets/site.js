// The site's few behaviours: the theme toggle (shared with the app), the
// storage notice, the download page's platform pick, and the landing page's
// scrub, which walks the checker's real audit step by step.
//
// Every page is complete without this file: the audit is rendered in full,
// stopped at its failing step, and the notice simply never appears.

const THEME_KEY = "aether-theme"; // the app's key, so both remember one choice
const NOTICE_KEY = "lemmata-storage-notice";

const store = {
  get(key) {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch {
      // Storage refused: the choice simply lasts for this page.
    }
  },
};

// --- Theme --------------------------------------------------------------------

function applyThemeImages(theme) {
  for (const img of document.querySelectorAll("img.themed")) {
    const src = img.dataset[theme];
    if (src && img.getAttribute("src") !== src) img.setAttribute("src", src);
  }
}

for (const button of document.querySelectorAll(".theme-toggle")) {
  button.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    store.set(THEME_KEY, next);
    applyThemeImages(next);
  });
}
applyThemeImages(document.documentElement.dataset.theme);

// --- The menu on narrow screens -------------------------------------------------

const menu = document.querySelector(".nav-menu");
if (menu) {
  const links = document.getElementById(menu.getAttribute("aria-controls"));
  const close = () => {
    menu.setAttribute("aria-expanded", "false");
    links.classList.remove("is-open");
  };
  menu.addEventListener("click", () => {
    const open = menu.getAttribute("aria-expanded") !== "true";
    menu.setAttribute("aria-expanded", String(open));
    links.classList.toggle("is-open", open);
    if (open) links.querySelector("a")?.focus();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && menu.getAttribute("aria-expanded") === "true") {
      close();
      menu.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target) && !links.contains(event.target)) close();
  });
}

// --- Storage notice -----------------------------------------------------------

// On the landing page it waits until the hero is scrolled away, so it never
// covers the audit's failing step; elsewhere it shows at once.
const notice = document.querySelector(".notice");
if (notice && !store.get(NOTICE_KEY)) {
  notice.querySelector("[data-notice-dismiss]").addEventListener("click", () => {
    store.set(NOTICE_KEY, "seen");
    notice.hidden = true;
  });
  const hero = document.querySelector(".hero");
  if (hero) {
    const watch = new IntersectionObserver((entries) => {
      if (entries.every((e) => !e.isIntersecting)) {
        watch.disconnect();
        notice.hidden = false;
      }
    });
    watch.observe(hero);
  } else {
    notice.hidden = false;
  }
}

// --- Download: put this platform first ---------------------------------------

const platforms = document.querySelector(".platforms");
if (platforms) {
  const ua = navigator.userAgent;
  const os = /Windows/.test(ua) ? "windows" : /Mac OS X|Macintosh/.test(ua) && !/iPhone|iPad/.test(ua) ? "macos" : /Linux|X11/.test(ua) && !/Android/.test(ua) ? "linux" : null;
  const mine = os && platforms.querySelector(`[data-os="${os}"]`);
  if (mine) {
    mine.classList.add("is-recommended");
    platforms.prepend(mine);
  }
}

// --- Copy buttons ---------------------------------------------------------------

for (const button of document.querySelectorAll("[data-copy]")) {
  button.addEventListener("click", async () => {
    const text = document.getElementById(button.dataset.copy)?.textContent ?? "";
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      button.textContent = "Select and copy";
    }
    setTimeout(() => (button.textContent = "Copy"), 1800);
  });
}

// --- The scrub ----------------------------------------------------------------

const run = document.querySelector(".run");
if (run) {
  const scrub = run.querySelector("#scrub");
  const rows = [...run.querySelectorAll(".audit-row")];
  const ticks = run.querySelector(".scrub-ticks");
  const readout = run.querySelector(".scrub-readout");
  const replay = run.querySelector(".scrub-replay");
  const fail = Number(run.dataset.fail);
  const specimenSymbols = [...document.querySelectorAll(".specimen .sym")];
  const glyphs = [...document.querySelectorAll(".glyph")];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

  ticks.replaceChildren(
    ...rows.map((row, i) => {
      const tick = document.createElement("li");
      if (i === fail) tick.classList.add("is-failure");
      return tick;
    }),
  );

  function show(index) {
    const row = rows[index];
    rows.forEach((r, i) => {
      r.classList.toggle("is-ahead", i > index);
      r.classList.toggle("is-current", i === index);
    });
    [...ticks.children].forEach((t, i) => t.classList.toggle("is-reached", i <= index));
    const used = new Set((row.dataset.symbols || "").split(" ").filter(Boolean));
    for (const s of specimenSymbols) s.classList.toggle("is-lit", used.has(s.dataset.symbol));
    for (const g of glyphs) g.classList.toggle("is-lit", used.has(g.dataset.symbol));
    const status = row.dataset.status.toLowerCase();
    readout.innerHTML = "";
    const where = document.createElement("strong");
    where.textContent = `Line ${row.dataset.line}`;
    const word = document.createElement("span");
    word.textContent = status;
    if (status === "invalid") word.className = "is-invalid";
    readout.append(where, ` · step ${index + 1} of ${rows.length} · `, word, ` · ${row.dataset.backend}`);
    scrub.setAttribute("aria-valuetext", `Line ${row.dataset.line}, ${status}`);
  }

  let timer = null;
  function stop() {
    clearTimeout(timer);
    timer = null;
  }
  function play() {
    stop();
    let i = 0;
    const step = () => {
      scrub.value = String(i);
      show(i);
      if (i < fail) {
        i += 1;
        timer = setTimeout(step, i === fail ? 900 : 520);
      } else {
        timer = null;
      }
    };
    step();
  }

  scrub.addEventListener("input", () => {
    stop();
    show(Number(scrub.value));
  });
  replay.addEventListener("click", play);

  if (reduced) {
    scrub.value = String(fail);
    show(fail);
  } else {
    // Play once, the first time the audit is on screen.
    const watcher = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          watcher.disconnect();
          play();
        }
      },
      { threshold: 0.35 },
    );
    watcher.observe(run);
  }
}
