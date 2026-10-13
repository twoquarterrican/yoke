import assert from "node:assert/strict";
import test from "node:test";
import { renderWorkflowsView } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_views_workflows.js";
import { FakeDocument, byClass, settle } from "./universe_ui_dom_test_support.mjs";
import { okEnvelope, workflowFixture } from "./universe_ui_workflows_test_support.mjs";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}
function mount(client) {
  const document = new FakeDocument();
  const main = document.createElement("main");
  renderWorkflowsView({ document, client, projects: () => [{ id: 1, slug: "sample" }],
    isMounted: () => true, navigate() {},
  }, main, "all");
  return main;
}
function text(root) { return root.textContent; }

test("instructions mount immediately and definitions render before mechanics or plans", async () => {
  const definitions = deferred();
  const mechanics = deferred();
  const instructions = deferred();
  const requests = [];
  const root = mount({ call(request) {
    requests.push(request);
    if (request.function === "workflows.definition.get") return definitions.promise;
    if (request.function === "workflows.mechanics.get") return mechanics.promise;
    if (request.function === "workflow.execution_instruction.list") return instructions.promise;
    throw new Error(`unexpected ${request.function}`);
  } });
  assert.match(byClass(root, "workflow-instructions-host")[0].textContent, /loading…/);
  assert.deepEqual(requests.map((r) => r.function).sort(), [
    "workflow.execution_instruction.list", "workflows.definition.get",
  ]);
  instructions.resolve(okEnvelope({ instructions: [{ id: 1, content: "An instruction" }] }));
  await settle();
  assert.match(text(root), /An instruction/);
  definitions.resolve(okEnvelope({ workflows: [workflowFixture()], gate_catalog: [] }));
  await settle();
  assert.equal(byClass(root, "tab-bar")[0].children.length, 1);
  assert.match(text(root), /Skill/);
  const filter = byClass(root, "workflow-instruction-workflow-filter")[0];
  assert.ok(filter.children.some((row) => row.value === "rally"));
  assert.equal(requests.some((r) => r.function === "qa.plan.list"), false);
  mechanics.resolve(okEnvelope({}));
  await settle();
});

test("mechanics refusal stays visible and retries without hiding definitions", async () => {
  let attempts = 0;
  const root = mount({ async call(request) {
    if (request.function === "workflows.definition.get") return okEnvelope({ workflows: [workflowFixture()] });
    if (request.function === "workflow.execution_instruction.list") return okEnvelope({ instructions: [] });
    if (request.function === "workflows.mechanics.get") {
      attempts++;
      return attempts === 1 ? { status: 408, envelope: { success: false, error: {
        code: "read_deadline_exceeded", message: "read_deadline_exceeded: narrow this read",
      } } } : okEnvelope({});
    }
    throw new Error(request.function);
  } });
  await settle();
  assert.match(text(root), /read_deadline_exceeded/);
  assert.equal(byClass(root, "tab-bar")[0].children.length, 1);
  const retry = byClass(root, "workflow-button").find((n) => n.textContent === "Retry defaults read");
  retry.dispatchEvent(new Event("click"));
  await settle();
  assert.equal(attempts, 2);
  assert.doesNotMatch(text(root), /read_deadline_exceeded/);
});
