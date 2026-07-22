# NanoVNA Screenshot Exporter

A deliberately small desktop utility that exports screenshots already saved on a supported NanoVNA. The normal workflow is:

1. Connect the NanoVNA by USB and turn it on.
2. Open the app.
3. Choose an export folder.
4. Choose the detected device, if more than one appears.
5. Select **Export now**.

The app never deletes screenshots from the NanoVNA. Existing identical files are skipped; different files with duplicate names are saved with `-2`, `-3`, and so on.

## Current compatibility

### Supported over USB serial

Firmware must provide all of the following shell commands:

- `help`
- `sd_list`
- `sd_read`

These commands are present in current NanoVNA-H/H4 firmware trees derived from the DiSlord/Hugen code when SD-card command support is enabled. This is the intended path for the AURSINC NanoVNA-H4 V4.4 and similar H/H4 units.

Saved image formats currently recognized: BMP, TIFF, PNG, and JPEG.

### Supported as mounted storage

On Windows, the app also lists removable drives. This allows export from a NanoVNA variant that exposes its screenshots as storage, or from the NanoVNA's SD card placed in a card reader.

### Not guaranteed

- NanoVNA V2/S-A-A-2 devices use a substantially different USB protocol and generally do not provide the H/H4 `sd_list`/`sd_read` shell interface.
- Some NanoVNA-F, clone, and older firmware builds can capture the *current* display over USB but cannot retrieve screenshots already stored on the SD card.
- Firmware built without SD-card shell commands cannot be fixed by this desktop program alone.

The app checks capabilities before exporting and reports a clear error rather than pretending that a current-screen capture is a saved screenshot.

## Run from source on Windows

Install Python 3.10 or newer, then double-click:

```text
run_windows.bat
```

Or run manually:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

## Build a standalone Windows executable

Double-click:

```text
build_windows.bat
```

The executable will be written to:

```text
dist\NanoVNA-Screenshot-Exporter.exe
```

The included GitHub Actions workflow can also build the executable. Run **Build Windows executable** from the repository's Actions tab or push a tag such as `v0.1.0`, then download the build artifact.

## Linux and macOS

Serial export is cross-platform. Tkinter must be available in the Python installation. Mounted-removable-drive discovery is currently Windows-specific; users on Linux or macOS can still use the serial method.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

Linux users may need permission to access the serial device, commonly through membership in the `dialout` group.

## Development

```bash
pip install -r requirements-dev.txt
pytest
ruff check .
```

## Safety and data handling

- Export is read-only on the NanoVNA.
- Files are written through a temporary `.part` file and renamed after the complete download.
- The app does not collect telemetry or use the network.
- A failed file does not stop the remaining screenshots from being attempted.

## Protocol notes

For supported H/H4 firmware, `sd_list` returns filename-and-size lines. `sd_read <filename>` returns a four-byte little-endian file size followed by the exact file bytes. The exporter uses the size reported by `sd_list` to validate each transfer and tolerate firmware builds that do or do not echo commands.

## Protocol references

See [ATTRIBUTIONS.md](ATTRIBUTIONS.md). This is an independent utility and is not an official NanoVNA application.

## License

MIT. See [LICENSE](LICENSE).
