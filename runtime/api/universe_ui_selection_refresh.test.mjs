import assert from "node:assert/strict";
import test from "node:test";
import { mountUniverseApp } from "../../packages/yoke-core/src/yoke_core/ui/static/app.js";
import { createProjectSelection, resolveProjectSelection } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_project_selection.js";
import { scopeForEntry, navEntry } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_navigation.js";
import { FakeDocument, response, settle } from "./universe_ui_dom_test_support.mjs";
import { twoProjectClient, scopeChips } from "./universe_ui_read_views_test_support.mjs";
const projects = [{ id: 1 }, { id: 2 }];
const ok = (result) => ({ status: 200, envelope: { success: true, result } });
async function mount(t, href, state) {
  const base = twoProjectClient();
  const client = { requests: base.requests, async call(request) {
    if (request.function === "ui_preferences.screen_selection.list") return ok(state);
    if (request.function === "ui_preferences.screen_selection.set") {
      base.requests.push(request);
      const { view_id, selection, focus, location } = request.payload;
      if (location !== undefined) state.last_location = location;
      else state.views[view_id] = { selection, focus };
      return ok({});
    }
    return base.call(request);
  } };
  t.mock.method(globalThis, "fetch", () => response(200, {}));
  const documentNode = new FakeDocument();
  const windowNode = documentNode.defaultView;
  windowNode.location.href = href;
  windowNode.fetch = () => response(503, {});
  const events = new EventTarget();
  documentNode.addEventListener = events.addEventListener.bind(events);
  documentNode.removeEventListener = events.removeEventListener.bind(events);
  documentNode.dispatchEvent = events.dispatchEvent.bind(events);
  windowNode.history = {
    replaceState(_s, _t, route) { windowNode.location.href = route; },
    pushState(_s, _t, route) { windowNode.location.href = route; },
  };
  const root = documentNode.createElement("div");
  const app = mountUniverseApp(root, { client });
  t.after(() => app.unmount());
  await settle();
  return { root, windowNode, documentNode, client, app };
}
const selectionWrites = (client) => client.requests.filter((r) =>
  r.function === "ui_preferences.screen_selection.set" && r.payload.location === undefined);
const selected = (root) => scopeChips(root).filter((c) => c.classList.contains("on")).map((c) => c.textContent);
test("history and reload scope never overwrite All; an explicit chip saves", async (t) => {
  const state = { views: { items: { selection: "all", focus: null } } };
  const { root, windowNode, client } = await mount(t, "/items?project=1", state);
  for (const href of ["/items?project=all", "/items?project=1"]) {
    windowNode.location.href = href;
    windowNode.dispatchEvent(new Event("popstate"));
    await settle();
  }
  assert.equal(state.views.items.selection, "all");
  assert.equal(selectionWrites(client).length, 0);
  scopeChips(root).find((c) => c.textContent === "All").dispatchEvent(new Event("click"));
  await settle();
  assert.equal(selectionWrites(client).length, 1);
  assert.equal(state.views.items.selection, "all");
});
test("single-project default focus never saves", async () => {
  const writes = [];
  const state = createProjectSelection((...args) => writes.push(args));
  state.markReady();
  assert.equal(scopeForEntry(navEntry("architecture"), null, projects, state), "1");
  await settle();
  assert.deepEqual(writes, []);
});
test("last-page replay drops old scope and uses saved All", async (t) => {
  const state = { views: { items: { selection: "all", focus: null } }, last_location: "/items?project=1&selection=1" };
  const { root, client } = await mount(t, "/", state);
  assert.deepEqual(selected(root), ["All"]);
  assert.equal(state.last_location, "/items");
  assert.equal(selectionWrites(client).length, 0);
});
test("returning tab refreshes saved scope and stops listening on unmount", async (t) => {
  const state = { views: { items: { selection: ["1"], focus: null } } };
  const { root, windowNode, documentNode, client, app } = await mount(t, "/items", state);
  assert.deepEqual(selected(root), ["ALP"]);
  state.views.items.selection = "all";
  windowNode.dispatchEvent(new Event("focus"));
  await settle();
  assert.deepEqual(selected(root), ["All"]);
  state.views.items.selection = ["2"];
  documentNode.visibilityState = "visible";
  documentNode.dispatchEvent(new Event("visibilitychange"));
  await settle();
  assert.deepEqual(selected(root), ["BET"]);
  assert.equal(selectionWrites(client).length, 0);
  app.unmount();
  const href = windowNode.location.href;
  windowNode.dispatchEvent(new Event("focus"));
  await settle();
  assert.equal(windowNode.location.href, href);
});
test("a choice during refresh wins and writes capture each clicked value", async () => {
  const writes = [];
  const state = createProjectSelection((_view, selection) => writes.push(selection));
  state.markReady();
  let finish;
  const read = state.refreshSelections(() => new Promise((resolve) => { finish = resolve; }));
  await settle();
  state.setSelectionFor("items", ["1"]);
  state.saveFor("items");
  state.setSelectionFor("items", "all");
  state.saveFor("items");
  finish({ views: { items: { selection: ["2"] } } });
  assert.equal(await read, false);
  await settle();
  assert.equal(state.selectionFor("items"), "all");
  assert.deepEqual(writes, [["1"], "all"]);
});
test("roster purge repairs saved IDs without saving a route's different scope", async () => {
  const writes = [];
  const state = createProjectSelection((...args) => writes.push(args));
  state.seed("items", ["1", "gone"], "gone");
  state.markReady();
  resolveProjectSelection(state, "items", projects, "2");
  await settle();
  assert.deepEqual(writes, [["items", ["1"], null]]);
  assert.deepEqual(state.selectionFor("items"), ["2"]);
});
