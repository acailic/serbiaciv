// The page's Serbian script: which one is shown, how text reaches it, and the switch.
//
// The app and its data are written in Serbian Latin. In Cyrillic mode everything a visitor sees is converted when it
// is displayed: page text and a few attributes by watchDom() below, canvas text by the map calling script(name) where
// it draws (render/map.js, render/banners.js, ext/towns). A switch reloads the page rather than redrawing it in
// place; the URL hash carries the choice, so the same view comes back in the other script and a shared link carries it.
//
//   initialScript({ hash, stored, language })   the script a page load starts in
//   getScript()                                 "lat" | "cyr" on this page
//   script(text)                                text as shown on this page
//   setScript("lat" | "cyr")                    store the choice, put it in the hash, reload
//   installScriptToggle(button)                 the Ћир / Lat button
//   watchDom()                                  transliterate the page now and as it changes (Cyrillic mode only)
import { toCyrillic } from "./transliterate.js";
import { parseHash, withScript } from "../app/urlstate.js";

/** localStorage key of the visitor's choice ("lat" | "cyr"). */
export const STORAGE_KEY = "serbiaciv.script";

const isScript = (s) => s === "lat" || s === "cyr";

/**
 * The script a page load starts in: the hash's `script=` wins, then the choice stored by an earlier visit, then
 * Cyrillic for a browser set to Serbian unless it asks for the Latin script. Every other first visit is Latin.
 */
export function initialScript({ hash, stored, language } = {}) {
  const fromHash = parseHash(hash).script;
  if (isScript(fromHash)) return fromHash;
  if (isScript(stored)) return stored;
  const lang = String(language ?? "");
  return /^sr(?:-|$)/i.test(lang) && !/^sr-latn(?:-|$)/i.test(lang) ? "cyr" : "lat";
}

/** The script of this page, "lat" or "cyr": what boot.js put on <html data-script>. */
export function getScript() {
  return typeof document !== "undefined" && document.documentElement?.dataset?.script === "cyr" ? "cyr" : "lat";
}

/** `text` as it is shown on this page: in Cyrillic when the script is Cyrillic, as written otherwise. */
export function script(text) {
  return getScript() === "cyr" ? toCyrillic(text) : text;
}

/**
 * Switch the script: store the choice, write it into the hash, then reload. The app restores its view from the
 * hash, so the same map comes back in the other script; the map is never redrawn in place.
 */
export function setScript(s) {
  try {
    localStorage.setItem(STORAGE_KEY, s);
  } catch {
    /* storage blocked (private mode, a sandbox): the hash still carries the choice */
  }
  try {
    history.replaceState(null, "", location.pathname + location.search + withScript(location.hash, s));
  } catch {
    /* some sandboxes forbid history writes: the stored choice still decides after the reload */
  }
  location.reload();
}

/**
 * Make `button` the script switch. It names the script it changes to, "Ћир" in Latin mode and "Lat" in Cyrillic
 * mode, so its own text must never be transliterated: data-no-translit keeps watchDom() away from it.
 */
export function installScriptToggle(button) {
  if (!button) return;
  const cyr = getScript() === "cyr";
  button.type = "button";
  button.textContent = cyr ? "Lat" : "Ћир";
  button.setAttribute("data-no-translit", "");
  button.addEventListener("click", () => setScript(cyr ? "lat" : "cyr"));
}

// Text nodes and these attributes are transliterated. An input's value is the visitor's own typing, and never is.
const ATTRS = ["title", "aria-label", "alt", "placeholder"];
// Markup, keyboard keys, preformatted text and text areas keep what is written, and so does anything marked
// data-no-translit (names that stay Latin in both scripts).
const KEEP = "[data-no-translit], script, style, code, kbd, pre, textarea";

// node → the Latin its text came from; element → { attribute: the Latin it came from }.
const latinSource = new WeakMap();
let observer = null;

function transliterateText(node) {
  if (node.parentElement?.closest(KEEP)) return;
  // A node that already shows the transliteration of its source was last written here: that is this module's own
  // mutation, and acting on it again would never stop.
  if (node.data === toCyrillic(latinSource.get(node))) return;
  latinSource.set(node, node.data);
  const shown = toCyrillic(node.data);
  if (shown !== node.data) node.data = shown;
}

function transliterateAttribute(el, name) {
  if (el.closest(KEEP)) return;
  const value = el.getAttribute(name);
  if (value == null || value === toCyrillic(latinSource.get(el)?.[name])) return;
  latinSource.set(el, { ...latinSource.get(el), [name]: value });
  const shown = toCyrillic(value);
  if (shown !== value) el.setAttribute(name, shown);
}

/** Transliterate an element, its attributes and everything below it, skipping what must stay as written. */
function transliterateTree(el) {
  if (el.closest(KEEP)) return;
  for (const name of ATTRS) if (el.hasAttribute(name)) transliterateAttribute(el, name);
  for (const child of el.childNodes) {
    if (child.nodeType === 3) transliterateText(child);
    else if (child.nodeType === 1) transliterateTree(child);
  }
}

/**
 * In Cyrillic mode: transliterate the page as it is now, and everything added or changed later. Called once, by
 * boot.js, before anything is drawn. Does nothing in Latin mode.
 */
export function watchDom() {
  if (observer || getScript() !== "cyr" || typeof document === "undefined" || typeof MutationObserver !== "function") return;
  transliterateTree(document.documentElement);
  observer = new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === "characterData") transliterateText(r.target);
      else if (r.type === "attributes") transliterateAttribute(r.target, r.attributeName);
      else for (const n of r.addedNodes) {
        if (n.nodeType === 1) transliterateTree(n);
        else if (n.nodeType === 3) transliterateText(n);
      }
    }
  });
  observer.observe(document, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}
