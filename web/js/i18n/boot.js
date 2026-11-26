// Decides the script of this page before anything is drawn. index.html loads this module first, right after the
// stylesheet, and main.js imports it too, so it always runs before the app; like every module it runs only once.
import { initialScript, installScriptToggle, watchDom, STORAGE_KEY } from "./index.js";

let stored = null;
try {
  stored = localStorage.getItem(STORAGE_KEY);
} catch {
  /* storage blocked (private mode, a sandbox): the browser's language decides */
}
// <html data-script="lat" | "cyr">: getScript() reads it, and so can a stylesheet or a test.
document.documentElement.dataset.script = initialScript({ hash: location.hash, stored, language: navigator.language });
installScriptToggle(document.getElementById("btn-script"));
// The page as already parsed is transliterated here as well, so a Cyrillic visit never shows Latin first.
watchDom();
