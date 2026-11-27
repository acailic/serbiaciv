/** Resolve Serbia v2 lens values lazily using the world county index.
 *
 * Municipality values are aligned to world.counties by geoid. The optional
 * categoryValues map translates raw world codes to legend category indices.
 */
export function resolveLensValues(lens, world, data) {
  const source = lens?.value_source;
  const owner = world?.owner;
  if (!source || !Array.isArray(owner)) throw new Error('Invalid lens or world');
  let values;
  if (source.kind === 'municipality') {
    // The file itself missing (a failed request) is not a mismatch: say so, or the console blames the ids.
    if (data == null) throw new Error('Podaci sočiva nisu učitani (lens-values.json)');
    if (data?.version !== 2 || !Array.isArray(data.municipality_ids) || !Array.isArray(world.counties) ||
        data.municipality_ids.length !== world.counties.length ||
        data.municipality_ids.some((id, index) => id !== world.counties[index]?.geoid)) {
      throw new Error('Municipality IDs do not match world data');
    }
    values = data.values?.[source.key];
    if (!Array.isArray(values) || values.length !== world.counties.length ||
        !Array.isArray(world.county) || world.county.length !== owner.length) {
      throw new Error('Invalid municipality lens values');
    }
    return owner.map((o, cell) => {
      const index = world.county[cell];
      return o >= 0 && Number.isInteger(index) && index >= 0 && index < values.length
        ? values[index] ?? null : null;
    });
  }
  if (source.kind === 'world' && ['elev', 'relief', 'cover'].includes(source.field)) {
    values = world[source.field];
    if (!Array.isArray(values) || values.length !== owner.length) throw new Error('Invalid world lens values');
    return owner.map((o, cell) => {
      const value = values[cell];
      if (o < 0 || value == null) return null;
      if (source.categoryValues) return Object.hasOwn(source.categoryValues, value) ? source.categoryValues[value] : null;
      return value;
    });
  }
  throw new Error('Unknown lens value source');
}
