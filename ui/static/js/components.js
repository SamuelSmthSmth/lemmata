// Web Awesome component registration.
//
// The components are vendored (see ui/vendor_webawesome.py) rather than loaded
// from Web Awesome's CDN, so the app keeps working offline and still needs no
// build step.  Only the components the UI actually renders are imported:
// `dist-cdn` shares a single copy of Lit across all of them through
// content-hashed chunks, so importing one never duplicates it, but there is no
// reason to download the ones we do not use.
//
// NOTE: never use the `name` attribute on <wa-icon>.  Web Awesome's default
// icon library is Font Awesome and it fetches each icon from
// ka-f.fontawesome.com at runtime -- the package ships no SVG assets of its
// own.  Slot an inline <svg> instead, which is what dom.js does.  This was
// verified with a network probe: a named <wa-icon> makes a cross-origin
// request, a slotted one makes none.  <wa-select> and <wa-option> are safe as
// they are, because their internal caret and checkmark are embedded data: URIs.

import { setBasePath } from "../vendor/webawesome/webawesome.js";

import "../vendor/webawesome/components/badge/badge.js";
import "../vendor/webawesome/components/button/button.js";
import "../vendor/webawesome/components/dialog/dialog.js";
import "../vendor/webawesome/components/icon/icon.js";
import "../vendor/webawesome/components/option/option.js";
import "../vendor/webawesome/components/popup/popup.js";
import "../vendor/webawesome/components/select/select.js";
import "../vendor/webawesome/components/spinner/spinner.js";
import "../vendor/webawesome/components/switch/switch.js";
import "../vendor/webawesome/components/toast/toast.js";
import "../vendor/webawesome/components/toast-item/toast-item.js";
import "../vendor/webawesome/components/tooltip/tooltip.js";

// Components resolve their assets relative to a base path.  Self-hosting means
// telling them where that is instead of letting them guess.
setBasePath("/static/vendor/webawesome");
