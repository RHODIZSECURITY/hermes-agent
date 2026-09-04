from types import SimpleNamespace

import pytest

from gateway.run import GatewayRunner
from hermes_cli.plugins import VALID_HOOKS


def _runner():
    runner = object.__new__(GatewayRunner)
    runner.session_store = SimpleNamespace()
    # Most hook tests are about ownership/fall-through rather than audio.
    # Keep voice disabled unless a test explicitly opts into that seam.
    runner._should_send_voice_reply = lambda *args, **kwargs: False
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
async def test_gateway_turn_handler_owned_turn_honors_voice_output(monkeypatch):
    monkeypatch.setattr(
        "hermes_cli.lifecycle.invoke_hook",
        lambda name, **kwargs: [{"action": "handled", "response": "RHODIZ voice reply"}],
    )
    runner = _runner()
    seen = {}

    def should_voice(event, response, agent_messages, already_sent=False):
        seen["gate"] = (response, agent_messages, already_sent)
        return True

    async def send_voice(event, response):
        seen["sent"] = response
        event._tts_only_voice_delivered = True
        return True

    runner._should_send_voice_reply = should_voice
    runner._send_voice_reply = send_voice
    event = SimpleNamespace(internal=False)
    result = await runner._run_gateway_turn_handler(
        event=event, source=SimpleNamespace(), session_key="whatsapp:owner"
    )

    assert result == "RHODIZ voice reply"
    assert seen["gate"] == ("RHODIZ voice reply", [], False)
    assert seen["sent"] == "RHODIZ voice reply"
    assert event._tts_only_voice_delivered is True


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
