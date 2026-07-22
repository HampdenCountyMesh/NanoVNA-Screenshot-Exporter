from __future__ import annotations

import hashlib
from pathlib import Path


SCREENSHOT_EXTENSIONS = {".bmp", ".tif", ".tiff", ".png", ".jpg", ".jpeg"}


def is_screenshot_name(name: str) -> bool:
    return Path(name).suffix.lower() in SCREENSHOT_EXTENSIONS


def sanitize_filename(name: str) -> str:
    """Return only a safe basename suitable for the destination platform."""
    basename = Path(name.replace("\\", "/")).name.strip()
    if not basename:
        raise ValueError("The device returned an empty filename.")
    invalid = '<>:"/\\|?*'
    for character in invalid:
        basename = basename.replace(character, "_")
    return basename


def files_are_identical(path: Path, data: bytes) -> bool:
    if not path.exists() or path.stat().st_size != len(data):
        return False
    existing_hash = hashlib.sha256(path.read_bytes()).digest()
    incoming_hash = hashlib.sha256(data).digest()
    return existing_hash == incoming_hash


def choose_destination(destination: Path, filename: str, data: bytes) -> tuple[Path, bool]:
    """Choose a non-destructive output path.

    Returns ``(path, already_present)``. Identical files are skipped. Different
    files with the same name receive ``-2``, ``-3``, and so on.
    """
    destination.mkdir(parents=True, exist_ok=True)
    safe_name = sanitize_filename(filename)
    candidate = destination / safe_name
    if not candidate.exists():
        return candidate, False
    if files_are_identical(candidate, data):
        return candidate, True

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 2
    while True:
        candidate = destination / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate, False
        if files_are_identical(candidate, data):
            return candidate, True
        counter += 1
