// The desktop app: the static build of the web app (ui/build_static.py) in a
// native window.  The checker runs inside the page, in Pyodide, exactly as on
// the website, so the shell adds only what a browser would otherwise provide:
//
// - downloads (exports: .aether, .zip, .pack.json, .tex) are saved to the
//   Downloads folder under the name the page gives them, never overwriting a
//   file that is already there;
// - links that leave the app (the pack registry on GitHub) open in the
//   system browser, not inside the app's window.
//
// The page gets no access to Tauri's IPC: it is the same page the website
// serves, and needs nothing from the shell.  The only network it uses is the
// pack registry (site.json `registry`), and only when one is reachable.

use std::path::{Path, PathBuf};

use tauri::webview::{DownloadEvent, NewWindowResponse};
use tauri::{Manager, Url, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;

/// Runs in the page before its own scripts.  A link that opens a new window
/// (`target="_blank"`, `window.open`) and leaves the app becomes an ordinary
/// navigation instead, which `on_navigation` hands to the system browser.
/// Webviews disagree about new windows (WebKitGTK under automation never asks
/// the shell at all), but every one of them asks about a navigation.
const EXTERNAL_LINKS: &str = r#"
(() => {
  const outside = (href) => {
    try {
      const url = new URL(href, location.href);
      return /^(https?|mailto):$/.test(url.protocol) && url.origin !== location.origin ? url.href : null;
    } catch { return null; }
  };
  document.addEventListener("click", (event) => {
    const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
    if (!link || event.defaultPrevented || !link.target || link.target === "_self") return;
    const href = outside(link.href);
    if (!href) return;
    event.preventDefault();
    location.assign(href);
  }, true);
  const open = window.open;
  window.open = function (href, ...rest) {
    const url = outside(href ?? "");
    if (url) { location.assign(url); return null; }
    return open.call(window, href, ...rest);
  };
})();
"#;

/// The app's own pages, as the webview serves them on each platform.
fn is_app_url(url: &Url) -> bool {
    match url.scheme() {
        "tauri" | "asset" | "blob" | "data" | "about" => true,
        "http" | "https" => matches!(url.host_str(), Some("tauri.localhost") | Some("asset.localhost")),
        _ => false,
    }
}

/// `dir/name`, or `dir/stem (2).ext` and so on if that file already exists.
fn unused_path(dir: &Path, name: &str) -> PathBuf {
    let candidate = dir.join(name);
    if !candidate.exists() {
        return candidate;
    }
    // "workspace.pack.json" keeps its double extension: split at the first dot.
    let (stem, ext) = match name.find('.') {
        Some(i) if i > 0 => (&name[..i], &name[i..]),
        _ => (name, ""),
    };
    (2..)
        .map(|n| dir.join(format!("{stem} ({n}){ext}")))
        .find(|p| !p.exists())
        .expect("an unused name")
}

/// Where a download goes: the user's Downloads folder, named as the page asked.
fn download_target(app: &tauri::AppHandle, suggested: &Path) -> Option<PathBuf> {
    let dir = app.path().download_dir().ok()?;
    let name = suggested
        .file_name()
        .and_then(|n| n.to_str())
        .filter(|n| !n.is_empty())
        .unwrap_or("download");
    std::fs::create_dir_all(&dir).ok()?;
    Some(unused_path(&dir, name))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            let title = app.config().product_name.clone().unwrap_or_else(|| "Lemmata".into());
            let opener = app.handle().clone();
            let navigator = app.handle().clone();
            let downloads = app.handle().clone();
            WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title(title)
                .inner_size(1280.0, 840.0)
                .min_inner_size(480.0, 560.0)
                .initialization_script(EXTERNAL_LINKS)
                .on_navigation(move |url| {
                    if is_app_url(url) {
                        return true;
                    }
                    if matches!(url.scheme(), "http" | "https" | "mailto") {
                        let _ = navigator.opener().open_url(url.as_str(), None::<&str>);
                    }
                    false
                })
                .on_new_window(move |url, _features| {
                    if matches!(url.scheme(), "http" | "https" | "mailto") && !is_app_url(&url) {
                        let _ = opener.opener().open_url(url.as_str(), None::<&str>);
                    }
                    NewWindowResponse::Deny
                })
                .on_download(move |_webview, event| match event {
                    DownloadEvent::Requested { destination, .. } => match download_target(&downloads, destination) {
                        Some(path) => {
                            *destination = path;
                            true
                        }
                        None => false,
                    },
                    _ => true,
                })
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running the Lemmata desktop app");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn app_urls_stay_in_the_window() {
        for url in ["tauri://localhost/index.html", "http://tauri.localhost/static/js/main.js", "blob:tauri://localhost/1234"] {
            assert!(is_app_url(&Url::parse(url).unwrap()), "{url}");
        }
        for url in ["https://github.com/SamuelSmthSmth/lemmata-packs", "https://lemmata.sous.systems/", "http://localhost:8000/"] {
            assert!(!is_app_url(&Url::parse(url).unwrap()), "{url}");
        }
    }

    #[test]
    fn downloads_never_overwrite() {
        let dir = std::env::temp_dir().join(format!("lemmata-downloads-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        assert_eq!(unused_path(&dir, "proof.aether"), dir.join("proof.aether"));
        std::fs::write(dir.join("proof.aether"), "").unwrap();
        assert_eq!(unused_path(&dir, "proof.aether"), dir.join("proof (2).aether"));
        std::fs::write(dir.join("me.pack.json"), "").unwrap();
        std::fs::write(dir.join("me (2).pack.json"), "").unwrap();
        assert_eq!(unused_path(&dir, "me.pack.json"), dir.join("me (3).pack.json"));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
