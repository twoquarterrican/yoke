"""Event names emitted by document-led execution."""

CLAIM_ACQUIRED_EVENT = "StrategyDocClaimAcquired"
CLAIM_RELEASED_EVENT = "StrategyDocClaimReleased"
CLAIM_BREAK_GLASS_EVENT = "StrategyDocClaimBreakGlassReleased"
REVISION_RESTORED_EVENT = "StrategyDocRevisionRestored"
COORDINATION_APPENDED_EVENT = "StrategyDocCoordinationAppended"

__all__ = [
    "CLAIM_ACQUIRED_EVENT",
    "CLAIM_BREAK_GLASS_EVENT",
    "CLAIM_RELEASED_EVENT",
    "COORDINATION_APPENDED_EVENT",
    "REVISION_RESTORED_EVENT",
]
