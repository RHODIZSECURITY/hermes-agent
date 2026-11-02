"""RHODIZ WWEBJS bridge integrity check used by Hermes' native adapter.

The deployment installer must have completed npm ci/audit/tests before writing
the marker; this only detects accidental drift, not hostile local admins.
No sessions, credentials, or phone identifiers are read.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

_FILES = (
    "package.json",
    "package-lock.json",
    "bridge.js",
    "control-auth.js",
    "lib.js",
    "scripts/patch-wwebjs.js",
    "scripts/bridge-integrity.js",
    "node_modules/whatsapp-web.js/package.json",
    "node_modules/whatsapp-web.js/src/util/Injected/Utils.js",
    "node_modules/whatsapp-web.js/src/authStrategies/RemoteAuth.js",
    "node_modules/puppeteer/package.json",
    "node_modules/archiver/package.json",
    "node_modules/minimatch/package.json",
    "node_modules/express/package.json",
)
_MARKER = "node_modules/.rhodiz-audit-verified.json"
_PACKAGE_NAME = "rhodiz-hermes-whatsapp-web-bridge"


def is_rhodiz_wwebjs_bridge(directory: Path) -> bool:
    try:
        data = json.loads((Path(directory) / "package.json").read_text(encoding="utf-8"))
        return data.get("name") == _PACKAGE_NAME
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def verified_bridge_integrity(directory: Path) -> bool:
    """Fail closed when any installed-file fingerprint differs from the audited build."""
    try:
        root = Path(directory).resolve(strict=True)
        marker = root / _MARKER
        # A marker in a symlinked dependency tree must not be trusted.
        if marker.is_symlink():
            return False
        data = json.loads(marker.read_text(encoding="utf-8"))
        entries = data.get("files")
        if data.get("schemaVersion") != 1 or not isinstance(entries, dict):
            return False
        if set(entries) != set(_FILES):
            return False
        for name in _FILES:
            file = root / name
            if file.is_symlink() or not file.is_file():
                return False
            if not file.resolve(strict=True).is_relative_to(root):
                return False
            actual = hashlib.sha256(file.read_bytes()).hexdigest()
            if entries[name] != actual:
                return False
        return True
    except (OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError):
        return False
