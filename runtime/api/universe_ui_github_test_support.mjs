import {
  mountUniverseApp,
} from "../../packages/yoke-core/src/yoke_core/ui/static/app.js";
import {
  FakeDocument,
  allNodes,
  byClass,
  response,
  settle,
} from "./universe_ui_dom_test_support.mjs";

export const SETTINGS_URL =
  "https://github.com/organizations/example-org/settings/installations/31";

export function okEnvelope(result) {
  return { status: 200, envelope: { success: true, result } };
}

export function boundStatusFixture(overrides = {}) {
  return {
    project: "yoke",
    github_repo: "example-org/example-repo",
    default_branch: "main",
    github_sync_mode: "enabled",
    bound: true,
    binding: {
      project_id: 1,
      installation_id: "31",
      repository_id: "repo-9",
      api_url: "https://api.github.com",
      github_repo: "example-org/example-repo",
      default_branch: "main",
      status: "active",
      permissions: { contents: "write" },
      last_verified_at: "2026-07-01T10:00:00Z",
      last_error: "",
      last_sync_at: "2026-07-02T08:30:00Z",
      last_sync_outcome: "success",
      last_sync_error: "",
    },
    installation: {
      installation_id: "31",
      api_url: "https://api.github.com",
      account_id: "acct-4",
      account_login: "example-org",
      account_type: "Organization",
      repository_selection: "selected",
      permissions: { contents: "write" },
      status: "active",
      last_verified_at: "2026-07-01T10:00:00Z",
      last_error: "",
      settings_url: SETTINGS_URL,
    },
    permission_status: { status: "satisfied", missing: [] },
    automation: { available: true, reason: "bound" },
    ...overrides,
  };
}

export const UNBOUND_STATUS = {
  project: "yoke",
  github_repo: "example-org/orphaned-repo",
  default_branch: "",
  github_sync_mode: "disabled",
  bound: false,
  binding: null,
  installation: null,
  permission_status: { status: "unknown", missing: [] },
  automation: { available: false, reason: "repo_not_bound" },
};

// `options.check` answers `projects.github_binding.check`; without it the
// page must never call the check.
export function githubClient(statusResult, options = {}) {
  const requests = [];
  return {
    requests,
    async call(request) {
      requests.push(request);
      if (request.function === "organizations.get") {
        return okEnvelope({ name: "Yoke" });
      }
      if (request.function === "projects.list") {
        return okEnvelope({
          rows: options.projects || [{ id: 1, slug: "yoke", name: "Yoke" }],
        });
      }
      if (request.function === "projects.github_binding.status") {
        return okEnvelope(statusResult);
      }
      if (request.function === "projects.github_binding.check" && options.check) {
        return options.check(request);
      }
      throw new Error(`unexpected function ${request.function}`);
    },
  };
}

export function modeCapabilities(mode, github) {
  const data = { portability: { mode } };
  if (github !== undefined) data.github = github;
  return { data };
}

export async function mountGithub(t, client, options = {}) {
  const originalFetch = globalThis.fetch;
  t.after(() => { globalThis.fetch = originalFetch; });
  globalThis.fetch = () => response(200, {});
  const documentNode = new FakeDocument();
  documentNode.defaultView.location.href = "/github?project=1";
  const root = documentNode.createElement("div");
  const mounted = mountUniverseApp(root, {
    client,
    capabilities: options.capabilities,
  });
  await settle();
  return { root, mounted, documentNode };
}

export function viewHost(root) {
  return byClass(root, "view-host")[0];
}

export function panelTitles(root) {
  return allNodes(viewHost(root))
    .filter((node) => node.tagName === "H2")
    .map((node) => node.textContent);
}

export function viewText(root) {
  return allNodes(viewHost(root))
    .map((node) => node.textContent || "").join(" ");
}

export function buttons(root, label) {
  return allNodes(viewHost(root)).filter(
    (node) => node.tagName === "BUTTON" && node.textContent === label,
  );
}

export function headerLabels(root) {
  return allNodes(viewHost(root))
    .filter((node) => node.tagName === "TH")
    .map((node) => node.textContent);
}

export async function click(node) {
  node.dispatchEvent(new Event("click"));
  await settle();
}
