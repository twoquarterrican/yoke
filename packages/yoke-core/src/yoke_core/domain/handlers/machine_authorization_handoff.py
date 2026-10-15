"""Hosted-service ingress for machine authorization codes."""

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from yoke_contracts.api.function_call import FunctionCallRequest
from yoke_core.domain.handlers.machine_authorization import _handle
from yoke_core.domain.machine_authorization_handoff import MATCH_CODE_PATTERN, handoff
from yoke_core.domain.machine_authorization_handoff_poll import handoff_poll


class AuthorizationHandoffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_code_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    user_code: StrictStr = Field(pattern="^" + MATCH_CODE_PATTERN + "$")
    machine_id: StrictStr
    machine_name: StrictStr = Field(min_length=1, max_length=150)
    platform: StrictStr = Field(min_length=1, max_length=80)
    expires_at: StrictStr
    org_id: int = Field(strict=True, gt=0)


def handle_handoff(request: FunctionCallRequest):
    return _handle(request, AuthorizationHandoffRequest, handoff)


class AuthorizationHandoffPollRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_code: StrictStr = Field(min_length=1, max_length=512, repr=False)
    machine_id: StrictStr
    machine_name: StrictStr = Field(min_length=1, max_length=150)
    org_id: int = Field(strict=True, gt=0)


def handle_handoff_poll(request: FunctionCallRequest):
    return _handle(request, AuthorizationHandoffPollRequest, handoff_poll)
