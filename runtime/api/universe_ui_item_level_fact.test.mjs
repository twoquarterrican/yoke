import assert from "node:assert/strict";
import test from "node:test";

import {
  renderItemDetailView,
} from "../../packages/yoke-core/src/yoke_core/ui/static/universe_views_items.js";
import {
  FakeDocument,
  allNodes,
  byClass,
  settle,
} from "./universe_ui_dom_test_support.mjs";
import {
  detailItem,
  itemContext,
  itemText,
} from "./universe_ui_items_test_support.mjs";

test("item details show effective level after status and the override reason in posture", async () => {
  const documentNode = new FakeDocument();
  const root = documentNode.createElement("div");
  const item = detailItem("dash");
  const override = { shift: -1, max: "SENIOR", reason: "Well-specified edits" };
  item.workflow.item_posture.level = override;
  item.level = { level: "JUNIOR", glyph: "🐥", stage_level: "SENIOR", stage_glyph: "🦉", stage_id: "implementing", override };
  renderItemDetailView(itemContext(documentNode, async () => ({
    status: 200, envelope: { success: true, result: { item } },
  })), root, String(item.project.id), item.public_ref);
  await settle();
  const labels = allNodes(byClass(root, "item-facts")[0]).filter((node) => node.tagName === "TH").map((node) => node.textContent);
  assert.equal(labels[labels.indexOf("Status") + 1], "Level");
  assert.match(itemText(root), /🐥 JUNIOR implementing · 🦉 SENIOR · shift -1 · max SENIOR/);
  assert.equal(byClass(root, "item-posture-label")[0].textContent, "Level");
  assert.match(itemText(byClass(root, "item-posture-grid")[0]), /Well-specified edits/);
});

for (const { name, level, expected } of [
  {
    name: "matching stage default without an override shows the effective level once",
    level: { level: "SENIOR", glyph: "🦉", stage_level: "SENIOR", stage_glyph: "🦉", stage_id: "implementing", override: {} },
    expected: "🦉 SENIOR",
  },
  {
    name: "different effective level without an override keeps the stage suffix",
    level: { level: "JUNIOR", glyph: "🐥", stage_level: "SENIOR", stage_glyph: "🦉", stage_id: "implementing" },
    expected: "🐥 JUNIOR implementing · 🦉 SENIOR",
  },
  {
    name: "override matching the stage default keeps the stage suffix",
    level: { level: "SENIOR", glyph: "🦉", stage_level: "SENIOR", stage_glyph: "🦉", stage_id: "implementing", override: { max: "SENIOR" } },
    expected: "🦉 SENIOR implementing · 🦉 SENIOR · max SENIOR",
  },
]) {
  test(name, async () => {
    const documentNode = new FakeDocument();
    const root = documentNode.createElement("div");
    const item = detailItem("dash");
    item.level = level;
    renderItemDetailView(itemContext(documentNode, async () => ({
      status: 200, envelope: { success: true, result: { item } },
    })), root, String(item.project.id), item.public_ref);
    await settle();
    const row = allNodes(byClass(root, "item-facts")[0]).find((node) =>
      node.tagName === "TR" && node.children[0].textContent === "Level");
    assert.equal(itemText(row.children[1]), expected);
    assert.equal(row.children[1].children[0].children[0].tagName, "B");
  });
}
