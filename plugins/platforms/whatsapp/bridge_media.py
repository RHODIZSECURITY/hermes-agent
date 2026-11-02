"""Safe outbound file staging for the first-party RHODIZ WWEBJS bridge.

The bridge can read only its per-profile media caches; copy gateway-approved
outbound files into one of those caches before sending, without copying
symlinks or loading unbounded content into memory.
"""
from __future__ import annotations

import mimetypes
import os
import stat
from pathlib import Path

MAX_MEDIA_BYTES = 32 * 1024 * 1024


def stage_outbound_media(source: str, media_kind: str) -> str:
    """Stage one gateway-selected regular file; reject symlinks/oversized files.

    Authorization of the *user action* remains the caller's responsibility.
    This function ensures the HTTP bridge need not access arbitrary host paths.
    """
    src = Path(source)
    if not src.is_absolute():
        raise ValueError("WhatsApp attachment requires an absolute file path")
    if not hasattr(os, "O_NOFOLLOW"):
        raise ValueError("Secure WhatsApp attachment staging is unavailable on this host")
    kind = media_kind.lower().strip()
    if kind not in {"image", "audio", "voice", "ptt", "video", "document"}:
        raise ValueError("Unsupported WhatsApp media type")
    fd = os.open(str(src), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 1 or before.st_size > MAX_MEDIA_BYTES:
            raise ValueError("WhatsApp attachment is missing, unsafe, or oversized")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read(before.st_size + 1)
        after = os.fstat(fd)
        if len(content) != before.st_size or after.st_size != before.st_size:
            raise ValueError("WhatsApp attachment changed during staging")
    finally:
        os.close(fd)
    # Reuse Hermes' hardened 0700/0600 per-profile cache writers. Neither
    # temporary files nor the user's original source are sent to Node.
    from gateway.platforms.base import cache_media_bytes

    mime, _ = mimetypes.guess_type(src.name)
    kind = "audio" if kind in {"voice", "ptt"} else kind
    cached = cache_media_bytes(content, filename=src.name, mime_type=mime or "", default_kind=kind)
    if cached is None:
        raise ValueError("WhatsApp attachment content failed validation")
    return cached.path
