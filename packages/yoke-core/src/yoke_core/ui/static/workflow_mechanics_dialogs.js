import { el } from "./universe_view_support.js";
import {
  button,
  setWorkflowInlineContent,
  workflowStageLabel,
} from "./workflow_view_primitives.js";
import {
  appendWorkflowDialogFooter,
  workflowDialogShell,
} from "./workflow_dialog_shell.js";
import {
  ROLE_LABELS,
} from "./workflow_mechanics_data.js";

const ROLE_OPTIONS = [
  ["owner", "Project owner"],
  ["operator", "Project operator"],
  ["admin", "Org admin"],
];

function fieldLabel(documentNode, text) {
  return el(documentNode, "div", "workflow-field-label", text);
}

function option(documentNode, value, label, selected) {
  const node = el(documentNode, "option", null, label);
  node.value = String(value);
  node.selected = String(value) === String(selected);
  return node;
}

function checkbox(documentNode, checked, label, toggle) {
  const row = el(documentNode, "label", "workflow-checkbox");
  const input = el(documentNode, "input");
  input.type = "checkbox";
  input.checked = checked;
  input.addEventListener("change", toggle);
  row.appendChild(input);
  row.appendChild(el(documentNode, "span", null, label));
  return row;
}

function transitionIds(workflow) {
  const stages = workflow.definition?.stages || [];
  const declared = new Set(
    (workflow.definition?.transitions || []).map(
      (transition) => transition.to_stage_id,
    ),
  );
  const ids = stages.map((stage) => stage.id).filter((id) => declared.has(id));
  return ids.length ? ids : stages.slice(1).map((stage) => stage.id);
}

export function openApprovalEditor({
  documentNode, host, workflow, data, close, save,
  subjects, source, title, impact, requireEverySubject = false,
  confirmText, subjectLabel,
}) {
  const usingSubjects = Array.isArray(subjects);
  const ids = usingSubjects
    ? subjects.map((subject) => subject.id)
    : transitionIds(workflow);
  const labelFor = (id) => {
    if (usingSubjects) {
      const match = subjects.find((subject) => subject.id === id);
      return match?.label || id;
    }
    return workflowStageLabel(workflow, id);
  };
  const sourceGates = source
    || workflow?.definition?.policies?.approval_defaults
    || {};
  const gates = Object.fromEntries(ids.map((transitionId) => {
    const gate = sourceGates[transitionId] || {};
    return [transitionId, {
      roles: [...(gate.roles || [])],
      actors: [...(gate.actors || [])].map(Number),
      mode: gate.mode === "all" ? "all" : "any",
    }];
  }));
  const state = { transitionId: ids[0], gates };
  const approvers = data?.approvers || [];

  const render = () => {
    const name = workflow?.name || workflow?.id || "";
    const shell = workflowDialogShell(
      documentNode, host, title || `Default approvals — ${name}`, close,
    );
    const { dialog } = shell;
    dialog.classList.add("workflow-approval-dialog");
    dialog.appendChild(fieldLabel(documentNode, subjectLabel || "Transition"));
    const transition = el(documentNode, "select", "workflow-field");
    for (const transitionId of ids) {
      const configured = (
        gates[transitionId].roles.length || gates[transitionId].actors.length
      );
      transition.appendChild(option(
        documentNode,
        transitionId,
        `${labelFor(transitionId)}` +
          `${configured ? " ✓" : ""}`,
        state.transitionId,
      ));
    }
    transition.value = state.transitionId;
    transition.addEventListener("change", (event) => {
      state.transitionId = event.target.value;
      render();
    });
    dialog.appendChild(transition);
    const gate = gates[state.transitionId];
    const approvalHelp = el(
      documentNode,
      "p",
      "workflow-field-help workflow-approval-help",
    );
    setWorkflowInlineContent(documentNode, approvalHelp, [
      gate.mode === "all"
        ? "Every box checked here must approve "
        : "Anyone who matches may approve ",
      {
        kind: "strong",
        text: labelFor(state.transitionId),
      },
    ]);
    dialog.appendChild(approvalHelp);
    for (const [role, label] of ROLE_OPTIONS) {
      dialog.appendChild(checkbox(
        documentNode,
        gate.roles.includes(role),
        label,
        () => {
          gate.roles = gate.roles.includes(role)
            ? gate.roles.filter((value) => value !== role)
            : [...gate.roles, role];
          render();
        },
      ));
    }
    dialog.appendChild(fieldLabel(documentNode, "Or any of these people"));
    for (const actor of approvers) {
      dialog.appendChild(checkbox(
        documentNode,
        gate.actors.includes(Number(actor.id)),
        actor.label,
        () => {
          const actorId = Number(actor.id);
          gate.actors = gate.actors.includes(actorId)
            ? gate.actors.filter((value) => value !== actorId)
            : [...gate.actors, actorId];
          render();
        },
      ));
    }
    if (!approvers.length) {
      dialog.appendChild(el(
        documentNode, "p", "workflow-field-help",
        "No named human actors are available.",
      ));
    }
    dialog.appendChild(fieldLabel(documentNode, "How many must approve"));
    const mode = el(documentNode, "select", "workflow-field");
    mode.appendChild(option(
      documentNode, "any", "Any one of them settles it", gate.mode,
    ));
    mode.appendChild(option(
      documentNode, "all", "All of them, one decision each", gate.mode,
    ));
    mode.value = gate.mode;
    mode.addEventListener("change", (event) => {
      gate.mode = event.target.value;
      render();
    });
    dialog.appendChild(mode);
    const configured = ids.filter(
      (id) => gates[id].roles.length || gates[id].actors.length,
    );
    const configuredSummary = el(
      documentNode, "p", "workflow-configured-summary",
    );
    const configuredParts = configured.length
      ? [
        "Gates set: ",
        ...configured.flatMap((stageId, index) => [
          ...(index ? [" · "] : []),
          {
            kind: "strong",
            className: "workflow-configured-stage",
            text: labelFor(stageId),
          },
        ]),
      ]
      : "No gates yet — a transition with no one selected has no approval.";
    setWorkflowInlineContent(
      documentNode, configuredSummary, configuredParts,
    );
    dialog.appendChild(configuredSummary);
    const incomplete = requireEverySubject && ids.some(
      (id) => !gates[id].roles.length && !gates[id].actors.length,
    );
    const impactText = impact !== undefined
      ? impact
      : (
        `Saving creates a new version of the ${name} workflow. Items already ` +
        `underway stay pinned to v${workflow.current_version} and are unaffected.`
      );
    appendWorkflowDialogFooter(documentNode, dialog, {
      impact: impactText,
      confirmText: confirmText || "Save universe default",
      dismiss: shell.dismiss,
      activate: shell.activate,
      disabled: incomplete,
      save: () => save(
        requireEverySubject
          ? Object.fromEntries(Object.entries(gates))
          : Object.fromEntries(
            Object.entries(gates).filter(
              ([, value]) => value.roles.length || value.actors.length,
            ),
          ),
      ),
    });
  };
  render();
}
