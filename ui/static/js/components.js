// Web Awesome component registration.
//
// The components are vendored (see ui/vendor_webawesome.py) rather than loaded
// from Web Awesome's CDN, so the app keeps working offline and still needs no
// build step.  Only the components the UI actually renders are imported:
// `dist-cdn` shares a single copy of Lit across all of them through
// content-hashed chunks, so importing one never duplicates it, but there is no
// reason to download the ones we do not use.
//
// Deliberately absent: <wa-badge>.  The auditor used to render a status pill
// and a backend pill on every row, which made eight passing steps as loud as
// the one that failed.  Status is now typographic (see styles.css), so the
// component is not vendored at all.
//
// NOTE: the app's own icons are plain inline <svg>, never <wa-icon>.
//
// Two independent reasons.  A `name` icon fetches from ka-f.fontawesome.com at
// runtime, because the package ships no SVG assets of its own -- which would
// break the no-cross-origin-requests rule this app is built on.  And a slotted
// <svg> is not a substitute: <wa-icon>'s shadow root is a single empty
// <svg part="svg"> with no <slot>, since it renders only from `name`/`src`, so
// a slotted icon stays 0x0 and paints nothing.  A plain <svg> inside
// <wa-button> lands in the button's label slot and just works.
//
// `icon.js` is still imported below regardless: <wa-dialog> (its close button)
// and several other components create <wa-icon library="system"> elements of
// their own, and the custom element has to be defined for those to render.
// Their glyphs are embedded data: URIs, so they make no requests.

import { setBasePath } from "../vendor/webawesome/webawesome.js";

import "../vendor/webawesome/components/button/button.js";
import "../vendor/webawesome/components/dialog/dialog.js";
import "../vendor/webawesome/components/dropdown/dropdown.js";
import "../vendor/webawesome/components/dropdown-item/dropdown-item.js";
import "../vendor/webawesome/components/input/input.js";
import "../vendor/webawesome/components/icon/icon.js";
import "../vendor/webawesome/components/popup/popup.js";
import "../vendor/webawesome/components/spinner/spinner.js";
import "../vendor/webawesome/components/switch/switch.js";
import "../vendor/webawesome/components/toast/toast.js";
import "../vendor/webawesome/components/toast-item/toast-item.js";
import "../vendor/webawesome/components/tooltip/tooltip.js";

// Components resolve their assets relative to a base path.  Self-hosting means
// telling them where that is instead of letting them guess.
setBasePath("/static/vendor/webawesome");
