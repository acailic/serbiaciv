// Keyboard & mouse cheat-sheet.
import { icon } from "../ui/icon.js";

const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
const MOD = isMac ? "⌘" : "Ctrl";

const ROWS = [
  ["Pomeranje", [
    [["Prevlačenje", "←↑→↓", "WASD"], "Pomeranje mape"],
    [["Točkić", "+", "–"], "Uvećavanje i umanjenje"],
    [["Dvostruki klik"], "Uvećanje prikaza na odabrano mesto"],
    [["Dva prsta"], "Stiskanje za uvećanje, prevlačenje za pomeranje (dodir)"],
    [["Minimapa"], "Klik ili prevlačenje za skok na mesto"],
  ]],
  ["Istraživanje", [
    [["Klik na grad"], "Otvara panel grada"],
    [["Klik na kopno"], "Otvara taj okrug"],
    [["/", `${MOD} K`], "Pretraga gradova i okruga"],
    [["L", "Shift L"], "Sledeće / prethodno sočivo"],
    [["Legenda"], "Priđite kursorom ili prevucite skalu da prikažete samo taj opseg"],
    [["R"], "Prikaži ili sakrij resurse"],
  ]],
  ["Paneli", [
    [["?"], "Ova pomoć"],
    [["Esc"], "Zatvori pomoć, pretragu, Almanah, pa panel"],
  ]],
];

export function initHelp() {
  const modal = document.getElementById("help");
  if (!modal) return { open() {}, close() {}, get isOpen() { return false; } };
  const card = modal.querySelector(".help-card");
  let restore = null;
  card.innerHTML = `
    <button class="icon-btn help-close" data-close aria-label="Zatvori pomoć">${icon("close", "✕", { size: 13 })}</button>
    <h2 id="help-title">${icon("help", "?", { size: 22 })}<span>Upravljanje</span></h2>
    <div class="help-cols">${ROWS.map(([title, rows]) => `
      <section><h3>${title}</h3>${rows.map(([keys, what]) => `
        <div class="help-row"><span class="keys">${keys.map((k) => `<kbd>${k}</kbd>`).join("")}</span><span>${what}</span></div>`).join("")}
      </section>`).join("")}</div>
    <p class="help-foot">Svaki broj se može pratiti do javnog izvora: otvorite <b>Almanah</b>. Veza u adresnoj traci uvek ponovo
      otvara ovaj prikaz. Izvorni kod: <a href="serbiaciv-source.zip" download>serbiaciv-source.zip</a> (MIT; pokrenite ga sa uv, pogledajte README).</p>`;

  const close = () => {
    if (modal.hidden) return;
    modal.hidden = true;
    if (restore && document.contains(restore)) restore.focus();
    restore = null;
  };
  modal.addEventListener("click", (e) => {
    if (e.target === modal || e.target.closest("[data-close]")) close();
  });
  modal.addEventListener("keydown", (e) => {
    if (e.key !== "Tab") return;
    e.preventDefault(); // the only focusable control is the close button
    card.querySelector("[data-close]").focus();
  });

  return {
    open() {
      if (!modal.hidden) return;
      restore = document.activeElement;
      modal.hidden = false;
      card.querySelector("[data-close]").focus();
    },
    close,
    toggle() { modal.hidden ? this.open() : close(); },
    get isOpen() { return !modal.hidden; },
  };
}
