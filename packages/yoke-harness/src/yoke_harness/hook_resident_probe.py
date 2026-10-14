"""Read-only resident health protocol, separate from hook evaluation."""

from yoke_contracts.engine_version import installed_engine_version
from yoke_contracts.hook_evaluator_protocol import (
    HookEvaluatorRequest,
    receive_frame,
    send_frame,
)

# Capture when this resident loads, rather than rereading replaced wheel metadata.
_LOADED_VERSION = installed_engine_version()


def answer_probe(peer, frame: dict, loaded_revision: str) -> bool:
    if frame.get("kind") != "health":
        return False
    send_frame(
        peer,
        {
            "status": "health",
            "loaded_revision": loaded_revision,
            "engine_version": _LOADED_VERSION,
        },
    )
    return True


def receive_request(peer, loaded_revision: str) -> HookEvaluatorRequest | None:
    frame = receive_frame(peer)
    if answer_probe(peer, frame, loaded_revision):
        return None
    return HookEvaluatorRequest.from_mapping(frame)
