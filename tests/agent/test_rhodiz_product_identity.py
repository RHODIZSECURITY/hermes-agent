from __future__ import annotations

import json

import pytest

from agent.product_identity import (
    assert_rhodiz_model_context_clean,
    filter_internal_skill_prompt,
    is_internal_maintenance_skill,
    is_rhodiz_product_mode,
    sanitize_model_visible_text,
    sanitize_tool_definitions,
)


def _home(tmp_path):
    (tmp_path / ".rhodiz-product").write_text("RHODIZ IA\n", encoding="utf-8")
    return tmp_path


def test_product_mode_marker_is_internal_and_deterministic(tmp_path):
    assert is_rhodiz_product_mode(_home(tmp_path)) is True


def test_internal_skills_are_removed_from_model_visible_index(tmp_path):
    home = _home(tmp_path)
    raw = "\n".join([
        "- github: GitHub workflows",
        "- hermes-agent: internal maintenance",
        "- inspecting-hermes-desktop-dom: internal DOM",
        "- python-debugpy: Python debugger",
    ])
    out = filter_internal_skill_prompt(raw, home=home)
    assert "github" in out and "python-debugpy" in out
    assert "- hermes-agent:" not in out
    assert "- inspecting-hermes-desktop-dom:" in out


def test_reviewed_technical_skill_names_are_visible_without_rebranding_identity(tmp_path):
    home = _home(tmp_path)
    raw = "\n".join([
        "- hermes-agent: framework identity and maintenance",
        "- hermes-agent-skill-authoring: author valid SKILL.md documents",
        "- inspecting-hermes-desktop-dom: inspect desktop UI via CDP",
        "- inspecting-hermes-other: unreviewed framework reference",
    ])
    index = filter_internal_skill_prompt(raw, home=home)
    assert "- hermes-agent:" not in index
    assert "inspecting-hermes-other" not in index
    assert "hermes-agent-skill-authoring" in index
    assert "inspecting-hermes-desktop-dom" in index
    assert is_internal_maintenance_skill("hermes-agent", home=home)
    assert not is_internal_maintenance_skill("hermes-agent-skill-authoring", home=home)
    assert not is_internal_maintenance_skill("software-development/inspecting-hermes-desktop-dom", home=home)
    assert is_internal_maintenance_skill("hermes-agent-unreviewed", home=home)

    output = sanitize_model_visible_text(
        "Use hermes-agent-skill-authoring and inspecting-hermes-desktop-dom. "
        "Hermes Agent is the implementation, not the product identity.",
        home=home,
    )
    assert "hermes-agent-skill-authoring" in output
    assert "inspecting-hermes-desktop-dom" in output
    assert "Hermes Agent" not in output
    assert "RHODIZ IA" in output
    assert_rhodiz_model_context_clean(output, home=home)
    with pytest.raises(RuntimeError):
        assert_rhodiz_model_context_clean("You are Hermes Agent", home=home)


def test_tool_schema_sanitizer_changes_only_prose_not_dispatch_metadata(tmp_path):
    home = _home(tmp_path)
    tools = [{
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Run Hermes tools via from hermes_tools import terminal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "description": "Hermes execution mode",
                        "enum": ["hermes", "native"],
                    }
                },
            },
        },
    }]
    out = sanitize_tool_definitions(tools, home=home)
    blob = json.dumps(out)
    assert out[0]["function"]["name"] == "execute_code"
    assert out[0]["function"]["parameters"]["properties"]["mode"]["enum"] == ["hermes", "native"]
    assert "rhodiz_tools" in out[0]["function"]["description"]
    assert "Hermes execution mode" not in blob


def test_model_visible_text_and_clean_gate_remove_implementation_provenance(tmp_path):
    home = _home(tmp_path)
    out = sanitize_model_visible_text(
        "Hermes Agent by Nous Research; import hermes_tools; see hermes-agent docs",
        home=home,
    )
    assert "hermes" not in out.lower()
    assert "nous research" not in out.lower()
    assert "rhodiz_tools" in out
    assert_rhodiz_model_context_clean(out, home=home)
    with pytest.raises(RuntimeError):
        assert_rhodiz_model_context_clean("Hermes", home=home)


def test_internal_maintenance_skill_gate_is_product_scoped(tmp_path):
    home = _home(tmp_path)
    assert is_internal_maintenance_skill("hermes-agent", home=home) is True
    assert is_internal_maintenance_skill("autonomous-ai-agents/hermes-agent", home=home) is True
    assert is_internal_maintenance_skill("github", home=home) is False
    plain = tmp_path / "plain"
    plain.mkdir()
    assert is_internal_maintenance_skill("hermes-agent", home=plain) is False
