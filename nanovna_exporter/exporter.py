from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from .files import SCREENSHOT_EXTENSIONS, choose_destination, is_screenshot_name
from .models import ExportSummary, ScreenshotFile
from .serial_device import NanoVNASerialClient


ProgressCallback = Callable[[str], None]


def _write_export(destination: Path, filename: str, data: bytes) -> bool:
    output, already_present = choose_destination(destination, filename, data)
    if already_present:
        return False
    temporary = output.with_suffix(output.suffix + ".part")
    temporary.write_bytes(data)
    os.replace(temporary, output)
    return True


def export_from_serial(
    port: str,
    destination: Path,
    progress: ProgressCallback,
) -> ExportSummary:
    exported = skipped = failed = 0
    with NanoVNASerialClient(port) as device:
        version = device.version() or "unknown firmware"
        progress(f"Connected to {port}: {version}")
        screenshots = device.list_screenshots()
        if not screenshots:
            progress("No supported screenshot files were found on the NanoVNA SD card.")
            return ExportSummary(0, 0, 0, destination)

        progress(f"Found {len(screenshots)} screenshot(s).")
        for index, screenshot in enumerate(screenshots, start=1):
            progress(
                f"Downloading {index}/{len(screenshots)}: {screenshot.name} "
                f"({screenshot.size:,} bytes)"
            )
            try:
                data = device.read_file(screenshot)
                if _write_export(destination, screenshot.name, data):
                    exported += 1
                else:
                    skipped += 1
                    progress(f"Already exported: {screenshot.name}")
            except Exception as exc:  # continue exporting the remaining files
                failed += 1
                progress(f"Failed: {screenshot.name} — {exc}")

    return ExportSummary(exported, skipped, failed, destination)


def _storage_screenshots(root: Path) -> list[Path]:
    files: list[Path] = []
    # Search the root and one directory level below it. This avoids an expensive
    # recursive crawl of an unrelated removable drive while covering common
    # DCIM/screenshots layouts.
    candidates = list(root.iterdir())
    for candidate in candidates:
        if candidate.is_file() and is_screenshot_name(candidate.name):
            files.append(candidate)
        elif candidate.is_dir():
            try:
                for child in candidate.iterdir():
                    if child.is_file() and child.suffix.lower() in SCREENSHOT_EXTENSIONS:
                        files.append(child)
            except OSError:
                continue
    return sorted(files, key=lambda path: path.name.casefold())


def export_from_storage(
    root: Path,
    destination: Path,
    progress: ProgressCallback,
) -> ExportSummary:
    exported = skipped = failed = 0
    screenshots = _storage_screenshots(root)
    if not screenshots:
        progress("No supported screenshot files were found on that storage device.")
        return ExportSummary(0, 0, 0, destination)

    progress(f"Found {len(screenshots)} screenshot(s).")
    for index, source in enumerate(screenshots, start=1):
        progress(f"Copying {index}/{len(screenshots)}: {source.name}")
        try:
            data = source.read_bytes()
            if _write_export(destination, source.name, data):
                exported += 1
            else:
                skipped += 1
                progress(f"Already exported: {source.name}")
        except Exception as exc:
            failed += 1
            progress(f"Failed: {source.name} — {exc}")

    return ExportSummary(exported, skipped, failed, destination)
