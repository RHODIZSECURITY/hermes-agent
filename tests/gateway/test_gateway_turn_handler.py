from types import SimpleNamespace

import pytest

from gateway.run import GatewayRunner
from hermes_cli.plugins import VALID_HOOKS


def _runner():
    runner = object.__new__(GatewayRunner)
    runner.session_store = SimpleNamespace()
    return runner


@pytest.mark.asyncio
async def test_gateway_turn_handler_can_own_authorized_turn(monkeypatch):
    seen = {}

    def fake_invoke(name, **kwargs):
        seen["name"] = name
        seen["session_key"] = kwargs["session_key"]
        return [{"action": "handled", "response": "RHODIZ core reply"}]

    monkeypatch.setattr("hermes_cli.lifecycle.invoke_hook", fake_invoke)
    event = SimpleNamespace(internal=False)
    source = SimpleNamespace()
    result = await _runner()._run_gateway_turn_handler(
        event=event, source=source, session_key="whatsapp:owner"
    )
    assert result == "RHODIZ core reply"
    assert seen == {"name": "gateway_turn_handler", "session_key": "whatsapp:owner"}


@pytest.mark.asyncio
async def test_gateway_turn_handler_allow_falls_through(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda name, **kwargs: [{"action": "allow"}],
    )
    result = await _runner()._run_gateway_turn_handler(
        event=SimpleNamespace(internal=False),
        source=SimpleNamespace(),
        session_key="photon:owner",
    )
    assert result is None


@pytest.mark.asyncio
async def test_gateway_turn_handler_never_handles_internal_events(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("hook should not run")

    monkeypatch.setattr("hermes_cli.lifecycle.invoke_hook", fail)
    result = await _runner()._run_gateway_turn_handler(
        event=SimpleNamespace(internal=True),
        source=SimpleNamespace(),
        session_key="internal",
    )
    assert result is None


def test_gateway_turn_handler_is_registered_hook():
    assert "gateway_turn_handler" in VALID_HOOKS
