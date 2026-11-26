import { resolveLensValues } from "./lensValues.js";

/** Lazily fetch and cache municipal values; a failed request can be tried again. */
export function createLensLoader(world, fetchValues) {
  let indexed = null;
  return async (lens) => {
    if (Array.isArray(lens?.values)) return lens.values;
    if (lens?.value_source?.kind === "world") return resolveLensValues(lens, world);
    if (lens?.value_source?.kind !== "municipality" || lens.value_source.file !== "lens-values.json") {
      throw new Error("Nepoznat izvor podataka za sočivo");
    }
    if (!indexed) {
      indexed = Promise.resolve().then(fetchValues).catch((error) => { indexed = null; throw error; });
    }
    try {
      return resolveLensValues(lens, world, await indexed);
    } catch (error) {
      indexed = null;
      throw error;
    }
  };
}
