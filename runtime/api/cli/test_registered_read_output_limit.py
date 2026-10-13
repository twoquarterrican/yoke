"""Atomic output refusal and registry coverage for CLI reads."""

import json

import pytest

from yoke_cli.transport.output_limit import (
    READ_OUTPUT_LIMIT_BYTES,
    read_output_scope,
)
from yoke_cli.transport.public_ref_display import emit_response
from yoke_contracts.api.function_call import FunctionCallResponse
from yoke_contracts.registered_reads import READ_FUNCTION_IDS
from runtime.api.tools.read_function_catalog import registered_read_ids


def response(function="qa.plan.list", result=None):
    return FunctionCallResponse(
        success=True, function=function, version="v1", result=result or {}
    )


def test_read_catalog_matches_all_registrations():
    assert READ_FUNCTION_IDS == registered_read_ids()


@pytest.mark.parametrize("json_mode", [True, False])
def test_oversized_read_refuses_without_partial_answer(capsys, json_mode):
    raw = response(result={"rows": [{"secret_marker": "x" * READ_OUTPUT_LIMIT_BYTES}]})
    assert emit_response(raw, json_mode=json_mode) == 1
    output = capsys.readouterr()
    assert "secret_marker" not in output.out + output.err
    assert "read_output_limit_exceeded" in output.out + output.err
    assert "yoke qa plan list" in output.out + output.err
    assert "--full" in output.out + output.err
    if json_mode:
        assert json.loads(output.out)["success"] is False
        assert not output.err


def test_human_writer_stderr_is_bounded_atomically(capsys):
    def writer(raw, stdout, stderr):
        print("partial answer", file=stdout)
        print("é" * READ_OUTPUT_LIMIT_BYTES, file=stderr)

    assert emit_response(response(), json_mode=False, human_writer=writer) == 1
    output = capsys.readouterr()
    assert "partial answer" not in output.out
    assert "read_output_limit_exceeded" in output.err


@pytest.mark.parametrize("json_mode", [True, False])
def test_full_returns_every_byte(capsys, json_mode):
    value = "z" * (READ_OUTPUT_LIMIT_BYTES + 1)
    with read_output_scope(["--full"]):
        assert emit_response(response(result={"body": value}), json_mode=json_mode) == 0
    assert value in capsys.readouterr().out


def test_full_does_not_escape_its_invocation():
    from yoke_cli.transport.output_limit import full_output_requested

    with read_output_scope(["--full"]):
        assert full_output_requested()
    assert not full_output_requested()
    with read_output_scope(["--", "--full"]):
        assert not full_output_requested()


def test_mutation_receipt_is_not_replaced_after_the_write(capsys):
    value = "m" * (READ_OUTPUT_LIMIT_BYTES + 1)
    assert emit_response(response("items.create", {"body": value}), json_mode=True) == 0
    assert value in capsys.readouterr().out


def test_registered_read_help_teaches_full_without_requesting_it():
    import argparse
    from yoke_cli.commands._helpers import parse_or_usage_error

    parser = argparse.ArgumentParser(prog="read")
    with read_output_scope([], "projects.list"):
        parsed = parse_or_usage_error(parser, [], "read")
    assert parsed.full is False
    assert "--full" in parser.format_help()
