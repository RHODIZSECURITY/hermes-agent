"""Regression contracts for private WhatsApp adapter diagnostics.

Static inspection avoids connecting WhatsApp, loading secrets, or changing
Hermes production state. Runtime media authorization is tested separately.
"""
from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "plugins" / "platforms" / "whatsapp" / "adapter.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))
PRIVATE_NAMES = frozenset({"url", "path", "doc_path", "chat_id", "raw_reply_id", "e", "exc", "data", "body"})


def _method(name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    found = [
        node for node in ast.walk(TREE)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    assert len(found) == 1, f"Missing or ambiguous WhatsApp adapter method {name}"
    return found[0]


def _diagnostics(method: ast.AST) -> list[ast.Call]:
    calls = []
    for node in ast.walk(method):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id == "print":
            calls.append(node)
        elif (
            isinstance(callee, ast.Attribute)
            and isinstance(callee.value, ast.Name)
            and callee.value.id == "logger"
            and callee.attr in {"debug", "info", "warning", "error", "exception", "critical"}
        ):
            calls.append(node)
    return calls


def test_media_pipeline_logs_no_private_paths_or_raw_errors() -> None:
    total = 0
    for method_name in (
        "_collect_bridge_media",
        "_inject_document_text",
        "_quoted_media",
        "_build_message_event",
    ):
        calls = _diagnostics(_method(method_name))
        assert calls, f"Lost operational diagnostics in {method_name}"
        total += len(calls)
        for call in calls:
            for arg in call.args:
                interpolated = {
                    node.value.id
                    for node in ast.walk(arg)
                    if isinstance(node, ast.FormattedValue) and isinstance(node.value, ast.Name)
                }
                leaked = interpolated & PRIVATE_NAMES
                assert not leaked, f"{method_name} logs private values: {sorted(leaked)}"
    assert total >= 10


def test_error_and_chat_diagnostics_never_include_raw_values() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "Could not get WhatsApp chat info for %s" not in source
    assert "Poll error: {e}" not in source
    assert "read receipt failed: %s" not in source
    assert "Error building event: {e}" not in source


def test_media_path_guards_and_text_injection_still_present() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "if _is_allowed_bridge_path(url):" in source
    assert "os.path.isabs(path) and _is_allowed_bridge_path(path)" in source
    assert "body = f\"{injection}\\n\\n{body}\" if body else injection" in source
    assert "print(f\"[{self.name}] Rejected bridge {label} path outside cache dir\"" in source
