from __future__ import annotations

import struct
import sys
import types

# The execution environment used for these source-tree tests may not have the
# optional runtime dependency installed. Supply the minimal import surface; the
# real GitHub workflow installs pyserial before running the same tests.
if "serial" not in sys.modules:
    serial_stub = types.ModuleType("serial")
    serial_stub.Serial = object
    serial_stub.SerialException = OSError
    sys.modules["serial"] = serial_stub

from nanovna_exporter.models import ScreenshotFile
from nanovna_exporter.serial_device import NanoVNASerialClient


class FakeSerial:
    def __init__(self, *args, echo: bool = True, **kwargs) -> None:
        self.echo = echo
        self.buffer = bytearray()
        self.closed = False
        self.files = {
            "SCREEN001.BMP": b"BM" + bytes(range(64)),
            "NOTES.TXT": b"not an image",
        }

    @property
    def in_waiting(self) -> int:
        return len(self.buffer)

    def reset_input_buffer(self) -> None:
        self.buffer.clear()

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    def read(self, size: int = 1) -> bytes:
        if not self.buffer:
            return b""
        size = min(size, len(self.buffer))
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def write(self, data: bytes) -> int:
        command = data.rstrip(b"\r\n").decode("ascii")
        prefix = data.rstrip(b"\r\n") + b"\r\n" if self.echo and command else b""
        if not command:
            response = b"\r\nch> "
        elif command == "version":
            response = prefix + b"1.2.52\r\nch> "
        elif command == "help":
            response = prefix + b"help version sd_list sd_read\r\nch> "
        elif command == "sd_list":
            response = prefix
            for name, content in self.files.items():
                response += f"{name} {len(content)}\r\n".encode("ascii")
            response += b"ch> "
        elif command.startswith("sd_read "):
            name = command.split(" ", 1)[1]
            content = self.files[name]
            response = prefix + struct.pack("<I", len(content)) + content + b"\r\nch> "
        else:
            response = prefix + b"?\r\nch> "
        self.buffer.extend(response)
        return len(data)


def fake_factory(echo: bool):
    def factory(*args, **kwargs):
        return FakeSerial(*args, echo=echo, **kwargs)

    return factory


def exercise_client(echo: bool) -> None:
    with NanoVNASerialClient("COM7", serial_factory=fake_factory(echo)) as client:
        assert client.version() == "1.2.52"
        screenshots = client.list_screenshots()
        assert screenshots == [ScreenshotFile("SCREEN001.BMP", 66)]
        assert client.read_file(screenshots[0]) == b"BM" + bytes(range(64))


def test_protocol_with_command_echo() -> None:
    exercise_client(True)


def test_protocol_without_command_echo() -> None:
    exercise_client(False)
