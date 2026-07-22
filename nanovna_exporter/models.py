from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DeviceKind = Literal["serial", "storage", "auto"]


@dataclass(frozen=True, slots=True)
class DeviceOption:
    kind: DeviceKind
    identifier: str
    label: str


@dataclass(frozen=True, slots=True)
class ScreenshotFile:
    name: str
    size: int


@dataclass(frozen=True, slots=True)
class ExportSummary:
    exported: int
    skipped: int
    failed: int
    destination: Path
