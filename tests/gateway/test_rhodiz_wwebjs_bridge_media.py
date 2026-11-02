"""No-account tests for per-profile WhatsApp outbound media staging."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

import pytest

SRC = Path(__file__).resolve().parents[2] / "plugins" / "platforms" / "whatsapp" / "bridge_media.py"
SPEC = importlib.util.spec_from_file_location("rhodiz_media_staging_under_test", SRC)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def fake_media_cache(monkeypatch):
    from gateway.platforms import base

    calls = []

    def fake_cache_media_bytes(data, **kwargs):
        calls.append((data, kwargs))
        return SimpleNamespace(path="/secure/media/cache/cached.ogg")

    monkeypatch.setattr(base, "cache_media_bytes", fake_cache_media_bytes)
    return calls


def test_regular_document_staged_once(tmp_path, fake_media_cache):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7\ncontent")
    result = MODULE.stage_outbound_media(str(source), "document")
    assert result == "/secure/media/cache/cached.ogg"
    assert fake_media_cache[0][0] == source.read_bytes()
    assert fake_media_cache[0][1]["default_kind"] == "document"


def test_voice_stages_as_audio(tmp_path, fake_media_cache):
    source = tmp_path / "voice.ogg"
    source.write_bytes(b"OggS\x00data")
    MODULE.stage_outbound_media(str(source), "voice")
    assert fake_media_cache[0][1]["default_kind"] == "audio"


def test_refuses_symlinks_and_oversized_files_without_cache_write(tmp_path, fake_media_cache, monkeypatch):
    secret = tmp_path / "secret"
    secret.write_bytes(b"private")
    link = tmp_path / "voice.ogg"
    link.symlink_to(secret)
    with pytest.raises(OSError):
        MODULE.stage_outbound_media(str(link), "audio")
    assert fake_media_cache == []

    oversized = tmp_path / "oversized.pdf"
    oversized.write_bytes(b"0123456789")
    monkeypatch.setattr(MODULE, "MAX_MEDIA_BYTES", 8)
    with pytest.raises(ValueError, match="oversized"):
        MODULE.stage_outbound_media(str(oversized), "document")
    assert fake_media_cache == []


def test_relative_and_unsupported_are_rejected(fake_media_cache):
    with pytest.raises(ValueError, match="absolute"):
        MODULE.stage_outbound_media("relative", "image")
    with pytest.raises(ValueError, match="Unsupported"):
        MODULE.stage_outbound_media("/does/not/matter", "arbitrary")
