import assert from "node:assert/strict";
import test from "node:test";

import { allNodes, byClass } from "./universe_ui_dom_test_support.mjs";
import {
  SETTINGS_URL,
  UNBOUND_STATUS,
  boundStatusFixture,
  buttons,
  click,
  githubClient,
  headerLabels,
  modeCapabilities,
  mountGithub,
  okEnvelope,
  panelTitles,
  viewHost,
  viewText,
} from "./universe_ui_github_test_support.mjs";

const PAGE_TITLES = [
  "GitHub App installations",
  "Project mappings with issue-sync",
];

function statusCalls(client) {
  return client.requests.filter(
    (request) => request.function === "projects.github_binding.status",
  );
}

function settingsLinks(root) {
  return allNodes(viewHost(root)).filter(
    (node) => node.tagName === "A" && node.textContent === "Manage on GitHub ↗",
  );
}

for (const mode of ["local", "self-host"]) {
  test(`${mode}: one page with last-checked freshness and Check now`, async (t) => {
    const client = githubClient(boundStatusFixture());
    const { root, mounted } = await mountGithub(t, client, {
      capabilities: modeCapabilities(mode),
    });

    assert.deepEqual(statusCalls(client)[0], {
      function: "projects.github_binding.status",
      payload: { project: "1" },
    });
    assert.deepEqual(panelTitles(root), PAGE_TITLES);
    assert.ok(headerLabels(root).includes("last checked"));
    assert.ok(!headerLabels(root).includes("updates"));
    const text = viewText(root);
    assert.ok(text.includes("example-org/example-repo"));
    assert.ok(text.includes("Organization"));
    assert.match(text, /\d+d ago/);
    assert.doesNotMatch(text, /unavailable/);

    const [link] = settingsLinks(root);
    assert.equal(link.href, SETTINGS_URL);
    assert.equal(link.target, "_blank");
    assert.equal(link.rel, "noreferrer");
    const [check] = buttons(root, "Check now");
    assert.equal(check.disabled, false);
    assert.equal(buttons(root, "Detach").length, 0);
    mounted.unmount();
  });
}

test("Check now re-verifies each bound project, then reloads", async (t) => {
  const client = githubClient(boundStatusFixture(), {
    check: () => okEnvelope({ project: "yoke", binding: {} }),
  });
  const { root, mounted } = await mountGithub(t, client, {
    capabilities: modeCapabilities("local"),
  });
  const before = statusCalls(client).length;

  await click(buttons(root, "Check now")[0]);

  assert.deepEqual(
    client.requests.filter(
      (request) => request.function === "projects.github_binding.check",
    ),
    [{ function: "projects.github_binding.check", payload: { project: "1" } }],
  );
  assert.ok(statusCalls(client).length > before);
  assert.ok(viewText(root).includes("Checked 1 bound project with GitHub."));
  assert.equal(byClass(viewHost(root), "error").length, 0);
  mounted.unmount();
});

test("a refused check names its reason and recovery", async (t) => {
  const client = githubClient(boundStatusFixture(), {
    check: () => ({
      status: 409,
      envelope: {
        success: false,
        error: {
          code: "github_check_authority_unavailable",
          message: "no GitHub authority can check this binding",
          recovery_hint: "Run yoke github connect on this machine.",
        },
      },
    }),
  });
  const { root, mounted } = await mountGithub(t, client, {
    capabilities: modeCapabilities("local"),
  });

  await click(buttons(root, "Check now")[0]);

  const [alert] = byClass(viewHost(root), "error");
  assert.equal(
    alert.textContent,
    "Yoke: no GitHub authority can check this binding " +
      "Run yoke github connect on this machine.",
  );
  assert.equal(alert.getAttribute("role"), "alert");
  mounted.unmount();
});

test("an unbound project disables Check now and still maps the repo", async (t) => {
  const client = githubClient(UNBOUND_STATUS);
  const { root, mounted } = await mountGithub(t, client, {
    capabilities: modeCapabilities("local"),
  });

  assert.deepEqual(panelTitles(root), PAGE_TITLES);
  const text = viewText(root);
  assert.ok(text.includes("example-org/orphaned-repo"));
  assert.ok(text.includes("repo_not_bound"));
  assert.ok(text.includes("no GitHub App installation backs a project"));
  const [check] = buttons(root, "Check now");
  assert.equal(check.disabled, true);
  assert.match(check.title, /No project in this scope is bound/);
  assert.equal(settingsLinks(root).length, 0);
  mounted.unmount();
});

test("a binding without an installation record renders honestly", async (t) => {
  const client = githubClient(boundStatusFixture({
    installation: null,
    permission_status: { status: "unknown", missing: [] },
    automation: { available: false, reason: "installation_missing" },
  }));
  const { root, mounted } = await mountGithub(t, client, {
    capabilities: modeCapabilities("self-host"),
  });

  const text = viewText(root);
  assert.ok(text.includes(
    "the binding names installation 31, but no installation record backs it",
  ));
  assert.ok(text.includes("installation_missing"));
  assert.ok(text.includes("blocked"));
  assert.doesNotMatch(text, /unavailable/);
  assert.equal(settingsLinks(root).length, 0);
  mounted.unmount();
});

test("hosted: live freshness, the host's installations, and Detach", async (t) => {
  const detached = [];
  const client = githubClient(boundStatusFixture());
  const { root, mounted } = await mountGithub(t, client, {
    capabilities: modeCapabilities("hosted", {
      installations: [
        {
          installationId: "31",
          accountLogin: "example-org",
          accountType: "Organization",
          status: "active",
          repositorySelection: "selected",
          settingsUrl: SETTINGS_URL,
          boundProjects: 1,
        },
        {
          installationId: "44",
          accountLogin: "spare-org",
          accountType: "Organization",
          status: "active",
          repositorySelection: "all",
          settingsUrl: "",
          boundProjects: 0,
          missingPermissions: ["issues"],
        },
      ],
      detachInstallation: {
        label: "Detach",
        onInvoke(option) { detached.push(option); },
      },
    }),
  });

  assert.deepEqual(panelTitles(root), PAGE_TITLES);
  assert.ok(headerLabels(root).includes("updates"));
  assert.ok(!headerLabels(root).includes("last checked"));
  assert.ok(byClass(viewHost(root), "pill").some(
    (node) => node.textContent === "live",
  ));
  assert.equal(buttons(root, "Check now").length, 0);
  const text = viewText(root);
  assert.ok(text.includes("spare-org"));
  assert.ok(text.includes("missing: issues"));
  assert.equal(settingsLinks(root).length, 1);

  const [boundDetach, spareDetach] = buttons(root, "Detach");
  assert.equal(boundDetach.disabled, true);
  assert.match(boundDetach.title, /Remove this installation's project mappings/);
  assert.equal(spareDetach.disabled, false);
  await click(spareDetach);
  assert.deepEqual(detached, [{ id: "44", label: "Detach" }]);
  mounted.unmount();
});
