import { css } from "../color.js";
import { esc, popShort } from "../format.js";
import { isCapital } from "../world.js";
import { yieldGrid, amenities, industries, gdpRow, popLine, growthSpan, showPanel } from "./infoPanel.js";

// What an okrug panel says when the office publishes no figures for it (in the office's own words).
const NO_FIGURES = "Republički zavod za statistiku ne objavljuje brojke za Kosovo i Metohiju: od 1999. godine bez podataka za AP Kosovo i Metohiju.";

/**
 * Opens the panel for state `idx` (index into world.json states / states.json).
 * ctx: {w, nation, states (states.json or null), cities, onClose, onPedia, onCity(city)}
 */
export function openStatePanel(idx, ctx) {
  const { w, nation } = ctx;
  const n = nation.nation;
  const geo = w.raw.states[idx] || {};
  // states.json is in the same order as world.json states; fall back to matching by fips.
  let st = ctx.states?.[idx];
  if (st && geo.fips && st.fips && st.fips !== geo.fips) st = ctx.states.find((s) => s.fips === geo.fips);
  st = st || { ...geo };
  const name = st.name || geo.name || "Okrug";
  const abbr = st.abbr || geo.abbr || "";
  // A city names its okruzi by their abbreviation or by the code they carry in `fips`.
  const code = st.fips || geo.fips || "";
  // Ranks compare the areas that have them: the office publishes no figures for Kosovo and Metohija, so its okruzi
  // are on the map but not ranked.
  const count = ctx.states?.filter((s) => s.ranks).length || w.raw.states.length;

  const cities = (ctx.cities || []).filter((c) => (c.states || []).some((x) => x === abbr || (code && x === code))).slice(0, 8);
  const cityRows = cities.length
    ? `<div class="city-list">${cities
        .map((c) => {
          const multi = (c.states || []).length > 1 ? `<span class="muted"> · ${esc(c.states.join("–"))}</span>` : "";
          return `<button class="city-row" data-city="${esc(c.id)}" title="${esc(c.full || c.name)}">
            <span class="cr-name">${isCapital(c) ? "★ " : ""}${esc(c.name)}${multi}</span>
            <span class="cr-pop">${popShort(c.population)}</span><span class="cr-go" aria-hidden="true">›</span></button>`;
        })
        .join("")}</div>`
    : `<p class="muted">U ovom okrugu nema gradova sa podacima.</p>`;

  const hasEcon = st.population != null || st.yields;
  showPanel({
    kind: "state",
    stripe: css(w.stateColor[idx] || [190, 190, 190]),
    title: name,
    sub: [esc(abbr), geo.fips ? `šifra ${esc(geo.fips)}` : ""].filter(Boolean).join(" · "),
    headExtra: hasEcon ? popLine(st, growthSpan(st, n)) : "",
    sections: [
      st.yields && { title: "Prinosi · rang među okruzima", html: `<div class="yield-grid">${yieldGrid(nation, st.yields, st.ranks, count)}</div>` },
      hasEcon && { title: "Zaposlenost i zarade", html: amenities(st, n) + gdpRow(st) },
      st.jobs && { title: "Najvažnije delatnosti · gde ljudi rade", html: industries(st, nation, 8) },
      { title: "Najveći gradovi", html: cityRows },
      // With states.json on the site, an okrug without figures is one the office publishes none for.
      !hasEcon && { title: "Podaci", html: `<p class="muted">${ctx.states ? NO_FIGURES : "Statistika okruga nije u ovom izdanju podataka (nedostaje states.json)."}</p>` },
    ],
    foot: `Izvor: ${esc(nation.vintage)}${nation.gdp_vintage ? `; BDP: ${esc(nation.gdp_vintage)}` : ""}. Rangovi su među ${count} okruzima sa podacima (1 = najveći).`,
    onClose: ctx.onClose,
    onPedia: ctx.onPedia,
    wire(panel) {
      panel.querySelectorAll("[data-city]").forEach((b) => {
        b.onclick = () => {
          const c = ctx.cities.find((x) => x.id === b.dataset.city);
          if (c) ctx.onCity(c);
        };
      });
    },
  });
}
