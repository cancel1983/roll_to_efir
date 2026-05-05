"""Tkinter desktop interface for Roll to Efir."""

from __future__ import annotations

from pathlib import Path
from queue import Queue, Empty
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .preset import EprPreset, load_epr
from .transcoder import TranscodeJob, build_ffmpeg_command, default_output_path, find_ffmpeg, run_transcode


class RollToEfirApp(tk.Tk):
    """Friendly GUI for selecting a source, EPR preset and MXF destination."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Roll to Efir — подготовка MXF")
        self.geometry("920x680")
        self.minsize(820, 600)

        self.source_var = tk.StringVar()
        self.preset_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Выберите исходный ролик и .epr пресет")
        self.command_var = tk.StringVar(value="Команда ffmpeg появится после выбора пресета")
        self._preset: EprPreset | None = None
        self._queue: Queue[tuple[str, str]] = Queue()
        self._worker: Thread | None = None

        self._build_widgets()
        self.after(150, self._poll_worker)

    def _build_widgets(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(5, weight=1)

        title = ttk.Label(root, text="Конвертация ролика в MXF по пресету Adobe Media Encoder", font=("TkDefaultFont", 14, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 16))

        self._path_row(root, 1, "Исходное видео", self.source_var, self._choose_source)
        self._path_row(root, 2, "Пресет .epr", self.preset_var, self._choose_preset)
        self._path_row(root, 3, "Итоговый MXF", self.output_var, self._choose_output)

        preset_frame = ttk.LabelFrame(root, text="Параметры из .epr", padding=10)
        preset_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(14, 10))
        preset_frame.columnconfigure(0, weight=1)
        self.preset_text = tk.Text(preset_frame, height=10, wrap="word", state="disabled")
        self.preset_text.grid(row=0, column=0, sticky="ew")

        log_frame = ttk.LabelFrame(root, text="Ход конвертации", padding=10)
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scroll.set)

        command_label = ttk.Label(root, textvariable=self.command_var, foreground="#555", wraplength=860)
        command_label.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        bottom = ttk.Frame(root)
        bottom.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        self.start_button = ttk.Button(bottom, text="Создать MXF", command=self._start)
        self.start_button.grid(row=0, column=1, sticky="e")

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=8, pady=4)
        ttk.Button(parent, text="Выбрать…", command=command).grid(row=row, column=2, sticky="e", pady=4)

    def _choose_source(self) -> None:
        path = filedialog.askopenfilename(title="Выберите исходный ролик")
        if path:
            self.source_var.set(path)
            if not self.output_var.get():
                self.output_var.set(str(default_output_path(path)))
            self._refresh_command_preview()

    def _choose_preset(self) -> None:
        path = filedialog.askopenfilename(title="Выберите пресет Adobe Media Encoder", filetypes=[("Adobe presets", "*.epr"), ("Все файлы", "*")])
        if path:
            self.preset_var.set(path)
            try:
                self._preset = load_epr(path)
            except Exception as exc:  # user-facing validation at file boundary
                self._preset = None
                messagebox.showerror("Не удалось прочитать .epr", str(exc))
                return
            self._render_preset()
            self._refresh_command_preview()

    def _choose_output(self) -> None:
        path = filedialog.asksaveasfilename(title="Куда сохранить MXF", defaultextension=".mxf", filetypes=[("MXF", "*.mxf"), ("Все файлы", "*")])
        if path:
            self.output_var.set(path)
            self._refresh_command_preview()

    def _render_preset(self) -> None:
        lines = self._preset.summary_lines() if self._preset else ["Пресет не выбран"]
        self.preset_text.configure(state="normal")
        self.preset_text.delete("1.0", tk.END)
        self.preset_text.insert(tk.END, "\n".join(lines))
        self.preset_text.configure(state="disabled")

    def _refresh_command_preview(self) -> None:
        if not (self.source_var.get() and self.output_var.get() and self._preset):
            return
        command = build_ffmpeg_command(self._job())
        self.command_var.set("ffmpeg: " + " ".join(command))

    def _job(self) -> TranscodeJob:
        assert self._preset is not None
        return TranscodeJob(source=Path(self.source_var.get()), preset=self._preset, output=Path(self.output_var.get()), ffmpeg=find_ffmpeg() or "ffmpeg")

    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        if not self.source_var.get() or not Path(self.source_var.get()).is_file():
            messagebox.showwarning("Не выбран источник", "Выберите существующий исходный видеоролик.")
            return
        if not self._preset:
            messagebox.showwarning("Не выбран пресет", "Выберите .epr файл Adobe Media Encoder.")
            return
        if not find_ffmpeg():
            messagebox.showerror("ffmpeg не найден", "Установите ffmpeg и добавьте его в PATH.")
            return
        Path(self.output_var.get()).parent.mkdir(parents=True, exist_ok=True)
        self._set_running(True)
        self._append_log("Старт конвертации…")
        self._worker = Thread(target=self._run_worker, daemon=True)
        self._worker.start()

    def _run_worker(self) -> None:
        try:
            code = run_transcode(self._job(), lambda line: self._queue.put(("log", line)))
            self._queue.put(("done", str(code)))
        except Exception as exc:  # report background failure to UI thread
            self._queue.put(("error", str(exc)))

    def _poll_worker(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "done":
                    self._set_running(False)
                    if payload == "0":
                        self.status_var.set("Готово: MXF создан")
                        messagebox.showinfo("Готово", "MXF файл успешно создан.")
                    else:
                        self.status_var.set(f"ffmpeg завершился с кодом {payload}")
                elif kind == "error":
                    self._set_running(False)
                    self.status_var.set("Ошибка конвертации")
                    messagebox.showerror("Ошибка", payload)
        except Empty:
            pass
        self.after(150, self._poll_worker)

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.status_var.set("Идет конвертация…" if running else "Готово к запуску")


def main() -> None:
    app = RollToEfirApp()
    app.mainloop()


if __name__ == "__main__":
    main()
