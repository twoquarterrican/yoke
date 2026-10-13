import assert from "node:assert/strict";
import test from "node:test";
import { renderMachineApproval } from "../../packages/yoke-core/src/yoke_core/ui/static/machine_approval.js";
import { parseUniverseRoute } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_navigation.js";
import { FakeDocument, allNodes, byClass, settle } from "./universe_ui_dom_test_support.mjs";

function page({ decision = null, failure = null, readError = null, count = 0,
  machine = "My laptop", code = "ABCDE-12345", expired = false } = {}) {
  const document = new FakeDocument();
  const main = document.createElement("div");
  const requests = [], navigation = [], titles = [];
  let refuse = failure;
  const expires = new Date(Date.now() + (expired ? -120000 : 540000)).toISOString();
  const context = {
    document, isMounted: () => true, navigate: (path) => navigation.push(path),
    client: { async call(request) {
      requests.push(request);
      const ok = (result) => ({ status: 200, envelope: { success: true, result } });
      if (request.function === "organizations.get") return ok({ name: "Example org" });
      if (request.function === "machine.list") return ok({ count, machines: [] });
      if (request.function === "machine_authorization.get") {
        if (readError) return { status: 404, envelope: { success: false, error: readError } };
        return ok({ authorization: { code, machine, machine_id: "4f2c9a1e-more-id", platform: "macOS", expires_at: expires, decision } });
      }
      if (refuse) {
        const error = refuse;
        refuse = null;
        return { status: 503, envelope: { success: false, error } };
      }
      return ok({ authorization: { decision: request.payload.action } });
    } },
  };
  renderMachineApproval(context, main, null, code, { setPageHead: ({ title }) => titles.push(title) });
  return { main, requests, context, navigation, titles, expires };
}
const button = (main, label) => allNodes(main).find((node) => node.tagName === "BUTTON" && node.textContent === label);
const tag = (main, name) => allNodes(main).filter((node) => node.tagName === name);

test("approval displays real facts and completes first-run progress", async () => {
    assert.equal(parseUniverseRoute("/machine-approval/ABCDE-12345").detail, "ABCDE-12345");
    const { main, requests, titles, expires } = page();
    await settle();
    assert.equal(titles.at(-1), "Approve this machine");
    assert.match(main.textContent, /My laptopmacOS · machine 4f2c9a1e/);
    assert.match(main.textContent, /matches the one in your terminal/);
    assert.match(main.textContent, /OrganizationExample org/);
    assert.match(main.textContent, /in 9 minutes/);
    assert.equal(tag(main, "TIME")[0].getAttribute("datetime"), expires);
    assert.notEqual(tag(main, "TIME")[0].textContent, expires);
    assert.equal(byClass(main, "machine-approval-steps")[0].children[3].getAttribute("aria-current"), "step");
    button(main, "Approve machine").dispatchEvent(new Event("click"));
    await settle();
    assert.deepEqual(requests.find((r) => r.function === "machine_authorization.resolve").payload, { code: "ABCDE-12345", action: "approve" });
    assert.equal(titles.at(-1), "Machine connected");
    assert.match(main.textContent, /✓ My laptop is connected to Example org/);
    assert.equal(byClass(main, "machine-approval-next")[0].textContent, "Return to your terminal");
    assert.equal(byClass(main, "machine-approval-steps")[0].children.every((step) => step.className === "done"), true);
    assert.doesNotMatch(main.textContent, /Expires|must match|yoke connect|CLI/);
    assert.equal(button(main, "Deny"), undefined);
  });

test("later machine requests omit setup progress", async () => {
  const { main } = page({ count: 2 });
  await settle();
  assert.equal(byClass(main, "machine-approval-steps").length, 0);
  assert.ok(button(main, "Approve machine"));
});

test("missing machine names omit the whole row", async () => {
  const { main } = page({ machine: null });
  await settle();
  assert.equal(tag(main, "DT").some((node) => node.textContent === "Machine"), false);
  assert.doesNotMatch(main.textContent, /Connecting machine|machine 4f2c9a1e/);
});

test("denial authorizes nothing and removes decision controls", async () => {
  const { main, titles } = page();
  await settle();
  button(main, "Deny").dispatchEvent(new Event("click"));
  await settle();
  assert.equal(titles.at(-1), "Connect your machine");
  assert.match(main.textContent, /Request deniedNothing was authorized/);
  assert.equal(button(main, "Approve machine"), undefined);
});

test("a transport refusal preserves retry and never reports success", async () => {
  const { main, requests } = page({ failure: { code: "authorization_store_unavailable", message: "authorization_store_unavailable: restore storage" } });
  await settle();
  const approve = button(main, "Approve machine");
  approve.dispatchEvent(new Event("click"));
  await settle();
  assert.match(main.textContent, /authorization_store_unavailable.*Retry your decision/);
  assert.doesNotMatch(main.textContent, /is connected/);
  assert.equal(approve.disabled, false);
  approve.dispatchEvent(new Event("click"));
  await settle();
  assert.equal(requests.filter((r) => r.function === "machine_authorization.resolve").length, 2);
  assert.match(main.textContent, /is connected/);
});

test("expired facts name the local time without promising automatic renewal", async () => {
  const { main, titles, expires } = page({ expired: true });
  await settle();
  assert.equal(titles.at(-1), "Connect your machine");
  assert.match(main.textContent, /This code expired at .*Nothing was authorized/);
  assert.doesNotMatch(main.textContent, /new code|yoke connect|CLI/);
  assert.equal(button(main, "Approve machine"), undefined);
  assert.doesNotMatch(main.textContent, new RegExp(expires));
});

test("an unavailable code has named recovery and a code entry form", async () => {
  const { main, context, navigation } = page({ readError: { code: "authorization_unavailable" } });
  await settle();
  assert.match(main.textContent, /That code isn't availableCheck the code in your terminal and try again/);
  const input = tag(main, "INPUT")[0];
  input.value = " ABCDE-12345 ";
  tag(main, "FORM")[0].dispatchEvent(new Event("submit", { cancelable: true }));
  assert.deepEqual(navigation, ["/machine-approval/ABCDE-12345"]);
  context.isMounted = () => false;
});

test("no URL code teaches terminal entry without command-specific language", async () => {
  const { main, requests } = page({ code: null });
  await settle();
  assert.match(main.textContent, /Enter the one-time code shown in your terminal/);
  assert.equal(requests.some((r) => r.function === "machine_authorization.get"), false);
  assert.ok(button(main, "Continue"));
});

test("decided codes show the outcome without another approval", async () => {
  const { main } = page({ decision: "approve" });
  await settle();
  assert.equal(button(main, "Approve machine"), undefined);
  assert.match(main.textContent, /Return to your terminal/);
});

test("a detached route ignores late reads even while the application stays mounted", async () => {
  const { main, titles } = page();
  main.isConnected = false;
  await settle();
  assert.equal(titles.at(-1), "Connect your machine");
  assert.doesNotMatch(main.textContent, /My laptop|Approve machine/);
});
