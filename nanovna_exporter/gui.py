from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .discovery import discover_devices, likely_device
from .exporter import export_from_serial, export_from_storage
from .models import DeviceOption, ExportSummary


APP_TITLE = "NanoVNA Screenshot Exporter"


class ExporterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("610x390")
        self.minsize(540, 350)

        self.devices: list[DeviceOption] = []
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.destination_var = tk.StringVar(value=str(Path.home() / "Pictures" / "NanoVNA"))
        self.device_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Connect the NanoVNA, then choose Export now.")

        self._build_ui()
        self.refresh_devices()
        self.after(100, self._process_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        frame = ttk.Frame(self, padding=18)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(5, weight=1)

        ttk.Label(frame, text=APP_TITLE, font=("Segoe UI", 17, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 16)
        )

        ttk.Label(frame, text="Device").grid(row=1, column=0, sticky="w")
        self.device_box = ttk.Combobox(
            frame,
            textvariable=self.device_var,
            state="readonly",
            width=58,
        )
        self.device_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(4, 13))
        self.refresh_button = ttk.Button(frame, text="Refresh", command=self.refresh_devices)
        self.refresh_button.grid(row=2, column=2, sticky="e", padx=(8, 0), pady=(4, 13))

        ttk.Label(frame, text="Export folder").grid(row=3, column=0, sticky="w")
        self.destination_entry = ttk.Entry(frame, textvariable=self.destination_var)
        self.destination_entry.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 13))
        ttk.Button(frame, text="Choose…", command=self.choose_destination).grid(
            row=4, column=2, sticky="e", padx=(8, 0), pady=(4, 13)
        )

        self.log = tk.Text(frame, height=9, wrap="word", state="disabled")
        self.log.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(0, 12))

        ttk.Label(frame, textvariable=self.status_var).grid(
            row=6, column=0, columnspan=2, sticky="w"
        )
        self.export_button = ttk.Button(frame, text="Export now", command=self.export_now)
        self.export_button.grid(row=6, column=2, sticky="e")

    def _append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.status_var.set(message)

    def choose_destination(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose export folder",
            initialdir=self.destination_var.get() or str(Path.home()),
        )
        if selected:
            self.destination_var.set(selected)

    def refresh_devices(self) -> None:
        self.devices = discover_devices()
        labels = [item.label for item in self.devices]
        self.device_box["values"] = labels
        preferred = likely_device(self.devices)
        if preferred is not None:
            self.device_var.set(preferred.label)
        elif labels:
            self.device_var.set(labels[0])
        else:
            self.device_var.set("No devices found")
        self._append_log(f"Detected {len(self.devices)} possible device(s).")

    def _selected_device(self) -> DeviceOption | None:
        selected_label = self.device_var.get()
        return next((item for item in self.devices if item.label == selected_label), None)

    def export_now(self) -> None:
        device = self._selected_device()
        if device is None:
            messagebox.showerror(APP_TITLE, "No NanoVNA or removable storage device was found.")
            return

        destination_text = self.destination_var.get().strip()
        if not destination_text:
            messagebox.showerror(APP_TITLE, "Choose an export folder first.")
            return
        destination = Path(destination_text).expanduser()
        try:
            destination.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(APP_TITLE, f"Could not create the export folder:\n{exc}")
            return

        self.export_button.configure(state="disabled")
        self.refresh_button.configure(state="disabled")
        self._append_log("Starting export…")
        worker = threading.Thread(
            target=self._export_worker,
            args=(device, destination),
            daemon=True,
        )
        worker.start()

    def _export_worker(self, device: DeviceOption, destination: Path) -> None:
        def progress(message: str) -> None:
            self.events.put(("progress", message))

        try:
            if device.kind == "serial":
                summary = export_from_serial(device.identifier, destination, progress)
            elif device.kind == "storage":
                summary = export_from_storage(Path(device.identifier), destination, progress)
            else:
                raise RuntimeError(f"Unsupported device type: {device.kind}")
            self.events.put(("done", summary))
        except Exception as exc:
            self.events.put(("error", exc))

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    self._append_log(str(payload))
                elif event == "done":
                    self._finish_export(payload)  # type: ignore[arg-type]
                elif event == "error":
                    self._export_failed(payload)  # type: ignore[arg-type]
        except queue.Empty:
            pass
        self.after(100, self._process_events)

    def _finish_export(self, summary: ExportSummary) -> None:
        self.export_button.configure(state="normal")
        self.refresh_button.configure(state="normal")
        message = (
            f"Finished: {summary.exported} exported, {summary.skipped} already present, "
            f"{summary.failed} failed."
        )
        self._append_log(message)
        if summary.exported or summary.skipped:
            messagebox.showinfo(
                APP_TITLE,
                f"{message}\n\nFolder:\n{summary.destination}",
            )
        elif not summary.failed:
            messagebox.showinfo(APP_TITLE, "No saved screenshots were found.")

    def _export_failed(self, error: Exception) -> None:
        self.export_button.configure(state="normal")
        self.refresh_button.configure(state="normal")
        self._append_log(f"Export failed: {error}")
        messagebox.showerror(APP_TITLE, str(error))


def main() -> None:
    app = ExporterApp()
    app.mainloop()
