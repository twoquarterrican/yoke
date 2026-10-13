import assert from "node:assert/strict";
import test from "node:test";
import { loadPlanSummaries } from "../../packages/yoke-core/src/yoke_core/ui/static/qa_plan_summary_rows.js";
import { loadVerificationCatalog } from "../../packages/yoke-core/src/yoke_core/ui/static/item_intake_controls.js";
import { openProjectDefaultEditor } from "../../packages/yoke-core/src/yoke_core/ui/static/workflow_project_default_editor.js";
import { createUniverseSearch } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_search_domains.js";
import { FakeDocument, allNodes, settle } from "./universe_ui_dom_test_support.mjs";
import { workflowFixture, okEnvelope } from "./universe_ui_workflows_test_support.mjs";

function client() {
  const calls = [];
  return { calls, async call(request) {
    calls.push(request);
    if (request.function === "projects.list") return okEnvelope({ rows: [{ id: 1 }] });
    if (request.function === "qa.plan.list") return okEnvelope({
      rows: [{ id: request.payload.offset + 1, slug: "source" }],
      next_offset: request.payload.offset === 0 ? 100 : null,
    });
    return okEnvelope({ rows: [], matches: [], docs: [], packs: [] });
  } };
}
function summaryRequests(c) {
  const reads = c.calls.filter((r) => r.function === "qa.plan.list");
  assert.equal(reads.length, 2);
  assert.deepEqual(reads.map((r) => r.payload.detail), ["summary", "summary"]);
  assert.deepEqual(reads.map((r) => r.payload.offset), [0, 100]);
}

test("summary catalogue follows pages and never returns a partial failed roster", async () => {
  const c = client();
  const result = await loadPlanSummaries(c, "sample");
  assert.equal(result.envelope.result.rows.length, 2);
  summaryRequests(c);
  const failed = await loadPlanSummaries({ async call(request) {
    return request.payload.offset === 0 ? okEnvelope({ rows: [{ id: 1 }], next_offset: 100 })
      : { status: 408, envelope: { success: false, error: { message: "read_deadline_exceeded" } } };
  } }, "sample");
  assert.equal(failed.envelope.success, false);
  assert.equal(failed.envelope.result, undefined);
});

test("intake and search use all summary pages", async () => {
  const intake = client();
  const result = await loadVerificationCatalog(intake, { slug: "sample" });
  assert.equal(result.plans.length, 2);
  summaryRequests(intake);
  const search = client();
  await createUniverseSearch(search)("source", () => {});
  summaryRequests(search);
});

test("testing picker reports a plan refusal with retry instead of no plans", async () => {
  const documentNode = new FakeDocument();
  const host = documentNode.createElement("div");
  let attempts = 0;
  const c = client();
  c.call = async (request) => {
    c.calls.push(request); attempts++;
    return attempts === 1 ? { status: 408, envelope: { success: false, error: {
      code: "read_deadline_exceeded", message: "read_deadline_exceeded: retry a summary page",
    } } } : okEnvelope({ rows: [{ id: 1, slug: "source" }] });
  };
  openProjectDefaultEditor({ documentNode, host, kind: "testing", workflow: workflowFixture(),
    projects: [{ id: 1, slug: "sample" }], data: { testingDefaults: [], plansByProject: {} },
    close() {}, save() {}, client: c,
  });
  assert.match(host.textContent, /loading…/);
  await settle();
  assert.match(host.textContent, /read_deadline_exceeded/);
  assert.doesNotMatch(host.textContent, /has no test plans/);
  const retry = allNodes(host).find((node) => node.textContent === "Retry plan read");
  retry.dispatchEvent(new Event("click"));
  await settle();
  assert.equal(attempts, 2);
  assert.doesNotMatch(host.textContent, /read_deadline_exceeded/);
  assert.ok(allNodes(host).some((node) => node.tagName === "OPTION" && node.textContent === "source"));
  assert.equal(c.calls[0].payload.detail, "summary");
});


test("Test plans requests full rows and renders outcome, target, cases and attachments", async () => {
  const { renderQaPlans } = await import("../../packages/yoke-core/src/yoke_core/ui/static/qa_view_plans.js");
  const document = new FakeDocument();
  const host = document.createElement("main");
  const calls = [];
  await renderQaPlans({ document, isMounted: () => true,
    projects: () => [{ id: 1, slug: "sample" }],
    client: { async call(request) {
      calls.push(request);
      return okEnvelope({ rows: [{ id: 3, project: "sample", slug: "source",
        case_count: 2, last_outcome: "passed",
        execution_target: { schema: 3, target_kind: "project", project: { id: 1, slug: "sample" } },
        attachments: [{ kind: "item", item_ref: "SAMPLE-7" }],
      }] });
    } },
  }, host, "all");
  assert.equal(calls[0].payload.detail, "full");
  assert.match(host.textContent, /passed/);
  assert.match(host.textContent, /project source/);
  assert.match(host.textContent, /SAMPLE-7/);
  assert.ok(allNodes(host).some((node) => node.tagName === "STRONG" && node.textContent === "2"));
});
