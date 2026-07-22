from __future__ import annotations

import ctypes
import os
import platform
from pathlib import Path

from serial.tools import list_ports

from .models import DeviceOption


STM32_USB_VID = 0x0483
STM32_CDC_PID = 0x5740


def _serial_sort_key(port: object) -> tuple[int, str]:
    description = (getattr(port, "description", "") or "").lower()
    product = (getattr(port, "product", "") or "").lower()
    likely = (
        "nanovna" in description
        or "nanovna" in product
        or (
            getattr(port, "vid", None) == STM32_USB_VID
            and getattr(port, "pid", None) == STM32_CDC_PID
        )
    )
    return (0 if likely else 1, getattr(port, "device", ""))


def discover_serial_devices() -> list[DeviceOption]:
    options: list[DeviceOption] = []
    for port in sorted(list_ports.comports(), key=_serial_sort_key):
        details = port.description or port.product or "USB serial device"
        hardware = ""
        if port.vid is not None and port.pid is not None:
            hardware = f" [{port.vid:04X}:{port.pid:04X}]"
        options.append(
            DeviceOption(
                kind="serial",
                identifier=port.device,
                label=f"USB serial: {port.device} — {details}{hardware}",
            )
        )
    return options


def _windows_volume_label(root: str) -> str:
    volume_name = ctypes.create_unicode_buffer(261)
    filesystem_name = ctypes.create_unicode_buffer(261)
    serial_number = ctypes.c_uint()
    max_component_length = ctypes.c_uint()
    filesystem_flags = ctypes.c_uint()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root),
        volume_name,
        len(volume_name),
        ctypes.byref(serial_number),
        ctypes.byref(max_component_length),
        ctypes.byref(filesystem_flags),
        filesystem_name,
        len(filesystem_name),
    )
    return volume_name.value if ok else "Removable drive"


def discover_storage_devices() -> list[DeviceOption]:
    """Discover mounted removable storage.

    NanoVNA-H/H4 normally uses serial SD-card commands, but a removable-storage
    backend also covers devices, card readers, and firmware variants that mount
    the screenshot card directly.
    """
    if platform.system() != "Windows":
        return []

    DRIVE_REMOVABLE = 2
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    options: list[DeviceOption] = []
    for index in range(26):
        if not (mask & (1 << index)):
            continue
        root = f"{chr(ord('A') + index)}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root)) != DRIVE_REMOVABLE:
            continue
        label = _windows_volume_label(root)
        options.append(
            DeviceOption(
                kind="storage",
                identifier=str(Path(root)),
                label=f"Removable storage: {root} — {label}",
            )
        )
    return options


def discover_devices() -> list[DeviceOption]:
    return discover_serial_devices() + discover_storage_devices()


def likely_device(options: list[DeviceOption]) -> DeviceOption | None:
    if not options:
        return None

    serial_options = [item for item in options if item.kind == "serial"]
    if len(serial_options) == 1:
        return serial_options[0]

    for item in serial_options:
        label = item.label.lower()
        if "nanovna" in label or "0483:5740" in label:
            return item

    if len(options) == 1:
        return options[0]
    return None
