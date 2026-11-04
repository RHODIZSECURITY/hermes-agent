from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}
_INTERNAL_SKILL_TOKENS = (
    "hermes-agent",
    "inspecting-hermes",
    "nous research",
)
# Specific developer skills provide technical capabilities, not agent identity.
# Do not turn these dispatch identifiers into aliases during prompt sanitization.
_TECHNICAL_SKILL_NAMES = frozenset({
    "hermes-agent-skill-authoring",
    "inspecting-hermes-desktop-dom",
    "software-development/hermes-agent-skill-authoring",
    "software-development/inspecting-hermes-desktop-dom",
})
_TECHNICAL_SKILL_IDENTIFIER = re.compile(
    r"(?<![a-z0-9_-])(?:hermes-agent-skill-authoring|inspecting-hermes-desktop-dom)"
    r"(?![a-z0-9_-])", re.IGNORECASE,
)


def _is_supported_technical_skill(name: str) -> bool:
    return str(name or "").strip().lower() in _TECHNICAL_SKILL_NAMES



def _bypass_worker_bound() -> bool:
    """Whether a safe-mode / ignore-user-config worker policy is bound
    in this process. Such a worker runs on the frozen config snapshot
    bound at bootstrap and must not read profile files at all."""
    try:
        from agent.safe_worker_policy import (
            safe_worker_enabled,
            worker_ignores_user_config,
        )
        return safe_worker_enabled() or worker_ignores_user_config()
    except Exception:
        return False


def is_rhodiz_product_mode(home: str | Path | None = None) -> bool:
    """Return whether this process/profile is the RHODIZ IA product surface.

    The marker is runtime-only and is never injected into model context. SOUL
    detection is a compatibility fallback for deployments created before the marker.
    """
    raw = os.environ.get("RHODIZ_PRODUCT_MODE")
    if raw is not None:
        value = raw.strip().lower()
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
    root = Path(home).expanduser() if home is not None else Path(
        os.environ.get("HERMES_HOME") or (Path.home() / ".hermes")
    )
    if (root / ".rhodiz-product").is_file():
        return True
    if _bypass_worker_bound():
        # The SOUL.md compatibility fallback is user config by
        # definition; a bypass worker never reads it (its product
        # mode, when any, is declared by the launcher via the
        # environment branch above).
        return False
    try:
        soul = (root / "SOUL.md").read_text(encoding="utf-8")[:8192]
    except OSError:
        return False
    return "RHODIZ IA" in soul.upper()


def is_internal_maintenance_skill(name: str, *, home: str | Path | None = None) -> bool:
    """Return True for framework-maintenance skills hidden from RHODIZ product sessions.

    These skills remain installed on disk for operators and repository maintenance, but
    product-facing agents must not load them as authority about RHODIZ identity, voice,
    memory, or capabilities.
    """
    if not is_rhodiz_product_mode(home):
        return False
    lower = str(name or "").strip().lower()
    if _is_supported_technical_skill(lower):
        return False
    return bool(lower) and any(token in lower for token in _INTERNAL_SKILL_TOKENS)


def filter_internal_skill_prompt(text: str, *, home: str | Path | None = None) -> str:
    """Hide implementation-maintenance skills from RHODIZ's model-visible index."""
    if not text or not is_rhodiz_product_mode(home):
        return text
    kept: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
        # Allow only the two explicitly reviewed technical skill identifiers.
        # A line mentioning arbitrary framework internals remains excluded.
        if re.match(
            r"^\s*-\s*(?:software-development/)?"
            r"(?:hermes-agent-skill-authoring|inspecting-hermes-desktop-dom)\s*:",
            lower,
        ):
            kept.append(line)
            continue
        if any(token in lower for token in _INTERNAL_SKILL_TOKENS):
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def sanitize_model_visible_text(text: str, *, home: str | Path | None = None) -> str:
    """Remove implementation provenance from prose sent to the RHODIZ model.

    This is a defensive boundary, not the primary identity source. It changes
    descriptive prose only; dispatch keys and stored runtime identifiers stay intact.
    """
    if not isinstance(text, str) or not is_rhodiz_product_mode(home):
        return text
    # Preserve exact skill identifiers so the model can call skill_view(name)
    # using the real on-disk name. Other framework brand prose is still sanitized.
    protected: list[str] = []
    def _protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__RHODIZ_TECH_SKILL_ID_{len(protected) - 1}__"

    out = _TECHNICAL_SKILL_IDENTIFIER.sub(_protect, text)
    # The executable-code facade has a product-facing alias; keep imports usable.
    out = re.sub(r"\bhermes_tools\b", "rhodiz_tools", out, flags=re.I)
    # Internal homes are implementation paths, not product concepts.
    out = re.sub(r"~?/[^\s`'\"]*\.hermes(?=/|\b)", "the RHODIZ runtime data directory", out, flags=re.I)
    out = re.sub(r"~?/\.hermes(?=/|\b)", "the RHODIZ runtime data directory", out, flags=re.I)
    # URLs/brands are maintenance provenance. RHODIZ should not build a self-concept from them.
    out = re.sub(r"https?://[^\s)\]>]*hermes[^\s)\]>]*", "RHODIZ internal documentation", out, flags=re.I)
    out = re.sub(r"\bNous Research\b", "upstream developers", out, flags=re.I)
    out = re.sub(r"\bhermes-agent(?:-[A-Za-z0-9_.-]+)?\b", "internal-runtime", out, flags=re.I)
    out = re.sub(r"\bHermes Agent\b", "RHODIZ IA", out, flags=re.I)
    out = re.sub(r"\bHermes\b", "RHODIZ IA", out, flags=re.I)
    for index, original_name in enumerate(protected):
        out = out.replace(f"__RHODIZ_TECH_SKILL_ID_{index}__", original_name)
    return out


def _sanitize_schema_node(value: Any, *, home: str | Path | None = None) -> Any:
    if isinstance(value, list):
        return [_sanitize_schema_node(v, home=home) for v in value]
    if not isinstance(value, dict):
        return value
    result: dict[Any, Any] = {}
    for key, item in value.items():
        # Only prose fields are rewritten. Names, enums, defaults, identifiers,
        # paths passed as actual values, and dispatch metadata remain byte-identical.
        if key in {"description", "title"} and isinstance(item, str):
            result[key] = sanitize_model_visible_text(item, home=home)
        else:
            result[key] = _sanitize_schema_node(item, home=home)
    return result


def sanitize_tool_definitions(tools: list[dict], *, home: str | Path | None = None) -> list[dict]:
    if not is_rhodiz_product_mode(home):
        return tools
    return [_sanitize_schema_node(tool, home=home) for tool in tools]


def assert_rhodiz_model_context_clean(text: str, *, home: str | Path | None = None) -> None:
    if not is_rhodiz_product_mode(home):
        return
    # Exact technical skill IDs are references, not assertions of RHODIZ identity.
    lower = _TECHNICAL_SKILL_IDENTIFIER.sub("", str(text)).lower()
    leaks = [term for term in ("hermes", "nous research") if term in lower]
    if leaks:
        raise RuntimeError(
            "RHODIZ model-visible context leaked implementation provenance: "
            + ", ".join(leaks)
        )
