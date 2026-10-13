// First-run progress follows organization state in every hosting mode.
import { callFunction, el, labelledField } from "./universe_view_support.js";

const STEPS = ["Sign in", "Enter code", "Create org", "Connect machine"];
const localTime = (instant) => new Date(instant).toLocaleTimeString([], {
  hour: "numeric", minute: "2-digit", timeZoneName: "short",
});

function progress(doc, approved) {
  const list = el(doc, "ol", "machine-approval-steps");
  list.setAttribute("aria-label", "Setup progress");
  STEPS.forEach((label, index) => {
    const done = approved || index < 3;
    const step = el(doc, "li", done ? "done" : "active");
    if (!done) step.setAttribute("aria-current", "step");
    const disc = el(doc, "span", "machine-approval-disc", done ? "✓" : index + 1);
    disc.setAttribute("aria-hidden", "true");
    step.appendChild(disc);
    step.appendChild(el(doc, "span", "machine-approval-step-label", label));
    list.appendChild(step);
  });
  return list;
}

function outcome(doc, body, title, recovery, success = false) {
  const line = el(doc, "div", `machine-approval-outcome ${success ? "good" : "warn"}`);
  line.setAttribute("role", success ? "status" : "alert");
  line.appendChild(el(doc, "strong", null, title));
  if (recovery) line.appendChild(el(doc, "p", null, recovery));
  body.appendChild(line);
}

function terminalCallout(doc) {
  const callout = el(doc, "div", "machine-approval-next");
  const svg = doc.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const [tag, attributes] of [
    ["rect", { x: 2.5, y: 4, width: 19, height: 16, rx: 2.5 }],
    ["path", { d: "M7 10l3 2.5L7 15M12.5 15.5H17" }],
  ]) {
    const node = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, value));
    svg.appendChild(node);
  }
  callout.appendChild(svg);
  callout.appendChild(el(doc, "strong", null, "Return to your terminal"));
  return callout;
}

function facts(doc, authorization, org, approved) {
  const table = el(doc, "dl", "machine-approval-facts");
  const row = (label, values) => {
    const group = el(doc, "div", "machine-approval-fact");
    group.appendChild(el(doc, "dt", null, label));
    const value = el(doc, "dd");
    values.forEach((node) => value.appendChild(node));
    group.appendChild(value);
    table.appendChild(group);
  };
  if (authorization.machine) {
    const detail = [authorization.platform, authorization.machine_id && `machine ${authorization.machine_id}`].filter(Boolean).join(" · ");
    row("Machine", [el(doc, "b", null, authorization.machine),
      ...(detail ? [el(doc, "span", "machine-approval-quiet", detail)] : [])]);
  }
  row("One-time code", [el(doc, "span", "machine-approval-code", authorization.code),
    ...(approved ? [] : [el(doc, "span", "machine-approval-quiet", "must match your terminal")])]);
  row("Organization", [el(doc, "span", null, org.name)]);
  if (!approved) {
    const time = el(doc, "time", null, localTime(authorization.expires_at));
    time.setAttribute("datetime", authorization.expires_at);
    const minutes = Math.max(1, Math.ceil((Date.parse(authorization.expires_at) - Date.now()) / 60000));
    row("Expires", [time, el(doc, "span", "machine-approval-quiet", `in ${minutes} ${minutes === 1 ? "minute" : "minutes"}`)]);
  }
  return table;
}

function codeEntry(context, body, lede) {
  const doc = context.document;
  if (lede) body.appendChild(el(doc, "p", "machine-approval-lede", "Enter the one-time code shown in your terminal."));
  const form = el(doc, "form", "machine-approval-form");
  const input = el(doc, "input");
  Object.assign(input, { required: true, maxLength: 32, autocomplete: "off", spellcheck: false, placeholder: "XXXX-XXXX" });
  form.appendChild(labelledField(doc, "One-time code", input, "machine-approval-field"));
  const actions = el(doc, "div", "machine-approval-actions");
  const submit = el(doc, "button", null, "Continue");
  submit.type = "submit";
  actions.appendChild(submit);
  form.appendChild(actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const code = input.value.trim();
    if (code) context.navigate(`/machine-approval/${encodeURIComponent(code)}`);
  });
  body.appendChild(form);
}

