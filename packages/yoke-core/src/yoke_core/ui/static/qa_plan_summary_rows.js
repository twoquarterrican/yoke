import { callFunction } from "./universe_view_support.js";

// A picker/search needs every name, without the full probes and attachments.
// Keep pages bounded and discard partial catalogues when any page refuses.
export async function loadPlanSummaries(client, project) {
  const rows = [];
  let offset = 0;
  while (true) {
    const result = await callFunction(client, "qa.plan.list", {
      project: String(project), detail: "summary", limit: 100, offset,
    });
    if (result.status !== 200 || !result.envelope.success) return result;
    const page = result.envelope.result || {};
    rows.push(...(page.rows || []));
    if (page.next_offset == null) {
      return { ...result, envelope: { ...result.envelope,
        result: { ...page, rows },
      } };
    }
    if (page.next_offset <= offset) throw new Error(
      "plan_page_invalid: next_offset did not advance; retry the plan read.",
    );
    offset = page.next_offset;
  }
}
