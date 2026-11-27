import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveLensValues } from './lensValues.js';

const world = {owner: [0, 0, 0, -1, -2, 1, 1], county: [0, 1, 0, 0, 1, 2, -1],
  counties: [{geoid:'70001'}, {geoid:'70002'}, {geoid:'90001'}, {geoid:'70003'}],
  elev: [100, 0, 200, null, null, 300, null], cover: [1, 7, 1, null, null, 2, null]};
const data = {version: 2, municipality_ids: ['70001','70002','90001','70003'], values: {x: [0, 42, null, 17]}};

test('municipality values map to owned hexes and preserve zero and missing values', () => {
  assert.deepEqual(resolveLensValues({value_source:{kind:'municipality', key:'x'}}, world, data), [0,42,0,null,null,null,null]);
});
test('inconsistent ids or value lengths are rejected', () => {
  const lens = {value_source:{kind:'municipality', key:'x'}};
  assert.throws(() => resolveLensValues(lens, world, {...data, municipality_ids:[...data.municipality_ids].reverse()}), /IDs/);
  assert.throws(() => resolveLensValues(lens, world, {...data, values:{x:[0]}}), /values/);
  assert.throws(() => resolveLensValues(lens, world, null), /nisu učitani/); // the file itself is missing
});
test('physical lenses cover Kosovo and categories map to legend indices', () => {
  assert.deepEqual(resolveLensValues({value_source:{kind:'world',field:'elev'}}, world), [100,0,200,null,null,300,null]);
  assert.deepEqual(resolveLensValues({value_source:{kind:'world',field:'cover',categoryValues:{1:0,2:1,7:2}}}, world), [0,2,0,null,null,1,null]);
});
