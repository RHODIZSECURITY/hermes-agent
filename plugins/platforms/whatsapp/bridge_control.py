"""Pure RHODIZ WWEBJS HTTP control-plane authentication contract.

Credentials are obtained by the adapter from its own Hermes profile scope,
not from the process-global environment, and never logged.
"""
from __future__ import annotations

import re

TOKEN_ENV = "RHODIZ_WHATSAPP_BRIDGE_TOKEN"
_TOKEN_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


def control_headers(is_rhodiz_wwebjs: bool, scoped_token: str) -> dict[str, str]:
    """Return a Bearer credential for the first-party bridge or fail closed.

    Upstream Baileys bridges retain their existing contract pending a separate
    reviewed migration.
    """
    if not is_rhodiz_wwebjs:
        return {}
    if not isinstance(scoped_token, str) or _TOKEN_RE.fullmatch(scoped_token) is None:
        raise ValueError("RHODIZ WhatsApp bridge control token is missing or invalid")
    return {"Authorization": f"Bearer {scoped_token}"}
