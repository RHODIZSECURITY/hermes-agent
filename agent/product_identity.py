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
    return bool(lower) and any(token in lower for token in _INTERNAL_SKILL_TOKENS)


def filter_internal_skill_prompt(text: str, *, home: str | Path | None = None) -> str:
    """Hide implementation-maintenance skills from RHODIZ's model-visible index."""
    if not text or not is_rhodiz_product_mode(home):
        return text
    kept: list[str] = []
    for line in text.splitlines():
        lower = line.lower()
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
    out = text
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
    lower = str(text).lower()
    leaks = [term for term in ("hermes", "nous research") if term in lower]
    if leaks:
        raise RuntimeError(
            "RHODIZ model-visible context leaked implementation provenance: "
            + ", ".join(leaks)
        )
