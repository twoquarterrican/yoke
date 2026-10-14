"""CLI boundary tests for Pulumi state and stack config surfaces."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from yoke_cli.commands.adapters.projects_pulumi_state import (
    _read_checkpoint_operator_state,
)
from yoke_cli.main import main as cli_main
from yoke_contracts.api.function_call import (
    FunctionCallRequest,
    FunctionCallResponse,
)


def test_checkpoint_import_reads_0600_file_and_emits_only_receipt(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "deployment": {
                    "secrets_providers": {
                        "state": {
                            "url": "awskms://alias/yoke-pulumi",
                            "encryptedkey": "encrypted-sensitive-material",
                        }
                    }
                }
            }
        )
    )
    checkpoint.chmod(0o600)
    calls = []

    def dispatch(request: FunctionCallRequest) -> FunctionCallResponse:
        calls.append(request)
        return FunctionCallResponse(
            success=True,
            function=request.function,
            version=request.version,
            request_id=request.request_id,
            result={"mode": "register", "receipt_digest": "receipt123"},
        )

    stdout = io.StringIO()
    with (
        patch.dict("os.environ", {"YOKE_SESSION_ID": "test-session"}),
        patch(
            "yoke_core.domain.yoke_function_dispatch.dispatch",
            side_effect=dispatch,
        ),
        patch("yoke_cli.commands._helpers.ensure_handlers_loaded"),
        redirect_stdout(stdout),
    ):
        rc = cli_main(
            [
                "projects",
                "pulumi-state",
                "checkpoint-import",
                "--project",
                "yoke",
                "--stack",
                "yoke-platform-stage-vps",
                "--checkpoint-file",
                str(checkpoint),
            ]
        )
    assert rc == 0
    assert "mode: register" in stdout.getvalue()
    assert "receipt digest: receipt123" in stdout.getvalue()
    assert "encrypted-sensitive-material" not in stdout.getvalue()
    assert calls[0].function == "projects.pulumi_state.checkpoint_import"
    assert calls[0].payload == {
        "project": "yoke",
        "stack_name": "yoke-platform-stage-vps",
        "secrets_provider": "awskms://alias/yoke-pulumi",
        "encrypted_key": "encrypted-sensitive-material",
        "apply": False,
    }


def test_checkpoint_import_refuses_readable_or_malformed_file(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text("{}")
    checkpoint.chmod(0o644)
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        rc = cli_main(
            [
                "projects",
                "pulumi-state",
                "checkpoint-import",
                "--project",
                "yoke",
                "--stack",
                "stage",
                "--checkpoint-file",
                str(checkpoint),
            ]
        )
    assert rc == 2
    assert "chmod 600" in stderr.getvalue()

    checkpoint.chmod(0o600)
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        rc = cli_main(
            [
                "projects",
                "pulumi-state",
                "checkpoint-import",
                "--project",
                "yoke",
                "--stack",
                "stage",
                "--checkpoint-file",
                str(checkpoint),
            ]
        )
    assert rc == 2
    assert "secrets-provider state" in stderr.getvalue()


def test_checkpoint_import_reads_backend_checkpoint_shape(tmp_path):
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        json.dumps(
            {
                "checkpoint": {
                    "latest": {
                        "secrets_providers": {
                            "state": {
                                "url": "awskms://alias/yoke-pulumi",
                                "encryptedkey": "encrypted-sensitive-material",
                            }
                        }
                    }
                }
            }
        )
    )
    checkpoint.chmod(0o600)

    assert _read_checkpoint_operator_state(checkpoint) == (
        "awskms://alias/yoke-pulumi",
        "encrypted-sensitive-material",
    )
