import { el, renderError } from "./universe_view_support.js";
import { loadPlanSummaries } from "./qa_plan_summary_rows.js";
import { button } from "./workflow_view_primitives.js";
import { appendWorkflowDialogFooter, workflowDialogShell } from "./workflow_dialog_shell.js";
import { optionsForProject, projectKey, selectedProjectDefault } from "./workflow_mechanics_data.js";

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

export function openProjectDefaultEditor({
  documentNode, host, kind, workflow, projects, data, close, save, client,
}) {
  let closed = false;
  const dismiss = () => { closed = true; close(); };
  const failures = {};
  const pending = new Set();
  const loadPlans = async (project) => {
    const key = projectKey(project);
    if (kind !== "testing" || data.plansByProject[key] || pending.has(key)) return;
    pending.add(key);
    delete failures[key];
    try {
      const result = await loadPlanSummaries(client, key);
      if (result.status === 200 && result.envelope.success) {
        data.plansByProject[key] = result.envelope.result.rows;
      } else failures[key] = result;
    } catch (error) {
      failures[key] = { status: 0, envelope: { error: {
        message: `plan_read_failed: ${error}; retry this project's plan read.`,
      } } };
    }
    pending.delete(key);
    if (closed) return;
    if (state.project === project) setProject(project);
    render();
  };
  const available = projects.filter(
    (project) => optionsForProject(data, kind, project).length,
  );
  const state = {
    project: available[0] || projects[0],
    value: "",
    applyToAll: false,
  };
  const noun = kind === "testing" ? "test plan" : "deployment flow";
  const setProject = (project) => {
    state.project = project;
    if (!failures[projectKey(project)]) loadPlans(project);
    const selected = selectedProjectDefault(
      data, kind, project, workflow.id,
    );
    const options = optionsForProject(data, kind, project);
    state.value = selected || (options[0] && String(options[0].id)) || "";
  };
  if (state.project) setProject(state.project);

  const render = () => {
    const name = workflow.name || workflow.id;
    const shell = workflowDialogShell(
      documentNode, host, `Default ${noun} — ${name}`, dismiss,
    );
    const { dialog } = shell;
    dialog.appendChild(fieldLabel(documentNode, "Project"));
    const projectSelect = el(documentNode, "select", "workflow-field");
    for (const project of projects) {
      projectSelect.appendChild(option(
        documentNode,
        projectKey(project),
        projectKey(project),
        state.project && projectKey(state.project),
      ));
    }
    projectSelect.value = state.project ? projectKey(state.project) : "";
    projectSelect.addEventListener("change", (event) => {
      const project = projects.find(
        (row) => projectKey(row) === event.target.value,
      );
      if (project) setProject(project);
      render();
    });
    dialog.appendChild(projectSelect);
    const projectName = state.project ? projectKey(state.project) : "";
    dialog.appendChild(fieldLabel(
      documentNode,
      `Default ${noun} for ${name} in ${projectName}`,
    ));
    const choices = state.project
      ? optionsForProject(data, kind, state.project) : [];
    if (pending.has(projectName)) {
      dialog.appendChild(el(documentNode, "p", "workflow-field-help", "loading…"));
    } else if (failures[projectName]) {
      renderError(dialog, failures[projectName]);
      const retry = button(documentNode, "Retry plan read", "workflow-button compact");
      retry.addEventListener("click", () => { loadPlans(state.project); render(); });
      dialog.appendChild(retry);
    } else if (choices.length) {
      const valueSelect = el(documentNode, "select", "workflow-field");
      for (const choice of choices) {
        const value = String(choice.id);
        valueSelect.appendChild(option(
          documentNode, value, choice.slug || choice.name || value, state.value,
        ));
      }
      valueSelect.value = state.value;
      valueSelect.addEventListener("change", (event) => {
        state.value = event.target.value;
      });
      dialog.appendChild(valueSelect);
    } else {
      dialog.appendChild(el(
        documentNode, "p",
        "workflow-field-help workflow-empty-options",
        `${projectName || "This project"} has no ${noun}s yet.`,
      ));
    }
    if (state.project) {
      dialog.appendChild(checkbox(
        documentNode,
        state.applyToAll,
        `Apply to every workflow in ${projectName}`,
        () => {
          state.applyToAll = !state.applyToAll;
          render();
        },
      ));
    }
    appendWorkflowDialogFooter(documentNode, dialog, {
      impact: "",
      confirmText: "Set default",
      dismiss: shell.dismiss,
      activate: shell.activate,
      disabled: !choices.length || pending.has(projectName) || Boolean(failures[projectName]),
      save: () => save({
        project: projectName,
        value: state.value,
        applyToAll: state.applyToAll,
      }),
    });
  };
  render();
}
