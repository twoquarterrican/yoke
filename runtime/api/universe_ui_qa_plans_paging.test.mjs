import assert from "node:assert/strict";
import test from "node:test";

import {
  PLAN_PAGE_SIZE,
  renderQaPlans,
} from "../../packages/yoke-core/src/yoke_core/ui/static/qa_view_plans.js";
import {
  FakeDocument,
  allNodes,
  byClass,
  settle,
} from "./universe_ui_dom_test_support.mjs";

function planRow(id) {
  return {
    id,
    project: "yoke",
    slug: `plan-${id}`,
    case_count: 0,
    materialized_requirement_count: 0,
    method_ids: [],
    attachments: [],
    execution_target: null,
  };
}

function plansContext(pages) {
  const documentNode = new FakeDocument();
  const requests = [];
  return {
    documentNode,
    requests,
    context: {
      document: documentNode,
      client: {
        async call(request) {
          requests.push(request);
          const page = pages.shift();
          if (!page) {
            return {
              status: 503,
              envelope: { success: false, error: { message: "plan read failed" } },
            };
          }
          return { status: 200, envelope: { success: true, result: page } };
        },
      },
      isMounted: () => true,
      navigate() {},
      projects: () => [{ id: 1, slug: "yoke", name: "Yoke" }],
    },
  };
}

function loadMore(main) {
  return allNodes(main).find((node) => node.tagName === "BUTTON"
    && ["Load more plans", "Retry"].includes(node.textContent));
}

test("Plans reads one page, then the next page on Load more", async () => {
  const { documentNode, requests, context } = plansContext([
    { rows: [planRow(1)], next_offset: PLAN_PAGE_SIZE },
    { rows: [planRow(2)], next_offset: null },
  ]);
  const main = documentNode.createElement("main");

  await renderQaPlans(context, main, ["1"]);

  assert.deepEqual(requests[0].payload, {
    project: "1", detail: "full", limit: PLAN_PAGE_SIZE, offset: 0,
  });
  assert.equal(byClass(main, "qa-plan-button").length, 1);
  loadMore(main).dispatchEvent(new Event("click"));
  await settle();

  assert.equal(requests[1].payload.offset, PLAN_PAGE_SIZE);
  assert.equal(byClass(main, "qa-plan-button").length, 2);
  assert.equal(loadMore(main), undefined);
});

test("A failed later page keeps loaded plans and offers Retry", async () => {
  const { documentNode, requests, context } = plansContext([
    { rows: [planRow(1)], next_offset: PLAN_PAGE_SIZE },
  ]);
  const main = documentNode.createElement("main");

  await renderQaPlans(context, main, ["1"]);
  loadMore(main).dispatchEvent(new Event("click"));
  await settle();

  assert.equal(byClass(main, "qa-plan-button").length, 1);
  assert.equal(loadMore(main).textContent, "Retry");
  assert.match(byClass(main, "event-recovery")[0].textContent, /Retry/);
  loadMore(main).dispatchEvent(new Event("click"));
  await settle();
  assert.equal(requests.at(-1).payload.offset, PLAN_PAGE_SIZE);
});
