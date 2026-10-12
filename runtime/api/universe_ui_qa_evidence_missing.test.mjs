import assert from "node:assert/strict";
import test from "node:test";

import { showArtifactResult } from "../../packages/yoke-core/src/yoke_core/ui/static/qa_evidence_artifact_view.js";
import { readOutcome } from "../../packages/yoke-core/src/yoke_core/ui/static/review_evidence_read.js";
import { FakeDocument } from "./universe_ui_dom_test_support.mjs";

const MISSING = {
  disposition: "evidence_missing",
  detail: "The recorded evidence no longer exists. Re-run the QA case.",
};

test("a read of deleted evidence is labelled missing with its recovery", () => {
  const outcome = readOutcome({
    status: 200,
    envelope: { success: true, result: MISSING },
  });

  assert.deepEqual(outcome, {
    ready: false,
    state: "Evidence missing",
    detail: MISSING.detail,
  });
});

test("the evidence view names missing evidence instead of a dead image", () => {
  const documentNode = new FakeDocument();
  const host = documentNode.createElement("div");

  const state = showArtifactResult(documentNode, host, { id: 6 }, MISSING);

  assert.equal(state, "evidence missing");
  assert.equal(host.textContent, MISSING.detail);
});
