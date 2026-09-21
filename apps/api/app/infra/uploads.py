"""Photos an operator uploads for a place.

Public data gives a real photo to ~3 % of places; everything else shows a category example photo.
The only honest way to close that gap is a photo somebody took of the place, so operators can upload
one. Files are checked by their leading bytes (not by the name the browser sent), named by content
hash so the same picture is stored once, and kept outside the repository. In production this module is
the one place to swap for object storage; callers only see `save()` and a public URL.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

MAX_PHOTO_BYTES = 6 * 1024 * 1024
URL_PREFIX = "/uploads"
_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", ".png"),
)


class NotAnImageError(ValueError):
    pass


def default_upload_dir() -> Path:
    """Outside the repository (and outside a synced folder): `%LOCALAPPDATA%/naegajjanday/uploads`."""
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "naegajjanday" / "uploads"


def extension_of(data: bytes) -> str:
    for signature, ext in _SIGNATURES:
        if data.startswith(signature):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    raise NotAnImageError


def save(data: bytes, owner: str, directory: Path) -> str:
    """Stores the picture under `<owner>/<content hash><ext>` and returns that relative path."""
    ext = extension_of(data)
    name = hashlib.sha256(data).hexdigest()[:24] + ext
    folder = directory / owner
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_bytes(data)
    return f"{owner}/{name}"