export function renderMachineApproval(context, main, _scope, code, page = {}) {
  const doc = context.document;
  const head = el(doc, "div", "machine-approval-head");
  const card = el(doc, "section", "machine-approval-card");
  card.setAttribute("aria-label", "Machine request");
  main.replaceChildren(head, card);
  const mounted = () => context.isMounted() && main.isConnected !== false && main.contains(card);
  let authorization, org, firstRun = false, timer;
  const clock = doc.defaultView || globalThis;
  const title = (text) => {
    if (page.setPageHead) page.setPageHead({ title: text });
    else head.appendChild(el(doc, "h1", "title", text));
  };
  function paint() {
    clock.clearTimeout(timer);
    head.replaceChildren();
    card.replaceChildren();
    const decision = authorization?.decision;
    const approved = decision === "approve";
    const expired = authorization && !decision && Date.parse(authorization.expires_at) <= Date.now();
    title(approved ? "Machine connected" : authorization && !decision && !expired ? "Approve this machine" : "Connect your machine");
    if (firstRun) head.appendChild(progress(doc, approved));
    if (!authorization) { codeEntry(context, card, true); return; }
    if (decision === "deny") { outcome(doc, card, "Request denied", "Nothing was authorized."); return; }
    if (expired) { outcome(doc, card, `This code expired at ${localTime(authorization.expires_at)}`, "Nothing was authorized."); return; }
    if (approved) {
      outcome(doc, card, `✓ ${authorization.machine || "Your machine"} is connected to ${org.name}`, null, true);
      card.appendChild(terminalCallout(doc));
      card.appendChild(facts(doc, authorization, org, true));
      return;
    }
    card.appendChild(el(doc, "p", "machine-approval-lede", "Approve only if this code matches the one in your terminal."));
    card.appendChild(facts(doc, authorization, org, false));
    const actions = el(doc, "div", "machine-approval-actions");
    const status = el(doc, "p", "machine-approval-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    for (const [action, label] of [["approve", "Approve machine"], ["deny", "Deny"]]) {
      const button = el(doc, "button", action === "deny" ? "secondary" : null, label);
      button.type = "button";
      button.addEventListener("click", async () => {
        clock.clearTimeout(timer);
        Array.from(actions.children).forEach((node) => { node.disabled = true; });
        status.textContent = "Recording your decision…";
        try {
          const reply = await callFunction(context.client, "machine_authorization.resolve", { code, action });
          if (!mounted()) return;
          if (!reply.envelope?.success) {
            if (["authorization_expired", "authorization_consumed", "authorization_unavailable"].includes(reply.envelope?.error?.code)) { await load(); return; }
            throw new Error(reply.envelope?.error?.message || "approval_failed: the decision could not be recorded");
          }
          authorization.decision = reply.envelope.result.authorization.decision;
          paint();
        } catch (error) {
          if (!mounted()) return;
          status.textContent = `${error.message || error}. Retry your decision, or return to your terminal to start a fresh connection.`;
          Array.from(actions.children).forEach((node) => { node.disabled = false; });
          schedule();
        }
      });
      actions.appendChild(button);
    }
    card.appendChild(actions);
    card.appendChild(status);
    schedule();
  }
  function schedule() {
    const delay = Math.max(0, Math.min(60000, Date.parse(authorization.expires_at) - Date.now()));
    timer = clock.setTimeout(() => { if (mounted()) paint(); }, delay);
    timer?.unref?.();
  }
  async function load() {
    try {
      const requests = [["organizations.get", {}], ["machine.list", {}],
        ...(code ? [["machine_authorization.get", { code }]] : [])];
      const replies = await Promise.all(requests.map(([id, payload]) => callFunction(context.client, id, payload)));
      if (!mounted()) return;
      for (const reply of replies.slice(0, 2)) {
        if (!reply.envelope?.success) throw new Error(reply.envelope?.error?.message || "organization_state_unavailable: setup facts could not be read");
      }
      org = replies[0].envelope.result;
      firstRun = replies[1].envelope.result.count === 0;
      const reply = replies[2];
      if (reply && !reply.envelope?.success) {
        const error = reply.envelope?.error || {};
        authorization = undefined;
        paint();
        card.replaceChildren();
        if (["authorization_unavailable", "authorization_consumed", "not_found"].includes(error.code) || reply.status === 404) {
          outcome(doc, card, "That code isn't available", "Check the code in your terminal and try again.");
          codeEntry(context, card, false);
        } else if (error.code === "authorization_expired") {
          outcome(doc, card, "This code expired", "Nothing was authorized.");
        } else {
          outcome(doc, card, error.message || "authorization_read_failed: the request could not be read", "Reload to retry, or return to your terminal to start a fresh connection.");
        }
        return;
      }
      authorization = reply?.envelope.result.authorization;
      paint();
    } catch (error) {
      if (!mounted()) return;
      head.replaceChildren();
      title("Connect your machine");
      card.replaceChildren();
      outcome(doc, card, error.message || "authorization_read_failed: the request could not be read", "Reload to retry, or return to your terminal to start a fresh connection.");
    }
  }
  title("Connect your machine");
  card.appendChild(el(doc, "p", "machine-approval-lede", "Loading machine request…"));
  return load();
}
