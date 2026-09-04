from __future__ import annotations

import logging
from types import MappingProxyType

import pytest

from hermes_cli.plugins import (
    MAX_SYSTEM_PROMPT_SECTIONS_TOTAL_CHARS,
    PluginContext,
    PluginManager,
    PluginManifest,
)


def _context(manager: PluginManager, name: str = "example-plugin") -> PluginContext:
    return PluginContext(
        PluginManifest(name=name, key=name, source="user"),
        manager,
    )


def test_registration_validates_stable_id_position_budget_and_duplicates():
    manager = PluginManager()
    ctx = _context(manager)

    for invalid_id in ("", "UPPER.case", "has space", "line\nbreak", "x" * 129):
        with pytest.raises(ValueError):
            ctx.register_system_prompt_section(invalid_id, "content")

    with pytest.raises(ValueError):
        ctx.register_system_prompt_section("example.rules", "content", position="priority-17")
    with pytest.raises(ValueError):
        ctx.register_system_prompt_section("example.rules", "content", max_chars=0)

    ctx.register_system_prompt_section("example.rules", "content")
    with pytest.raises(ValueError, match="already registered"):
        _context(manager, "other-plugin").register_system_prompt_section(
            "example.rules", "other content"
        )


def test_render_is_deterministic_bounded_and_session_info_is_read_only(caplog):
    manager = PluginManager()
    ctx = _context(manager)
    observed = []

    def render_b(info):
        observed.append(info)
        with pytest.raises(TypeError):
            info["session_id"] = "changed"
        return "B"

    ctx.register_system_prompt_section("example.z", render_b, max_chars=4)
    ctx.register_system_prompt_section("example.a", "A", max_chars=4)
    ctx.register_system_prompt_section("example.too-large", "12345", max_chars=4)

    with caplog.at_level(logging.WARNING, logger="hermes_cli.plugins"):
        rendered = manager.render_system_prompt_sections({"session_id": "session-1"})

    assert [(item.id, item.content) for item in rendered] == [
        ("example.a", "A"),
        ("example.z", "B"),
    ]
    assert isinstance(observed[0], MappingProxyType)
    assert observed[0]["session_id"] == "session-1"
    assert "exceeded max_chars" in caplog.text


def test_render_fails_open_for_callback_failure_wrong_type_and_aggregate_budget(caplog):
    manager = PluginManager()
    ctx = _context(manager)

    def boom(_info):
        raise RuntimeError("plugin exploded")

    ctx.register_system_prompt_section("example.boom", boom)
    ctx.register_system_prompt_section("example.wrong", lambda _info: {"not": "text"})
    chunk = (MAX_SYSTEM_PROMPT_SECTIONS_TOTAL_CHARS // 2) - 200
    ctx.register_system_prompt_section("example.first", "a" * chunk, max_chars=chunk)
    ctx.register_system_prompt_section("example.second", "b" * chunk, max_chars=chunk)
    ctx.register_system_prompt_section("example.zzlast", "c" * 500, max_chars=500)

    with caplog.at_level(logging.WARNING, logger="hermes_cli.plugins"):
        rendered = manager.render_system_prompt_sections({})

    assert [item.id for item in rendered] == ["example.first", "example.second"]
    assert "plugin exploded" in caplog.text
    assert "returned dict, not str" in caplog.text
    assert "aggregate" in caplog.text


def test_explicit_eight_kib_section_is_supported_for_bounded_product_persona():
    manager = PluginManager()
    ctx = _context(manager, "rhodiz-identity")
    content = "R" * 8000
    ctx.register_system_prompt_section(
        "rhodiz.personality", content, max_chars=8000
    )
    rendered = manager.render_system_prompt_sections({"session_id": "rhodiz"})
    assert [(item.id, item.content) for item in rendered] == [
        ("rhodiz.personality", content)
    ]


def test_product_prompt_markers_are_brand_neutral():
    from hermes_cli.plugins import (
        PLUGIN_SECTIONS_END,
        PLUGIN_SECTIONS_START,
        format_system_prompt_section,
    )
    rendered = format_system_prompt_section("rhodiz.personality", "RHODIZ IA")
    assert "hermes" not in PLUGIN_SECTIONS_START.lower()
    assert "hermes" not in PLUGIN_SECTIONS_END.lower()
    assert "hermes" not in rendered.lower()
    assert "agent-plugin-section-chars" in rendered
