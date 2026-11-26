import { test } from "node:test";
import assert from "node:assert/strict";
import { createHashState } from "./api.js";

test("writing a map view preserves the selected script in a shared link", () => {
  const previous = { window: globalThis.window, location: globalThis.location, history: globalThis.history, document: globalThis.document };
  const location = { hash: "#lens=income&script=cyr", pathname: "/", search: "" };
  const writes = [];
  globalThis.location = location;
  globalThis.window = { addEventListener() {} };
  globalThis.history = {
    pushState(_state, _title, url) { writes.push(url); location.hash = url.slice(url.indexOf("#")); },
    replaceState(_state, _title, url) { writes.push(url); location.hash = url.slice(url.indexOf("#")); },
  };
  try {
    const state = createHashState({ read: () => ({ lens: "relief", at: [1, 2, 0.5] }), apply() {} });
    state.flush();
    assert.equal(writes[0], "/#lens=relief&at=1,2,0.5&script=cyr");
    // A Cyrillic browser or stored preference can select the script without a hash parameter.
    location.hash = "#lens=income";
    globalThis.document = { documentElement: { dataset: { script: "cyr" } } };
    state.flush();
    assert.equal(writes[1], "/#lens=relief&at=1,2,0.5&script=cyr");
    assert.throws(() => state.register("script", { get() {}, set() {} }), /reserved/);
  } finally {
    Object.assign(globalThis, previous);
  }
});
