"""No-account tests for RHODIZ WWEBJS 1.34.7 / Hermes v0.22.5 compatibility.

Never start a browser, touch production phone sessions or execute npm.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from gateway.whatsapp_identity import to_whatsapp_jid
from plugins.platforms.whatsapp.adapter import WhatsAppAdapter
from plugins.platforms.whatsapp.bridge_integrity import (
    _FILES, _MARKER, is_rhodiz_wwebjs_bridge, verified_bridge_integrity,
)

LID = "77214955630717@lid"
OTHER_LID = "77214955630718@lid"


def _bridge_files(root: Path) -> None:
    (root / "package.json").write_text(
        json.dumps({"name": "rhodiz-hermes-whatsapp-web-bridge"}), encoding="utf-8"
    )
    for relative in _FILES:
        f = root / relative
        f.parent.mkdir(parents=True, exist_ok=True)
        if relative != "package.json":
            f.write_text("fixed-test-" + relative, encoding="utf-8")


def _stamp(root: Path) -> None:
    data = {"schemaVersion": 1, "files": {
        f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in _FILES
    }}
    f = root / _MARKER
    f.parent.mkdir(exist_ok=True, parents=True)
    f.write_text(json.dumps(data), encoding="utf-8")


def test_verified_bridge_requires_exact_audited_artifact(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    _bridge_files(root)
    assert is_rhodiz_wwebjs_bridge(root)
    assert not verified_bridge_integrity(root)
    _stamp(root)
    assert verified_bridge_integrity(root)
    (root / "package-lock.json").write_text("tampered", encoding="utf-8")
    assert not verified_bridge_integrity(root)
    _stamp(root)
    assert verified_bridge_integrity(root)
    (root / _MARKER).write_text("not-json", encoding="utf-8")
    assert not verified_bridge_integrity(root)
    _stamp(root)
    (root / "node_modules/minimatch/package.json").unlink()
    assert not verified_bridge_integrity(root)


def test_verified_bridge_rejects_symlinked_dependency(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    _bridge_files(root)
    f = root / "node_modules/minimatch/package.json"
    target = tmp_path / "untrusted"
    target.write_bytes(f.read_bytes())
    f.unlink()
    f.symlink_to(target)
    _stamp(root)
    assert not verified_bridge_integrity(root)


def test_other_bridge_is_not_treated_as_rhodiz_wwebjs(tmp_path):
    root = tmp_path / "baileys"
    root.mkdir()
    (root / "package.json").write_text('{"name":"hermes-whatsapp-bridge"}')
    assert not is_rhodiz_wwebjs_bridge(root)


def test_unaudited_rhodiz_bridge_refuses_implicit_npm_install(tmp_path):
    root = tmp_path / "bridge"
    root.mkdir()
    _bridge_files(root)
    adapter = WhatsAppAdapter.__new__(WhatsAppAdapter)
    adapter._set_fatal_error = MagicMock()
    assert adapter._ensure_bridge_deps(root) is False
    adapter._set_fatal_error.assert_called_once()
    args, kwargs = adapter._set_fatal_error.call_args
    assert args[0] == "rhodiz_whatsapp_bridge_unverified"
    assert kwargs["retryable"] is False
    assert "npm" in str(args[1])
    _stamp(root)
    assert adapter._ensure_bridge_deps(root) is True
    adapter._set_fatal_error.assert_called_once()


def _mock_adapter(bridge: Path, session: Path, health: dict) -> WhatsAppAdapter:
    adapter = WhatsAppAdapter.__new__(WhatsAppAdapter)
    from gateway.config import Platform
    adapter.platform = Platform.WHATSAPP
    adapter._session_path = session
    adapter._bridge_script = str(bridge)
    adapter._foreign_bridge_session = None
    adapter._bridge_probe_timed_out = False
    adapter._send_read_receipts = False
    adapter._probe_bridge_health = AsyncMock(return_value=(True, health))
    adapter._attach_to_bridge = MagicMock()
    adapter._mark_connected = MagicMock()
    adapter._wire_plugin_handlers = MagicMock()
    return adapter


@pytest.mark.asyncio
async def test_bridge_without_owning_session_is_never_adopted(tmp_path):
    bridge = tmp_path / "bridge.js"
    bridge.write_text("test bridge", encoding="utf-8")
    adapter = _mock_adapter(bridge, tmp_path / "account",
                            {"status": "connected", "scriptHash": hashlib.sha256(bridge.read_bytes()).hexdigest()[:16],
                             "sendReadReceipts": False})
    assert await adapter._reuse_running_bridge(bridge) is False
    assert adapter._foreign_bridge_session
    adapter._attach_to_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_other_phone_session_is_never_adopted(tmp_path):
    bridge = tmp_path / "bridge.js"
    bridge.write_text("test bridge", encoding="utf-8")
    adapter = _mock_adapter(bridge, tmp_path / "authorized-account",
                            {"status": "connected", "session": str(tmp_path / "different-account"),
                             "scriptHash": hashlib.sha256(bridge.read_bytes()).hexdigest()[:16],
                             "sendReadReceipts": False})
    assert await adapter._reuse_running_bridge(bridge) is False
    assert adapter._foreign_bridge_session
    adapter._attach_to_bridge.assert_not_called()


@pytest.mark.asyncio
async def test_exact_session_and_same_bridge_hash_may_be_adopted(tmp_path):
    bridge = tmp_path / "bridge.js"
    bridge.write_text("test bridge", encoding="utf-8")
    session = tmp_path / "authorized-account"
    adapter = _mock_adapter(bridge, session, {
        "status": "connected",
        "session": str(session),
        "scriptHash": hashlib.sha256(bridge.read_bytes()).hexdigest()[:16],
        "sendReadReceipts": False,
    })
    assert await adapter._reuse_running_bridge(bridge) is True
    assert adapter._foreign_bridge_session is None
    adapter._mark_connected.assert_called_once()
    adapter._attach_to_bridge.assert_called_once_with(None)


def test_lid_target_remains_native_through_normalizer():
    assert to_whatsapp_jid(LID) == LID
    assert to_whatsapp_jid(OTHER_LID) == OTHER_LID
    assert to_whatsapp_jid("120363001234567890@g.us") == "120363001234567890@g.us"
