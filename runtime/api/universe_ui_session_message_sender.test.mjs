import assert from "node:assert/strict";
import test from "node:test";
import { senderDescription } from "../../packages/yoke-core/src/yoke_core/ui/static/universe_session_message_actors.js";

test("an engine message names Yoke with no actor kind or surface", () => {
  assert.equal(
    senderDescription({ sender_actor_id: null, sender_actor_label: "Yoke" }),
    "Yoke",
  );
});

test("an actor's message keeps its kind and surface", () => {
  assert.equal(
    senderDescription({
      sender_actor_id: 1,
      sender_actor_label: "Ben",
      sender_actor_kind: "human",
      sender_surface: "cli",
    }),
    "Ben (human, cli)",
  );
});
