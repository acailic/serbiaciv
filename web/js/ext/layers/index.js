// Map-art extension: tile improvements (motorways and major roads, railroads, river ports, airports) and wonders
// with protected land, each as a static layer drawn into the cached map (nothing animates; an idle map draws no
// frames), with a switch in the "Mapa" menu. Serbia publishes no military or freight-trade data, so upstream's
// military and trade layers have no switch here and are never loaded (their drawing code stays dormant).
//
// Data: infrastructure.json and wonders.json (loaded eagerly by main.js right after the first frame; app.loadData
// returns the same promise). A missing file (null) leaves its layers off and their switches harmless. Defaults:
// roads, rail, ports & airports and wonders on (roads, rail and hubs only from the region view in: see each layer's
// minRpx).
import { createModel } from "./model.js";
import { makeLayers } from "./layers.js";
import { tips } from "./tips.js";

const TOGGLES = [
  { id: "roads", label: "Putevi", icon: "t-road", def: true, title: "Auto-putevi i glavni putevi", layers: ["roads"] },
  { id: "rail", label: "Pruge", icon: "t-rail", def: true, title: "Glavne i sekundarne pruge", layers: ["rail"] },
  { id: "hubs", label: "Luke i aerodromi", icon: "d-harbor", def: true, title: "Rečne luke i aerodromi na karti", layers: ["hubs"] },
  { id: "wonders", label: "Čuda", icon: "w-landmark", def: true, title: "Nacionalni parkovi, univerziteti i znamenitosti", layers: ["wonders", "protected", "plates"] },
];

export function install(app) {
  const model = createModel(app.w);
  const on = Object.fromEntries(TOGGLES.map((t) => [t.id, t.def]));
  const layers = makeLayers(model, on, { tips, app });
  for (const l of layers) app.registerStaticLayer(l);

  for (const t of TOGGLES) {
    app.ui.addMapToggle({
      id: t.id, label: t.label, icon: t.icon, title: t.title, default: t.def,
      get: () => on[t.id],
      set: (v) => {
        on[t.id] = !!v;
        app.requestDraw();
      },
    });
  }

  const apply = (name, data) => {
    model.setData(name, data);
    app.requestDraw();
  };
  for (const name of ["infrastructure", "wonders"]) {
    if (app.data[name] !== undefined) apply(name, app.data[name]);
    else app.loadData(name).then((d) => apply(name, d), (err) => console.warn(`map layers: ${name} failed to load`, err));
  }

  // For debugging and the gallery: the model and switches.
  app.mapArt = { model, on, layers };
}
