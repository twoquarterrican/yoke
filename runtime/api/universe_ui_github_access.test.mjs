import assert from "node:assert/strict";
import test from "node:test";

import { allNodes, byClass } from "./universe_ui_dom_test_support.mjs";
import {
  boundStatusFixture,
  buttons,
  click,
  githubClient,
  modeCapabilities,
  mountGithub,
  panelTitles,
  viewHost,
  viewText,
} from "./universe_ui_github_test_support.mjs";

const WITH_PERSONAL = [
  "GitHub App installations",
  "Personal GitHub authorization",
  "Project mappings with issue-sync",
];

function codes(root) {
  return allNodes(viewHost(root))
    .filter((node) => node.tagName === "CODE")
    .map((node) => node.textContent);
}

test("local machine authorization shows the account and its state", async (t) => {
  const { root, mounted } = await mountGithub(t, githubClient(boundStatusFixture()), {
    capabilities: modeCapabilities("local", {
      authorization: { login: "octo", status: "authorized" },
    }),
  });

  assert.deepEqual(panelTitles(root), WITH_PERSONAL);
  assert.ok(codes(root).includes("@octo"));
  assert.ok(byClass(viewHost(root), "pill").some(
    (node) => node.textContent === "authorized",
  ));
  assert.ok(!codes(root).includes("yoke github connect"));
  mounted.unmount();
});

test("an unconnected machine names the connect command", async (t) => {
  const { root, mounted } = await mountGithub(t, githubClient(boundStatusFixture()), {
    capabilities: modeCapabilities("local", { authorization: null }),
  });

  assert.deepEqual(panelTitles(root), WITH_PERSONAL);
  assert.ok(viewText(root).includes("not connected"));
  assert.ok(codes(root).includes("yoke github connect"));
  mounted.unmount();
});

test("an unreadable machine config shows its notice, not a guess", async (t) => {
  const { root, mounted } = await mountGithub(t, githubClient(boundStatusFixture()), {
    capabilities: modeCapabilities("local", {
      authorization: null,
      notices: [{ kind: "error", message: "machine GitHub config is unreadable" }],
    }),
  });

  const alert = byClass(viewHost(root), "error")
    .find((node) => node.textContent === "machine GitHub config is unreadable");
  assert.equal(alert.getAttribute("role"), "alert");
  mounted.unmount();
});

test("no authorization fact hides the Personal panel entirely", async (t) => {
  for (const capabilities of [
    modeCapabilities("self-host"),
    modeCapabilities("hosted", {}),
  ]) {
    const { root, mounted } = await mountGithub(
      t, githubClient(boundStatusFixture()), { capabilities },
    );
    assert.ok(!panelTitles(root).includes("Personal GitHub authorization"));
    assert.doesNotMatch(viewText(root), /unavailable/);
    mounted.unmount();
  }
});

test("hosted identity actions run, and a failure lands on the panel", async (t) => {
  const invoked = [];
  const { root, mounted } = await mountGithub(t, githubClient(boundStatusFixture()), {
    capabilities: modeCapabilities("hosted", {
      authorization: { login: "acme-admin", status: "authorized" },
      connect: {
        label: "Add or refresh GitHub access",
        onInvoke() { invoked.push("connect"); },
      },
      disconnectIdentity: {
        label: "Disconnect my GitHub identity",
        async onInvoke() { throw new Error("identity is still in use"); },
      },
    }),
  });

  assert.deepEqual(panelTitles(root), WITH_PERSONAL);
  await click(buttons(root, "Add or refresh GitHub access")[0]);
  assert.deepEqual(invoked, ["connect"]);
  await click(buttons(root, "Disconnect my GitHub identity")[0]);
  assert.ok(byClass(viewHost(root), "error").some(
    (node) => node.textContent ===
      "Disconnect my GitHub identity failed: identity is still in use",
  ));
  assert.ok(!codes(root).includes("yoke github connect"));
  mounted.unmount();
});

test("hosted without a connected identity offers connect but not disconnect", async (t) => {
  const { root, mounted } = await mountGithub(t, githubClient(boundStatusFixture()), {
    capabilities: modeCapabilities("hosted", {
      authorization: null,
      connect: { label: "Connect GitHub", onInvoke() {} },
      disconnectIdentity: { label: "Disconnect my GitHub identity", onInvoke() {} },
    }),
  });

  assert.equal(buttons(root, "Connect GitHub").length, 1);
  assert.equal(buttons(root, "Disconnect my GitHub identity").length, 0);
  assert.ok(viewText(root).includes("not connected"));
  mounted.unmount();
});
