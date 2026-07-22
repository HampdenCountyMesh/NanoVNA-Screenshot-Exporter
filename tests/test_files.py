from pathlib import Path

from nanovna_exporter.files import choose_destination, is_screenshot_name, sanitize_filename


def test_screenshot_extensions_are_case_insensitive() -> None:
    assert is_screenshot_name("SCREEN001.BMP")
    assert is_screenshot_name("trace.tiff")
    assert not is_screenshot_name("measurement.s2p")


def test_sanitize_filename_removes_paths_and_invalid_characters() -> None:
    assert sanitize_filename("folder/SCREEN:01.BMP") == "SCREEN_01.BMP"


def test_identical_file_is_skipped(tmp_path: Path) -> None:
    original = tmp_path / "screen.bmp"
    original.write_bytes(b"same")
    destination, already_present = choose_destination(tmp_path, "screen.bmp", b"same")
    assert destination == original
    assert already_present


def test_collision_gets_numbered_name(tmp_path: Path) -> None:
    (tmp_path / "screen.bmp").write_bytes(b"old")
    destination, already_present = choose_destination(tmp_path, "screen.bmp", b"new")
    assert destination.name == "screen-2.bmp"
    assert not already_present
