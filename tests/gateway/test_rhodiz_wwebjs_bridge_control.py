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
