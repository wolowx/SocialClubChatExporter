import logging
import os
import tkinter as tk
from dataclasses import replace
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .cert_manager import CertError
from .controller import (
    ControllerCallbacks,
    ControllerState,
    ExportResult,
)
from .settings import save_settings

FONT = "Microsoft YaHei UI"
BG = "#f4f6fb"
CARD = "#ffffff"
BORDER = "#e5e7eb"
TEXT = "#111827"
MUTED = "#667085"
ACCENT = "#4f46e5"
ACCENT_HOVER = "#4338ca"


class ExporterApp(tk.Tk):
    def __init__(self, controller, settings_path: Path):
        super().__init__()
        self.controller = controller
        self.settings_path = Path(settings_path)
        self.last_paths = None
        self._timeout_id = None
        self.log_path = self.settings_path.parent / "logs" / "exporter.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(
            f"socialclub_exporter.gui.{id(self)}"
        )
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self._log_handler = RotatingFileHandler(
            self.log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        self._log_handler.setFormatter(
            logging.Formatter("%(asctime)s %(message)s")
        )
        self.logger.addHandler(self._log_handler)

        self.title("Social Club 聊天导出器")
        self.geometry("820x620")
        self.minsize(720, 560)
        self.configure(bg=BG)
        self._configure_style()
        self._build_ui()
        self.controller.callbacks = ControllerCallbacks(
            on_status=self._on_status,
            on_progress=self._on_progress,
            on_log=self._on_log,
            on_done=self._on_done,
            on_error=self._on_error,
        )
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._refresh_certificate_status()
        self._poll()
        self._on_log("工具启动")

    def _configure_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", font=(FONT, 10), padding=(10, 6))
        style.configure(
            "Accent.TButton",
            font=(FONT, 10, "bold"),
            foreground="white",
            background=ACCENT,
            padding=(14, 7),
        )
        style.map(
            "Accent.TButton",
            background=[("active", ACCENT_HOVER), ("disabled", "#c7d2fe")],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#e5e7eb",
            background=ACCENT,
        )

    def _card(self, parent, title=None):
        frame = tk.Frame(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightthickness=1,
            bd=0,
        )
        frame.pack(fill="x", pady=(0, 12))
        inner = tk.Frame(frame, bg=CARD)
        inner.pack(fill="x", padx=14, pady=12)
        if title:
            tk.Label(
                inner,
                text=title,
                bg=CARD,
                fg=TEXT,
                font=(FONT, 11, "bold"),
            ).pack(anchor="w", pady=(0, 8))
        return inner

    def _build_ui(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=18, pady=16)

        header = tk.Frame(main, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(
            header,
            text="Social Club 聊天导出器",
            bg=BG,
            fg=TEXT,
            font=(FONT, 19, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="游戏开着 → 开始监听 → 在面板里打开对话并滚到最早消息 → 停止并导出",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(4, 0))

        status_card = self._card(main, "捕获状态")
        self.status_var = tk.StringVar(value="准备就绪")
        self.count_var = tk.StringVar(value="尚未开始")
        tk.Label(
            status_card,
            textvariable=self.status_var,
            bg=CARD,
            fg=TEXT,
            font=(FONT, 10),
            wraplength=740,
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            status_card,
            textvariable=self.count_var,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w", pady=(4, 8))
        self.progress = ttk.Progressbar(
            status_card, mode="determinate", maximum=100, value=0
        )
        self.progress.pack(fill="x", pady=(0, 10))

        buttons = tk.Frame(status_card, bg=CARD)
        buttons.pack(fill="x")
        self.start_btn = ttk.Button(
            buttons,
            text="开始监听",
            style="Accent.TButton",
            command=self._on_start,
        )
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(
            buttons,
            text="停止并导出",
            command=self._on_stop,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.open_html_btn = ttk.Button(
            buttons,
            text="打开 HTML",
            command=self._open_html,
            state="disabled",
        )
        self.open_html_btn.pack(side="right")
        self.open_folder_btn = ttk.Button(
            buttons,
            text="打开输出文件夹",
            command=self._open_output,
            state="disabled",
        )
        self.open_folder_btn.pack(side="right", padx=(0, 8))
        self.open_log_btn = ttk.Button(
            buttons, text="打开日志文件夹", command=self._open_log
        )
        self.open_log_btn.pack(side="right", padx=(0, 8))

        settings_card = self._card(main, "设置")
        row = tk.Frame(settings_card, bg=CARD)
        row.pack(fill="x", pady=(0, 8))
        tk.Label(
            row, text="目标昵称", bg=CARD, fg=TEXT, font=(FONT, 10), width=10,
            anchor="w",
        ).pack(side="left")
        self.target_var = tk.StringVar(
            value=self.controller.settings.target_nickname or ""
        )
        ttk.Entry(row, textvariable=self.target_var).pack(
            side="left", fill="x", expand=True
        )
        tk.Label(
            settings_card,
            text="留空则导出你在面板里打开的第一个会话；填写后只接受匹配的昵称。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(anchor="w")

        row = tk.Frame(settings_card, bg=CARD)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(
            row, text="输出目录", bg=CARD, fg=TEXT, font=(FONT, 10), width=10,
            anchor="w",
        ).pack(side="left")
        self.output_var = tk.StringVar(
            value=str(self.controller.settings.output_root)
        )
        ttk.Entry(row, textvariable=self.output_var).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(row, text="选择…", command=self._browse_output).pack(
            side="left", padx=(8, 0)
        )

        cert_card = self._card(main, "本地证书")
        cert_row = tk.Frame(cert_card, bg=CARD)
        cert_row.pack(fill="x")
        self.cert_status_var = tk.StringVar(value="检查中…")
        tk.Label(
            cert_row,
            textvariable=self.cert_status_var,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
        ).pack(side="left")
        self.uninstall_cert_btn = ttk.Button(
            cert_row, text="卸载证书", command=self._uninstall_cert
        )
        self.uninstall_cert_btn.pack(side="right")
        self.install_cert_btn = ttk.Button(
            cert_row, text="安装证书", command=self._install_cert
        )
        self.install_cert_btn.pack(side="right", padx=(0, 8))
        tk.Label(
            cert_card,
            text="证书只安装到当前 Windows 用户，用于捕获本机 Social Club 的加密请求；可随时卸载。",
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            wraplength=740,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

    def _set_running(self, running: bool):
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")

    def _refresh_certificate_status(self):
        try:
            status = self.controller.certificate_status()
        except Exception as exc:
            self.cert_status_var.set(f"检查失败：{exc}")
            return
        self.cert_status_var.set("已安装（当前用户）" if status.installed else "未安装")
        self.install_cert_btn.configure(
            state="disabled" if status.installed else "normal"
        )
        self.uninstall_cert_btn.configure(
            state="normal" if status.installed else "disabled"
        )

    def _install_cert(self):
        if not messagebox.askyesno(
            "安装本地证书",
            "为了捕获 Social Club 的加密请求，需要安装一个仅当前用户可见的本地证书。\n\n"
            "证书只用于本机抓包，可随时卸载。是否安装？",
        ):
            return
        try:
            self.controller.install_certificate()
        except CertError as exc:
            messagebox.showerror("证书安装失败", str(exc))
        except Exception as exc:
            messagebox.showerror("证书安装失败", str(exc))
        self._refresh_certificate_status()
        messagebox.showinfo(
            "请重开面板",
            "如果证书刚刚安装，请按 Home 关闭再打开 Social Club 面板，然后开始监听。",
        )

    def _uninstall_cert(self):
        if not messagebox.askyesno("卸载证书", "从当前用户受信任根存储中移除本地证书？"):
            return
        try:
            self.controller.uninstall_certificate()
        except Exception as exc:
            messagebox.showerror("卸载失败", str(exc))
        self._refresh_certificate_status()

    def _on_start(self):
        target = self.target_var.get().strip() or None
        self.controller.settings = replace(
            self.controller.settings, target_nickname=target
        )

        try:
            status = self.controller.certificate_status()
        except Exception as exc:
            messagebox.showerror("证书状态检查失败", str(exc))
            return

        if not status.installed:
            if not messagebox.askyesno(
                "需要本地证书",
                "还没有安装本地证书。安装后需要按 Home 重开一次 Social Club 面板。\n\n是否现在安装？",
            ):
                return
            try:
                self.controller.install_certificate()
            except Exception as exc:
                messagebox.showerror("证书安装失败", str(exc))
                return
            self._refresh_certificate_status()
            messagebox.showinfo(
                "请重开面板",
                "证书已安装。请按 Home 关闭再打开 Social Club 面板，再点“开始监听”。",
            )
            return

        try:
            self.controller.start_capture()
        except CertError as exc:
            messagebox.showerror("无法开始", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("无法开始", str(exc))
            return

        self._set_running(True)
        self._cancel_timeout()
        self._timeout_id = self.after(60000, self._on_capture_timeout)
        self._log("开始监听。请打开对话并往上滚到最早消息。")

    def _on_stop(self):
        self._cancel_timeout()
        if not self.target_var.get().strip() and self.controller.target_nickname:
            if not messagebox.askyesno(
                "确认会话",
                f"准备导出与 {self.controller.target_nickname} 的会话。\n"
                "如果不是这个会话，请点否并重新开始监听。继续？",
            ):
                return
        result = self.controller.stop_and_export()
        self._set_running(False)

        if result.paths is not None:
            self._show_success(result)
            return

        if not result.complete:
            reasons = "\n".join(result.report.reasons) or result.message
            if messagebox.askyesno(
                "捕获不完整",
                reasons + "\n\n仍然导出已捕获的部分吗？",
            ):
                forced = self.controller.stop_and_export(force=True)
                if forced.paths is not None:
                    self._show_success(forced)
                else:
                    messagebox.showerror("导出失败", forced.message)
            else:
                self._on_status("已停止。继续加载后请重新点“开始监听”。")
            return

        messagebox.showwarning("没有导出", result.message)

    def _show_success(self, result: ExportResult):
        self.last_paths = result.paths
        self.open_html_btn.configure(state="normal")
        self.open_folder_btn.configure(state="normal")
        self._on_status(result.message)
        self._log(f"导出完成：{result.paths.directory}")
        messagebox.showinfo(
            "导出完成",
            f"{result.message}\n\n输出目录：\n{result.paths.directory}",
        )

    def _browse_output(self):
        initial = str(self.controller.settings.output_root)
        chosen = filedialog.askdirectory(initialdir=initial)
        if not chosen:
            return
        self.controller.settings = replace(
            self.controller.settings, output_root=Path(chosen)
        )
        self.output_var.set(chosen)

    def _open_output(self):
        directory = (
            self.last_paths.directory
            if self.last_paths is not None
            else self.controller.settings.output_root
        )
        try:
            os.startfile(str(directory))
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _open_html(self):
        if self.last_paths is None:
            return
        try:
            os.startfile(str(self.last_paths.html))
        except Exception as exc:
            messagebox.showerror("打开失败", str(exc))

    def _on_status(self, text: str):
        self.status_var.set(text)
        if (
            self.controller.state == ControllerState.WAITING
            and self._timeout_id is not None
        ):
            self._cancel_timeout()
            self._timeout_id = self.after(60000, self._on_capture_timeout)

    def _on_progress(self, pages, unique, total, has_more):
        self._cancel_timeout()
        if has_more is True:
            suffix = " · 仍有更多消息"
        elif has_more is False:
            suffix = " · 已到最早消息"
        else:
            suffix = " · 是否到底未知"
        if total:
            self.progress.configure(maximum=total, value=unique)
            self.count_var.set(
                f"已捕获 {pages} 页 / {unique} 条 / 共 {total} 条{suffix}"
            )
        else:
            self.progress.configure(maximum=100, value=0)
            self.count_var.set(f"已捕获 {pages} 页 / {unique} 条{suffix}")

    def _cancel_timeout(self):
        if self._timeout_id is not None:
            try:
                self.after_cancel(self._timeout_id)
            except tk.TclError:
                pass
            self._timeout_id = None

    def _on_capture_timeout(self):
        self._timeout_id = None
        if (
            self.controller.state == ControllerState.WAITING
            and not self.controller.pages
        ):
            self.controller.abort_capture(
                "60 秒内没有捕获到请求。请按 Home 关闭再打开 Social Club 面板，"
                "然后重新开始监听。"
            )
            self._set_running(False)

    def _on_log(self, text: str):
        try:
            self.logger.info(text)
        except Exception:
            pass

    def _log(self, text: str) -> None:
        self._on_log(text)

    def _open_log(self):
        try:
            self._on_log("打开日志文件夹")
            os.startfile(str(self.log_path.parent))
        except Exception as exc:
            messagebox.showerror("打开日志文件夹失败", str(exc))

    def _on_done(self, result: ExportResult):
        if result.paths is not None:
            self.last_paths = result.paths
            self.open_html_btn.configure(state="normal")
            self.open_folder_btn.configure(state="normal")

    def _on_error(self, text: str):
        self._set_running(False)
        self._on_status(text)
        self._log(f"错误：{text}")

    def _poll(self):
        if not self.winfo_exists():
            return
        for event in self.controller.poll_capture_events():
            self.controller.on_capture_event(event)
        self.after(100, self._poll)

    def _on_close(self):
        self._cancel_timeout()
        try:
            self.controller.close()
        except Exception:
            pass
        try:
            save_settings(self.settings_path, self.controller.settings)
        except Exception:
            pass
        try:
            self._on_log("工具关闭")
        except Exception:
            pass
        try:
            self.logger.removeHandler(self._log_handler)
            self._log_handler.close()
        except Exception:
            pass
        self.destroy()
