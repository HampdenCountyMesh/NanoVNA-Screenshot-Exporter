from __future__ import annotations

import re
import struct
import time
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Callable

import serial

from .files import is_screenshot_name
from .models import ScreenshotFile


PROMPT = b"ch> "
LISTING_LINE = re.compile(r"^(?P<name>.+?)\s+(?P<size>\d+)$")
MAX_REASONABLE_FILE_SIZE = 64 * 1024 * 1024


class NanoVNAError(RuntimeError):
    pass


class NanoVNAUnsupportedError(NanoVNAError):
    pass


class NanoVNASerialClient(AbstractContextManager["NanoVNASerialClient"]):
    def __init__(
        self,
        port: str,
        *,
        baudrate: int = 115200,
        timeout: float = 0.2,
        serial_factory: Callable[..., serial.Serial] = serial.Serial,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._serial_factory = serial_factory
        self.serial: serial.Serial | None = None

    def __enter__(self) -> "NanoVNASerialClient":
        try:
            self.serial = self._serial_factory(
                self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                write_timeout=2,
            )
        except serial.SerialException as exc:
            raise NanoVNAError(f"Could not open {self.port}: {exc}") from exc

        self.serial.reset_input_buffer()
        self.serial.reset_output_buffer()
        self._synchronize()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        if self.serial is not None:
            self.serial.close()
            self.serial = None

    def _require_serial(self) -> serial.Serial:
        if self.serial is None:
            raise NanoVNAError("The NanoVNA serial connection is not open.")
        return self.serial

    def _synchronize(self) -> None:
        connection = self._require_serial()
        connection.write(b"\r")
        try:
            self._read_until_prompt(timeout=3.0)
        except NanoVNAError:
            # A second carriage return helps devices that were left in a partial
            # command or had just finished enumerating on USB.
            connection.reset_input_buffer()
            connection.write(b"\r")
            self._read_until_prompt(timeout=3.0)

    def _read_until_prompt(self, *, timeout: float = 4.0) -> bytes:
        connection = self._require_serial()
        deadline = time.monotonic() + timeout
        buffer = bytearray()
        while time.monotonic() < deadline:
            chunk = connection.read(connection.in_waiting or 1)
            if chunk:
                buffer.extend(chunk)
                if PROMPT in buffer:
                    return bytes(buffer[: buffer.index(PROMPT)])
            else:
                time.sleep(0.01)
        raise NanoVNAError("Timed out waiting for the NanoVNA command prompt.")

    def _text_command(self, command: str, *, timeout: float = 5.0) -> str:
        connection = self._require_serial()
        connection.reset_input_buffer()
        connection.write(command.encode("ascii") + b"\r")
        raw = self._read_until_prompt(timeout=timeout)
        text = raw.replace(b"\r", b"").decode("utf-8", errors="replace")
        lines = text.split("\n")
        command_lower = command.lower().strip()
        cleaned: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.lower() == command_lower:
                continue
            cleaned.append(stripped)
        return "\n".join(cleaned)

    def version(self) -> str:
        return self._text_command("version").strip()

    def supports_sd_export(self) -> bool:
        help_text = self._text_command("help", timeout=7.0).lower()
        return "sd_list" in help_text and "sd_read" in help_text

    def list_screenshots(self) -> list[ScreenshotFile]:
        if not self.supports_sd_export():
            raise NanoVNAUnsupportedError(
                "This firmware does not advertise the sd_list and sd_read commands "
                "needed to export screenshots already saved on the device."
            )

        response = self._text_command("sd_list", timeout=8.0)
        if "err: no card" in response.lower():
            raise NanoVNAError("The NanoVNA did not detect an SD card.")

        results: list[ScreenshotFile] = []
        seen: set[str] = set()
        for line in response.splitlines():
            match = LISTING_LINE.match(line.strip())
            if not match:
                continue
            name = match.group("name").strip()
            size = int(match.group("size"))
            key = name.casefold()
            if key in seen or not is_screenshot_name(name):
                continue
            if not 0 <= size <= MAX_REASONABLE_FILE_SIZE:
                continue
            seen.add(key)
            results.append(ScreenshotFile(name=name, size=size))
        return sorted(results, key=lambda item: item.name.casefold())

    def read_file(self, remote_file: ScreenshotFile) -> bytes:
        if not remote_file.name or any(char in remote_file.name for char in "\r\n"):
            raise NanoVNAError("The NanoVNA returned an invalid filename.")
        if " " in remote_file.name:
            raise NanoVNAError(
                f"Cannot download {remote_file.name!r}: this firmware's shell cannot "
                "address filenames containing spaces."
            )

        connection = self._require_serial()
        command = f"sd_read {remote_file.name}".encode("ascii", errors="strict") + b"\r"
        connection.reset_input_buffer()
        connection.write(command)

        expected_header = struct.pack("<I", remote_file.size)
        deadline = time.monotonic() + 5.0
        prefix = bytearray()
        header_index = -1

        # Depending on the USB shell build, the command may be echoed before the
        # four-byte little-endian file size. Scan a small prefix for that exact
        # expected size so both echoing and non-echoing firmware are handled.
        while time.monotonic() < deadline and len(prefix) < 512:
            chunk = connection.read(connection.in_waiting or 1)
            if chunk:
                prefix.extend(chunk)
                header_index = prefix.find(expected_header)
                if header_index >= 0:
                    break
            else:
                time.sleep(0.01)

        if header_index < 0:
            text = prefix.decode("utf-8", errors="ignore").strip()
            if "err: no file" in text.lower():
                raise NanoVNAError(f"The device could not open {remote_file.name}.")
            raise NanoVNAError(
                f"Did not receive a valid size header for {remote_file.name}."
            )

        post_header = bytes(prefix[header_index + 4 :])
        data = bytearray(post_header[: remote_file.size])
        trailing = post_header[remote_file.size :]

        deadline = time.monotonic() + max(10.0, remote_file.size / 20_000.0)
        while len(data) < remote_file.size and time.monotonic() < deadline:
            chunk = connection.read(min(4096, remote_file.size - len(data)))
            if chunk:
                data.extend(chunk)
            else:
                time.sleep(0.01)

        if len(data) != remote_file.size:
            raise NanoVNAError(
                f"Download of {remote_file.name} stopped at {len(data):,} of "
                f"{remote_file.size:,} bytes."
            )

        # Leave the port clean for the next command. A fast USB connection can
        # put the file and prompt into the same read used to find the size header.
        if PROMPT not in trailing:
            try:
                self._read_until_prompt(timeout=3.0)
            except NanoVNAError:
                connection.reset_input_buffer()

        return bytes(data)
