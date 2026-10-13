// Who reaches GitHub for this page, and the controls that change it. The
// mount packet carries these facts under `capabilities.data.github`: a
// hosted shell passes its organization's connection and actions, and the
// local `yoke ui` server passes this machine's GitHub App user
// authorization. A packet without an `authorization` key has no such fact
// to show, so the Personal panel is not rendered at all.

import { el, section, statePill } from "./universe_view_support.js";

const TITLE_PERSONAL = "Personal GitHub authorization";

export function githubHost(capabilities) {
  const github = capabilities?.data?.github;
  return github && typeof github === "object" ? github : {};
}

function isAction(action) {
  return Boolean(action) && typeof action.onInvoke === "function";
}

// Runs a host action and reports a throw or rejection on the panel's own
// status line, where the person who clicked is already looking.
function invoke(action, option, status) {
  const fail = (error) => {
    status.hidden = false;
    status.className = "error";
    status.textContent =
      `${action.label || "action"} failed: ${String(error?.message || error)}`;
  };
  try {
    Promise.resolve(action.onInvoke(option)).catch(fail);
  } catch (error) {
    fail(error);
  }
}

export function actionButton(documentNode, action, status, options = {}) {
  const option = options.option;
  const button = el(
    documentNode, "button", "capability-action",
    String(option?.label || action.label || ""),
  );
  button.type = "button";
  if (options.disabledReason) {
    button.disabled = true;
    button.title = options.disabledReason;
  }
  button.addEventListener("click", () => invoke(action, option, status));
  return button;
}

export function statusLine(documentNode) {
  const status = el(documentNode, "p", "fact-line");
  status.hidden = true;
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  return status;
}

export function appendNotices(documentNode, body, notices) {
  for (const notice of Array.isArray(notices) ? notices : []) {
    const isError = notice?.kind === "error";
    const line = el(
      documentNode, "p", isError ? "error" : "fact-line",
      String(notice?.message || ""),
    );
    line.setAttribute("role", isError ? "alert" : "status");
    body.appendChild(line);
  }
}

function accountLine(documentNode, authorization) {
  const line = el(documentNode, "p", "fact-line", "GitHub account: ");
  if (!authorization) {
    line.appendChild(documentNode.createTextNode("not connected"));
    return line;
  }
  line.appendChild(el(documentNode, "code", null, `@${authorization.login}`));
  const pill = statePill(documentNode, authorization.status);
  if (pill) {
    line.appendChild(documentNode.createTextNode(" "));
    line.appendChild(pill);
  }
  return line;
}

function connectCommand(documentNode) {
  const line = el(
    documentNode, "p", "fact-line",
    "Connect this machine to GitHub: ",
  );
  line.appendChild(el(documentNode, "code", null, "yoke github connect"));
  return line;
}

// The Personal panel, or null when the host carries no authorization fact.
// The connect command is this machine's own route; a hosted shell offers
// its connect action or a notice instead.
export function personalPanel(documentNode, capabilities, hosted) {
  const github = githubHost(capabilities);
  if (!Object.hasOwn(github, "authorization")) return null;
  const panel = section(documentNode, TITLE_PERSONAL);
  const body = panel.children[1];
  body.replaceChildren();
  appendNotices(documentNode, body, github.notices);
  const authorization = github.authorization && github.authorization.login
    ? github.authorization : null;
  body.appendChild(accountLine(documentNode, authorization));
  const actions = [github.connect, authorization && github.disconnectIdentity]
    .filter(isAction);
  if (actions.length) {
    const status = statusLine(documentNode);
    const row = el(documentNode, "div", "capability-actions");
    for (const action of actions) {
      row.appendChild(actionButton(documentNode, action, status));
    }
    body.appendChild(row);
    body.appendChild(status);
  } else if (!authorization && !hosted) {
    body.appendChild(connectCommand(documentNode));
  }
  return panel;
}

export { TITLE_PERSONAL, isAction };
