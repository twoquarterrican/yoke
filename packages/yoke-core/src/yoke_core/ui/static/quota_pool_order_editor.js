import { callFunction, el, section } from "./universe_view_support.js";

export function renderCursorQuotaOrder(context, parent, pools, onSaved) {
  const documentNode = context.document;
  const panel = section(documentNode, "Cursor quota order");
  parent.appendChild(panel);
  panel.renderEnvelope(null, (body) => {
    const table = el(documentNode, "table", "items cursor-quota-order");
    const tbody = el(documentNode, "tbody");
    const buttons = [];
    const error = el(documentNode, "p", "error");
    error.hidden = true;
    error.setAttribute("role", "alert");
    pools.forEach((pool, index) => {
      const row = el(documentNode, "tr");
      row.appendChild(el(documentNode, "td", "level-rank", String(index + 1)));
      row.appendChild(el(documentNode, "td", null, pool));
      const actions = el(documentNode, "td");
      const button = el(documentNode, "button", "quota-order-move", index === 0 ? "↓" : "↑");
      button.type = "button";
      button.setAttribute("aria-label", `Move ${pool} ${index === 0 ? "down" : "up"}`);
      button.addEventListener("click", async () => {
        buttons.forEach((control) => { control.disabled = true; });
        error.hidden = true;
        try {
          const response = await callFunction(context.client, "universe.cursor_quota_order.set", { pools: [...pools].reverse() });
          if (!context.isMounted()) return;
          if (response.status !== 200 || !response.envelope.success) {
            throw new Error(response.envelope.error?.message || "cursor_quota_order_set_failed: retry or ask an org admin to set the order.");
          }
          await onSaved();
        } catch (failure) {
          if (!context.isMounted()) return;
          error.textContent = String(failure.message || failure);
          error.hidden = false;
          buttons.forEach((control) => { control.disabled = false; });
        }
      });
      buttons.push(button);
      actions.appendChild(button);
      row.appendChild(actions);
      tbody.appendChild(row);
    });
    table.appendChild(tbody);
    body.appendChild(table);
    body.appendChild(error);
  });
  return panel;
}
