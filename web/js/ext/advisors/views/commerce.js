// Saobraćaj i veze („Majstor puteva“): luke i aerodromi sa prevozom (infrastructure.json) i mreža puteva i pruga.
// Za Srbiju nema javnih podataka o tokovima robe između opština, pa tabla o trgovinskim putevima izostavlja.
import { esc, fin, el as mk } from "../core/util.js";
import { int, count3, signedPct } from "../core/fmt.js";
import { barList, stackedBars, swatchLegend, sizeLegend } from "../core/charts.js";
import { section, tiles, segmented, sourcesHtml } from "../core/view.js";
import { focusPoint } from "../core/frame.js";
import { KIM_NOTE } from "../core/notes.js";

const PORT_COLOR = "#4f9ad6", AIR_COLOR = "#e6cf86";

/** Passengers of an airport in the file's own field (upstream: enplanements; a Serbian file may say passengers). */
export const paxOf = (a) => a?.enplanements ?? a?.passengers ?? null;
export const paxPrevOf = (a) => a?.enplanements_prev ?? a?.passengers_prev ?? null;
/** Cargo of an airport: {v, unit} from cargo_lbs / cargo_t / cargo_kg, or null. */
export function cargoOf(a) {
  if (fin(a?.cargo_lbs)) return { v: a.cargo_lbs, unit: "lb" };
  if (fin(a?.cargo_t)) return { v: a.cargo_t, unit: "t" };
  if (fin(a?.cargo_kg)) return { v: a.cargo_kg, unit: "kg" };
  return null;
}

/** Counts of hex links per class / tier: roads and rail are [a, b, class] triples in the upstream shape. */
export function linkCounts(list) {
  const out = [];
  for (const r of list || []) { const c = r[2] | 0; out[c] = (out[c] || 0) + 1; }
  return out;
}

