"""Negative tests for RHODIZ WhatsApp HTTP control-token contract (no credentials)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[2] / "plugins" / "platforms" / "whatsapp" / "bridge_control.py"
SPEC = importlib.util.spec_from_file_location("rhodiz_bridge_control", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

FAKE_TOKEN = "ab" * 32


@pytest.mark.parametrize("invalid", ["", None, "short", "ab" * 32 + "0", "zz" * 32, " " + FAKE_TOKEN])
def test_first_party_bridge_rejects_missing_or_malformed_token(invalid):
    with pytest.raises(ValueError, match="missing or invalid"):
        MODULE.control_headers(True, invalid)


def test_scoped_token_is_not_inferred_from_global_environment(monkeypatch):
    monkeypatch.setenv("RHODIZ_WHATSAPP_BRIDGE_TOKEN", FAKE_TOKEN)
    with pytest.raises(ValueError, match="missing or invalid"):
        MODULE.control_headers(True, "")


def test_first_party_receives_exact_bearer_header():
    assert MODULE.control_headers(True, FAKE_TOKEN) == {"Authorization": "Bearer " + FAKE_TOKEN}


def test_upstream_baileys_contract_remains_unchanged():
    assert MODULE.control_headers(False, "") == {}


def test_adapter_resolves_bearer_from_own_profile_only(tmp_path, monkeypatch):
    from plugins.platforms.whatsapp import adapter as adapter_module
    bridge = tmp_path / "bridge.js"
    bridge.write_text("synthetic", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        '{"name":"rhodiz-hermes-whatsapp-web-bridge"}', encoding="utf-8"
    )
    monkeypatch.setenv(MODULE.TOKEN_ENV, "cd" * 32)  # another profile, must not win
    monkeypatch.setattr(adapter_module, "_wenv", lambda name, default="": FAKE_TOKEN)
    assert adapter_module._rhodiz_bridge_auth_headers(bridge) == {
        "Authorization": "Bearer " + FAKE_TOKEN
    }
    monkeypatch.setattr(adapter_module, "_wenv", lambda name, default="": "")
    with pytest.raises(ValueError, match="missing or invalid"):
        adapter_module._rhodiz_bridge_auth_headers(bridge)


def test_adapter_gateway_posts_include_authorization(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from plugins.platforms.whatsapp import adapter as adapter_module

    (tmp_path / "package.json").write_text(
        '{"name":"rhodiz-hermes-whatsapp-web-bridge"}', encoding="utf-8"
    )
    bridge = tmp_path / "bridge.js"
    bridge.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(adapter_module, "_wenv", lambda name, default="": FAKE_TOKEN)
    adapter = adapter_module.WhatsAppAdapter.__new__(adapter_module.WhatsAppAdapter)
    adapter._bridge_script = str(bridge)
    adapter._bridge_port = 3000
    sentinel = object()
    post = MagicMock(return_value=sentinel)
    adapter._http_session = SimpleNamespace(post=post)
    assert adapter._bridge_req("post", "send", 5, json={"message": "test"}) is sentinel
    assert post.call_args.kwargs["headers"] == {"Authorization": "Bearer " + FAKE_TOKEN}
    assert post.call_args.kwargs["json"] == {"message": "test"}


def test_non_rhodiz_bridge_does_not_require_new_header(tmp_path, monkeypatch):
    from plugins.platforms.whatsapp import adapter as adapter_module
    (tmp_path / "package.json").write_text('{"name":"hermes-whatsapp-bridge"}', encoding="utf-8")
    monkeypatch.setattr(adapter_module, "_wenv", lambda name, default="": "")
    assert adapter_module._rhodiz_bridge_auth_headers(tmp_path / "bridge.js") == {}