export async function mount(ctx) {
  const { app, el, link, data } = ctx;
  const infra = await app.loadData?.("infrastructure").catch(() => null);
  const NO_FREIGHT = "Tabla o tokovima robe između opština izostavljena je: za Srbiju nema javnih podataka o tome šta se, odakle i dokle prevozi (kao što u SAD objavljuje FAF).";
  if (!infra) {
    el.innerHTML = `<p class="adv-empty pad">Datoteka infrastructure.json još nije uključena: luke, aerodromi, putevi i pruge biće prikazani iz nje.</p>${sourcesHtml(data, [], [NO_FREIGHT, "Dok mreža saobraćajnica nije uključena, ovaj savetnik nema šta da prikaže."])}`;
    return {};
  }
  const v = infra.vintage || {};
  const ports = (infra.ports || []).map((p) => ({ ...p, key: `p${p.id}` }));
  const airports = (infra.airports || []).map((a) => ({ ...a, key: `a${a.id}` }));
  const pax = airports.filter((a) => fin(paxOf(a))).sort((a, b) => paxOf(b) - paxOf(a));
  const topAir = pax[0], topPort = (infra.ports || [])[0];
  const tonsPorts = ports.filter((p) => fin(p.tons));

  // --- headline -------------------------------------------------------------------------------------------------
  el.insertAdjacentHTML("beforeend", tiles([
    { label: "Aerodromi", value: int(airports.length), sub: `${int(pax.length)} sa objavljenim prevozom putnika${v.airports ? ` · ${esc(v.airports)}` : ""}` },
    { label: "Najprometniji aerodrom", value: topAir ? count3(paxOf(topAir)) : "–", sub: topAir ? `${topAir.name}${topAir.city ? ` (${topAir.city})` : ""}${fin(topAir.year) ? ` · ${int(topAir.year)}.` : ""}` : "nema objavljenih podataka o putnicima", color: AIR_COLOR },
    { label: "Luke", value: int(ports.length), sub: tonsPorts.length ? `${esc(topPort?.name || "")} najprometnija · ${count3(topPort.tons)} t` : "rečne i jezerske luke; tonaža nije objavljena", color: PORT_COLOR },
  ]) + `<p class="adv-callout">${esc(NO_FREIGHT)}</p>`);

  let portBars = null, airBars = null, portBubbles = null, airBubbles = null;

  // --- ports ------------------------------------------------------------------------------------------------------
  const pBody = section(el, { title: "Luke", kicker: esc(v.ports || ""), note: `${esc(infra.rules?.ports || "Luke su prikazane kako su izabrane za kartu.")}${tonsPorts.length ? " Tonaža je podeljena na unutrašnji, uvozni i izvozni prevoz." : ""}` });
  const PK = [{ key: "domestic", label: "Unutrašnji prevoz", color: "#8fcbb8" }, { key: "imports", label: "Uvoz", color: "#4f9ad6" }, { key: "exports", label: "Izvoz", color: "#d9a457" }];
  const portHover = (p) => {
    link.hover(p ? { cells: new Set(p.cell != null ? [p.cell] : []), label: p.name } : null);
    portBubbles?.setHot(p ? p.key : null);
  };
  if (tonsPorts.length) {
    portBars = stackedBars(pBody, {
      rows: ports.slice(0, 15).map((p) => ({ key: p.key, label: p.name, sub: p.state, parts: { domestic: p.domestic, imports: p.imports, exports: p.exports }, total: p.tons, text: `${count3(p.tons)} t` })),
      keys: PK, fmt: (x) => `${count3(x)} t`, ariaLabel: "Najprometnije luke po tonaži",
      onHover: (x) => portHover(x ? ports.find((p) => p.key === x.row.key) : null),
      onClick: (x) => flyTo(ports.find((p) => p.key === x.row.key)),
    });
    pBody.insertAdjacentHTML("beforeend", swatchLegend(PK) + `<p class="adv-note">Prvih 15 od ${int(ports.length)} luka sa objavljenom tonažom.</p>`);
  } else {
    portBars = barList(pBody, {
      ariaLabel: "Luke na karti",
      rows: ports.map((p) => ({ key: p.key, label: p.name, sub: p.state || "", value: null, text: "–", color: PORT_COLOR, full: p.name })),
      onHover: (r) => portHover(r ? ports.find((p) => p.key === r.key) : null),
      onClick: (r) => flyTo(ports.find((p) => p.key === r.key)),
    });
    pBody.insertAdjacentHTML("beforeend", `<p class="adv-note">${int(ports.length)} luka na karti. Tonaža prevoza nije javno objavljena po lukama, pa se luke ne rangiraju („–“ znači da podatka nema).</p>`);
  }

  // --- airports ---------------------------------------------------------------------------------------------------
  const aBody = section(el, { title: "Aerodromi", kicker: esc(v.airports || ""), note: esc(infra.rules?.airports || "Aerodromi su prikazani kako su izabrani za kartu.") });
  let aMode = "pax";
  const aHost = mk("div");
  segmented(aBody, { label: "Poređaj po", value: aMode, options: [{ value: "pax", label: "Putnici" }, { value: "cargo", label: "Teret" }], onChange: (x) => { aMode = x; drawAir(); } });
  aBody.appendChild(aHost);
  const airHover = (a) => {
    link.hover(a ? { cells: new Set(a.cell != null ? [a.cell] : []), label: `${a.id ? `${a.id} · ` : ""}${a.name}` } : null);
    airBubbles?.setHot(a ? a.key : null);
  };
  function drawAir() {
    aHost.innerHTML = "";
    const list = (aMode === "pax" ? airports.filter((a) => fin(paxOf(a))).sort((a, b) => paxOf(b) - paxOf(a)) : airports.filter((a) => cargoOf(a)).sort((a, b) => cargoOf(b).v - cargoOf(a).v)).slice(0, 15);
    airBars = barList(aHost, {
      rank: true, ariaLabel: aMode === "pax" ? "Najprometniji aerodromi po broju putnika" : "Najprometniji aerodromi po teretu",
      rows: list.map((a) => {
        const ch = aMode === "pax" && fin(paxPrevOf(a)) && paxPrevOf(a) > 0 ? paxOf(a) / paxPrevOf(a) - 1 : null;
        const cg = cargoOf(a);
        return {
          key: a.key, label: a.city ? `${a.id ? `${a.id} ` : ""}${a.city}` : a.name, full: a.name, value: aMode === "pax" ? paxOf(a) : cg.v,
          text: aMode === "pax" ? count3(paxOf(a)) : `${count3(cg.v)} ${cg.unit}`,
          sub: aMode === "pax" ? (fin(ch) ? `${signedPct(ch)} prema ${int(a.year) - 1}.` : "") : `${a.state || ""}`,
          tone: fin(ch) ? (ch >= 0 ? "good" : "bad") : undefined, color: AIR_COLOR,
        };
      }),
      onHover: (r) => airHover(r ? airports.find((a) => a.key === r.key) : null),
      onClick: (r) => flyTo(airports.find((a) => a.key === r.key)),
    });
    aHost.insertAdjacentHTML("beforeend", `<p class="adv-note">${aMode === "pax" ? "Prevezeni putnici u toku godine; promena prema godini ranije." : `Težina pristiglog tereta, kako je objavljena (${list[0] ? cargoOf(list[0]).unit : "t"}).`}</p>`);
    if (!list.length) aHost.insertAdjacentHTML("beforeend", `<p class="adv-empty">Nijedan aerodrom nema objavljen ${aMode === "pax" ? "broj putnika" : "teret"}.</p>`);
  }
  drawAir();

  // --- on the map -------------------------------------------------------------------------------------------------
  const mBody = section(el, { title: "Na karti" });
  let show = "both";
  segmented(mBody, {
    label: "Prikaži", value: show,
    options: [{ value: "both", label: "Luke i aerodromi" }, { value: "ports", label: "Luke" }, { value: "air", label: "Aerodromi" }, { value: "none", label: "Bez oznaka" }],
    onChange: (x) => { show = x; drawSites(); },
  });
  const sizeBox = mk("div");
  mBody.appendChild(sizeBox);
  portBubbles = ctx.bubbles("ports", {
    rMax: 20, alpha: 0.5,
    tip: (b) => `<b>${esc(b.it.name)}</b><br>Luka${fin(b.it.tons) ? ` · <b>${count3(b.it.tons)} t</b>${fin(b.it.year) ? ` (${int(b.it.year)})` : ""}` : " · tonaža nije objavljena"}${fin(b.it.rank) ? ` · ${int(b.it.rank)}. po tonaži` : ""}${fin(b.it.domestic) || fin(b.it.imports) || fin(b.it.exports) ? `<br><span class="sub">unutrašnji ${fin(b.it.domestic) ? count3(b.it.domestic) : "–"} · uvoz ${fin(b.it.imports) ? count3(b.it.imports) : "–"} · izvoz ${fin(b.it.exports) ? count3(b.it.exports) : "–"}</span>` : ""}`,
    onHover: (b) => portBars?.setHot(b ? b.key : null),
    onClick: (b) => { portBars?.setHot(b.key); flyTo(b.it); },
  });
  airBubbles = ctx.bubbles("airports", {
    rMax: 16, alpha: 0.5,
    tip: (b) => `<b>${esc(b.it.id ? `${b.it.id} · ` : "")}${esc(b.it.name)}</b><br>${esc(infra.hubs?.[b.it.hub] || "Aerodrom")} · <b>${fin(paxOf(b.it)) ? count3(paxOf(b.it)) : "–"}</b> putnika${cargoOf(b.it) ? `<br><span class="sub">teret ${count3(cargoOf(b.it).v)} ${cargoOf(b.it).unit}</span>` : ""}`,
    onHover: (b) => airBars?.setHot(b ? b.key : null),
    onClick: (b) => { airBars?.setHot(b.key); flyTo(b.it); },
  });
  function drawSites() {
    const pMax = Math.max(1, ...ports.map((p) => p.tons || 0)), aMax = Math.max(1, ...airports.map((a) => paxOf(a) || 0));
    // Ports without a published tonnage get a small fixed circle: the size carries no data and the tip says so.
    portBubbles.set(show === "both" || show === "ports" ? ports.filter((p) => fin(p.x) && fin(p.y)).map((p) => ({ key: p.key, x: p.x, y: p.y, value: fin(p.tons) ? p.tons : pMax / 400, color: PORT_COLOR, it: p })) : [], { vMax: pMax });
    airBubbles.set(show === "both" || show === "air" ? airports.filter((a) => fin(paxOf(a)) && fin(a.x) && fin(a.y)).map((a) => ({ key: a.key, x: a.x, y: a.y, value: paxOf(a), color: AIR_COLOR, it: a })) : [], { vMax: aMax });
    sizeBox.innerHTML = (show === "both" || show === "ports" ? (tonsPorts.length ? sizeLegend([pMax / 100, pMax / 10, pMax].filter((x, i, arr) => arr.indexOf(x) === i), (x) => 20 * Math.sqrt(x / pMax), (x) => `${count3(x)} t`, "Luke (plavo): tonaža") : "") + (ports.some((p) => !fin(p.tons)) ? `<p class="adv-note">Luke bez objavljene tonaže nacrtane su kao maleni krugovi iste veličine.</p>` : "") : "")
      + ((show === "both" || show === "air") && pax.length ? sizeLegend([aMax / 100, aMax / 10, aMax].filter((x, i, arr) => arr.indexOf(x) === i), (x) => 16 * Math.sqrt(x / aMax), (x) => count3(x), "Aerodromi (zlatno): putnici") : "");
  }
  drawSites();

  // --- roads and rail: the counts and rules (the map-art layers draw them; switches live in the Map menu). -----------
  const nRoad = linkCounts(infra.roads), nRail = linkCounts(infra.rail);
  const toggles = (() => { try { return app.ui.mapToggles?.() || []; } catch { return []; } })();
  const nBody = section(el, { title: "Putevi i pruge", note: "Dužina mreže izražena brojem veza između susednih hekseva (heks od 5 km), po klasi puta, odnosno po redu pruge. Putevi i pruge su crtež karte, ne statistika.", open: false });
  nBody.innerHTML = `<p class="adv-note">${(infra.road_classes || []).map((c, i) => `<b>${esc(c.name)}</b>: ${int(nRoad[i] || 0)} veza između hekseva`).join(" · ") || "Putevi nisu uključeni u datoteku."}<br>${(infra.rail_tiers || []).map((c, i) => `<b>${esc(c.name)}</b>: ${int(nRail[i] || 0)} veza između hekseva`).join(" · ") || "Pruge nisu uključene u datoteku."}</p>
    ${infra.rules?.roads ? `<p class="adv-note">${esc(infra.rules.roads)}</p>` : ""}${infra.rules?.rail ? `<p class="adv-note">${esc(infra.rules.rail)}</p>` : ""}
    ${toggles.length ? `<p class="adv-note">Crtež puteva, pruga i saobraćajnica uključujete i isključujete iz menija <b>Mapa</b>, pored sloja Resursi.</p>` : ""}`;

  el.insertAdjacentHTML("beforeend", sourcesHtml(data, [...(infra.sources || [])], [
    NO_FREIGHT,
    "Putevi i pruge su crtež karte (OpenStreetMap), a ne statistika: pojednostavljene trase bez podataka o propusnosti ili prometu.",
    "Prevezeni putnici odnose se na godinu navedenu u izdanju podataka; aerodromi bez objavljenog broja putnika ne rangiraju se.",
    KIM_NOTE,
  ]));

  function flyTo(p) {
    if (!p || !fin(p.x) || !fin(p.y)) return;
    focusPoint(app, p.x, p.y, Math.min(app.cam.maxScale, Math.max(app.cam.scale, (app.cam.fitScale || 1) * 3)));
  }

  return {
    onMapHover(h) {
      if (h.item?.kind === "port") portBars?.setHot(`p${h.item.data?.id}`);
      if (h.item?.kind === "airport") airBars?.setHot(`a${h.item.data?.id}`);
    },
    onMapClick(ev) {
      if (ev.item?.kind === "port" || ev.item?.kind === "airport") { flyTo(ev.item.data); return true; }
      return false;
    },
  };
}
