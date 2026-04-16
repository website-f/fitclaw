from __future__ import annotations

import os
import platform
from queue import Empty, Queue
import subprocess
import threading
from tkinter import messagebox

import customtkinter as ctk

from ai_ops_agent.constants import APP_NAME
from ai_ops_agent.config import AgentConfig
from ai_ops_agent.installer import (
    install_agent,
    remove_agent,
    save_config,
    test_connection,
    uninstall_autostart,
)
from ai_ops_agent.paths import config_path, log_path

# ── Palette (matches FitClaw PWA dark theme) ──
_BG = "#0b1120"
_CARD = "#111b2d"
_CARD_EDGE = "#1e3050"
_FIELD = "#17243a"
_FIELD_EDGE = "#2a426a"
_TXT = "#f5f8ff"
_TXT2 = "#c2d0e7"
_TXT3 = "#8096b8"
_ACCENT = "#38bdf8"
_ACCENT_H = "#60ccff"
_GREEN = "#34d399"
_RED = "#f87171"
_SEC = "#1c2941"
_SEC_H = "#274066"


class InstallerWindow:
    """Modern setup window built with customtkinter."""

    def __init__(self) -> None:
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.root = ctk.CTk()
        self.root.title(f"{APP_NAME} Setup")
        self.root.geometry("820x720")
        self.root.minsize(440, 480)
        self.root.configure(fg_color=_BG)

        # ── State from saved config ──
        cfg = AgentConfig.load()
        self.server_var = ctk.StringVar(value=cfg.api_base_url)
        self.agent_name_var = ctk.StringVar(value=cfg.agent_name)
        self.username_var = ctk.StringVar(value=cfg.username)
        self.shared_key_var = ctk.StringVar(value=cfg.shared_key)
        self.capabilities_var = ctk.StringVar(value=",".join(cfg.capabilities))
        self.poll_var = ctk.StringVar(value=str(cfg.poll_interval_seconds))
        self.heartbeat_var = ctk.StringVar(value=str(cfg.heartbeat_interval_seconds))
        self.timeout_var = ctk.StringVar(value=str(cfg.task_timeout_seconds))
        self.allow_unassigned_var = ctk.BooleanVar(value=cfg.allow_unassigned)
        self.auto_start_var = ctk.BooleanVar(value=cfg.auto_start)
        self.show_key_var = ctk.BooleanVar(value=False)
        self.status_title_var = ctk.StringVar(value="Ready")
        self.status_detail_var = ctk.StringVar(
            value="Check server details, then test the connection before installing."
        )

        self.buttons: list[ctk.CTkButton] = []
        self.fields: list = []
        self.worker_events: Queue[tuple[str, tuple[object, ...]]] = Queue()
        self.progress_bar: ctk.CTkProgressBar | None = None
        self.status_title_lbl: ctk.CTkLabel | None = None
        self.status_detail_lbl: ctk.CTkLabel | None = None
        self.key_entry: ctk.CTkEntry | None = None

        self._build()
        self.root.after(100, self._drain_worker_events)

    # ────────────────────────────── layout helpers ──────────────────────────────

    def _card(self, parent, title: str) -> ctk.CTkFrame:
        outer = ctk.CTkFrame(
            parent, fg_color=_CARD, corner_radius=14,
            border_width=1, border_color=_CARD_EDGE,
        )
        outer.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(outer, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=(14, 16))
        ctk.CTkLabel(
            inner, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=_TXT, anchor="w",
        ).pack(fill="x", pady=(0, 8))
        return inner

    def _entry(self, parent, label: str, var, show: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent, text=label,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_TXT3, anchor="w",
        ).pack(fill="x", pady=(4, 1))
        e = ctk.CTkEntry(
            parent, textvariable=var, show=show,
            fg_color=_FIELD, border_color=_FIELD_EDGE,
            text_color=_TXT, placeholder_text_color=_TXT3,
            height=36, corner_radius=10, font=ctk.CTkFont(size=13),
        )
        e.pack(fill="x", pady=(0, 4))
        self.fields.append(e)
        return e

    def _entry_in(self, parent, label: str, var, row: int, col: int, show: str = "") -> ctk.CTkEntry:
        frm = ctk.CTkFrame(parent, fg_color="transparent")
        frm.grid(row=row, column=col, sticky="ew", padx=3)
        ctk.CTkLabel(
            frm, text=label,
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=_TXT3, anchor="w",
        ).pack(fill="x", pady=(4, 1))
        e = ctk.CTkEntry(
            frm, textvariable=var, show=show,
            fg_color=_FIELD, border_color=_FIELD_EDGE,
            text_color=_TXT, placeholder_text_color=_TXT3,
            height=36, corner_radius=10, font=ctk.CTkFont(size=13),
        )
        e.pack(fill="x", pady=(0, 4))
        self.fields.append(e)
        return e

    # ────────────────────────────── build layout ───────────────────────────────

    def _build(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self.root, fg_color=_BG,
            scrollbar_button_color=_FIELD_EDGE,
            scrollbar_button_hover_color=_ACCENT,
        )
        scroll.pack(fill="both", expand=True)

        pad = ctk.CTkFrame(scroll, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=22, pady=(18, 22))

        # ── Header ──
        ctk.CTkLabel(
            pad, text="FitClaw Agent",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=_ACCENT, anchor="w",
        ).pack(fill="x")
        ctk.CTkLabel(
            pad, text="Install Desktop Agent",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=_TXT, anchor="w",
        ).pack(fill="x", pady=(2, 0))
        ctk.CTkLabel(
            pad,
            text="Validate the server, configure runtime settings, and launch the background agent.",
            font=ctk.CTkFont(size=12), text_color=_TXT2,
            anchor="w", wraplength=720,
        ).pack(fill="x", pady=(4, 16))

        # ── Connection & Identity ──
        conn = self._card(pad, "Connection & Identity")
        self._entry(conn, "Server URL", self.server_var)
        ctk.CTkLabel(
            conn,
            text="Use the server root, for example https://fitclaw.example.com, not /app or another page.",
            font=ctk.CTkFont(size=10),
            text_color=_TXT3,
            anchor="w",
            wraplength=700,
        ).pack(fill="x", pady=(0, 6))

        row1 = ctk.CTkFrame(conn, fg_color="transparent")
        row1.pack(fill="x")
        row1.columnconfigure(0, weight=1)
        row1.columnconfigure(1, weight=1)
        self._entry_in(row1, "Agent Name", self.agent_name_var, 0, 0)
        self._entry_in(row1, "Auth Username", self.username_var, 0, 1)

        row2 = ctk.CTkFrame(conn, fg_color="transparent")
        row2.pack(fill="x")
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)
        self.key_entry = self._entry_in(row2, "Shared Key", self.shared_key_var, 0, 0, show="\u25cf")
        self._entry_in(row2, "Capabilities", self.capabilities_var, 0, 1)

        show_cb = ctk.CTkCheckBox(
            conn, text="Show shared key",
            variable=self.show_key_var, command=self._toggle_key,
            font=ctk.CTkFont(size=11), text_color=_TXT3,
            fg_color=_ACCENT, hover_color=_ACCENT_H,
            border_color=_FIELD_EDGE, height=22,
            corner_radius=4, checkbox_width=18, checkbox_height=18,
        )
        show_cb.pack(anchor="w", pady=(2, 4))
        self.fields.append(show_cb)

        ctk.CTkLabel(
            conn,
            text="Comma-separated capabilities (shell,screenshot,storage). Agent auto-detects extras at runtime.",
            font=ctk.CTkFont(size=10), text_color=_TXT3,
            anchor="w", wraplength=700,
        ).pack(fill="x")

        # ── Settings & Behavior ──
        settings = self._card(pad, "Settings & Behavior")

        num_row = ctk.CTkFrame(settings, fg_color="transparent")
        num_row.pack(fill="x")
        num_row.columnconfigure(0, weight=1)
        num_row.columnconfigure(1, weight=1)
        num_row.columnconfigure(2, weight=1)
        self._entry_in(num_row, "Poll (s)", self.poll_var, 0, 0)
        self._entry_in(num_row, "Heartbeat (s)", self.heartbeat_var, 0, 1)
        self._entry_in(num_row, "Timeout (s)", self.timeout_var, 0, 2)

        allow_cb = ctk.CTkCheckBox(
            settings, text="Allow unassigned tasks",
            variable=self.allow_unassigned_var,
            font=ctk.CTkFont(size=12), text_color=_TXT,
            fg_color=_ACCENT, hover_color=_ACCENT_H,
            border_color=_FIELD_EDGE, corner_radius=4,
        )
        allow_cb.pack(anchor="w", pady=(10, 6))
        auto_cb = ctk.CTkCheckBox(
            settings, text="Start automatically on login",
            variable=self.auto_start_var,
            font=ctk.CTkFont(size=12), text_color=_TXT,
            fg_color=_ACCENT, hover_color=_ACCENT_H,
            border_color=_FIELD_EDGE, corner_radius=4,
        )
        auto_cb.pack(anchor="w", pady=(0, 2))
        self.fields.extend([allow_cb, auto_cb])

        # ── Status ──
        status = self._card(pad, "Status")
        self.status_title_lbl = ctk.CTkLabel(
            status, textvariable=self.status_title_var,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=_GREEN, anchor="w",
        )
        self.status_title_lbl.pack(fill="x")
        self.status_detail_lbl = ctk.CTkLabel(
            status, textvariable=self.status_detail_var,
            font=ctk.CTkFont(size=11), text_color=_TXT2,
            anchor="w", wraplength=700, justify="left",
        )
        self.status_detail_lbl.pack(fill="x", pady=(4, 8))
        self.progress_bar = ctk.CTkProgressBar(
            status, mode="indeterminate",
            progress_color=_ACCENT, fg_color=_FIELD,
            height=4, corner_radius=2,
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        # ── Actions ──
        actions = self._card(pad, "Actions")
        bg = ctk.CTkFrame(actions, fg_color="transparent")
        bg.pack(fill="x")
        for c in range(3):
            bg.columnconfigure(c, weight=1)

        specs = [
            ("Test Connection", self.on_test_connection, _SEC, _SEC_H, _TXT),
            ("Save Config", self.on_save_only, _SEC, _SEC_H, _TXT),
            ("Install & Start", self.on_install, _ACCENT, _ACCENT_H, "#082028"),
            ("Remove Agent", self.on_remove_agent, "#7f1d1d", "#991b1b", "#fca5a5"),
            ("Remove Auto-Start", self.on_remove_autostart, _SEC, _SEC_H, _TXT),
            ("Exit", self.root.destroy, _SEC, _SEC_H, _TXT3),
        ]
        for idx, (text, cmd, fg, hv, tc) in enumerate(specs):
            b = ctk.CTkButton(
                bg, text=text, command=cmd,
                fg_color=fg, hover_color=hv, text_color=tc,
                font=ctk.CTkFont(size=12, weight="bold" if "Install" in text else "normal"),
                height=38, corner_radius=10,
            )
            b.grid(row=idx // 3, column=idx % 3, sticky="ew", padx=3, pady=3)
            self.buttons.append(b)

        # ── Local Paths ──
        paths = self._card(pad, "Local Paths")
        ctk.CTkLabel(
            paths, text=f"Config  {config_path()}",
            font=ctk.CTkFont(size=10), text_color=_TXT3,
            anchor="w", wraplength=700,
        ).pack(fill="x")
        ctk.CTkLabel(
            paths, text=f"Logs    {log_path()}",
            font=ctk.CTkFont(size=10), text_color=_TXT3,
            anchor="w", wraplength=700,
        ).pack(fill="x", pady=(0, 8))

        pb = ctk.CTkFrame(paths, fg_color="transparent")
        pb.pack(anchor="w")
        for lbl, target in [("Open Config Folder", config_path().parent), ("Open Log Folder", log_path().parent)]:
            b = ctk.CTkButton(
                pb, text=lbl,
                command=lambda t=target: self._open_path(t),
                fg_color=_SEC, hover_color=_SEC_H,
                text_color=_TXT3, font=ctk.CTkFont(size=11),
                height=30, corner_radius=8, width=140,
            )
            b.pack(side="left", padx=(0, 8))
            self.buttons.append(b)

    # ────────────────────────────── callbacks ──────────────────────────────────

    def _toggle_key(self) -> None:
        if self.key_entry:
            self.key_entry.configure(show="" if self.show_key_var.get() else "\u25cf")

    def _open_path(self, target) -> None:
        try:
            system = platform.system()
            if system == "Windows":
                os.startfile(str(target))  # type: ignore[attr-defined]
            elif system == "Darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not open {target}.\n\n{exc}")

    def _config_from_form(self) -> AgentConfig:
        return AgentConfig(
            api_base_url=self.server_var.get().strip(),
            agent_name=self.agent_name_var.get().strip(),
            username=self.username_var.get().strip() or "agent",
            shared_key=self.shared_key_var.get().strip(),
            capabilities=[i.strip() for i in self.capabilities_var.get().split(",") if i.strip()],
            poll_interval_seconds=float(self.poll_var.get().strip()),
            heartbeat_interval_seconds=float(self.heartbeat_var.get().strip()),
            allow_unassigned=self.allow_unassigned_var.get(),
            task_timeout_seconds=int(float(self.timeout_var.get().strip())),
            auto_start=self.auto_start_var.get(),
        )

    # ── status ──

    def _set_status(self, title: str, detail: str | None = None, tone: str = "info") -> None:
        self.status_title_var.set(title)
        if detail is not None:
            self.status_detail_var.set(detail)
        colors = {"info": _ACCENT, "success": _GREEN, "error": _RED, "muted": _TXT3}
        if self.status_title_lbl:
            self.status_title_lbl.configure(text_color=colors.get(tone, _ACCENT))

    def _set_busy(self, busy: bool, title: str | None = None, detail: str | None = None) -> None:
        state = "disabled" if busy else "normal"
        for btn in self.buttons:
            if busy and btn.cget("text") == "Exit":
                btn.configure(state="normal")
            else:
                btn.configure(state=state)
        for field in self.fields:
            try:
                field.configure(state=state)
            except Exception:
                continue
        if self.progress_bar:
            if busy:
                self.progress_bar.start()
            else:
                self.progress_bar.stop()
                self.progress_bar.set(0)
        if title or detail:
            self._set_status(title or self.status_title_var.get(), detail or self.status_detail_var.get())

    def _update_status_from_worker(self, detail: str, title: str = "Working...") -> None:
        self.worker_events.put(("status", (title, detail)))

    def _drain_worker_events(self) -> None:
        try:
            while True:
                kind, payload = self.worker_events.get_nowait()
                if kind == "status":
                    self._set_status(str(payload[0]), str(payload[1]))
                elif kind == "success":
                    msg, det, popup = payload
                    self._finish_success(
                        str(msg) if msg else None,
                        str(det) if det else None,
                        bool(popup),
                    )
                elif kind == "error":
                    self._finish_error(str(payload[0]) if payload else "Unknown error")
        except Empty:
            pass
        finally:
            self.root.after(100, self._drain_worker_events)

    def _run_async(
        self,
        work,
        success_message: str | None = None,
        success_detail: str | None = None,
        show_success_popup: bool = False,
        initial_title: str = "Working...",
        initial_detail: str = "Please wait.",
    ) -> None:
        def task() -> None:
            try:
                result = work()
            except Exception as exc:
                self.worker_events.put(("error", (str(exc),)))
            else:
                det = success_detail
                if isinstance(result, str) and result.strip():
                    det = f"{success_detail}\n\n{result}" if success_detail else result
                self.worker_events.put(("success", (success_message, det, show_success_popup)))

        self._set_busy(True, initial_title, initial_detail)
        threading.Thread(target=task, daemon=True).start()

    def _finish_success(self, message: str | None, detail: str | None, show_popup: bool) -> None:
        self._set_busy(False)
        self._set_status(message or "Done", detail or "Completed successfully.", "success")
        if message and show_popup:
            messagebox.showinfo(APP_NAME, message)

    def _finish_error(self, message: str) -> None:
        self._set_busy(False)
        self._set_status("Action failed", message, "error")
        messagebox.showerror(APP_NAME, message)

    # ── action handlers ──

    def on_test_connection(self) -> None:
        def work() -> None:
            cfg = self._config_from_form()
            errors = cfg.validate()
            if errors:
                raise ValueError("\n".join(errors))
            test_connection(cfg, progress_callback=self._update_status_from_worker)

        self._run_async(
            work,
            success_message="Connection succeeded",
            success_detail="Server reachable, credentials valid, registration + heartbeat accepted.",
            initial_title="Testing connection...",
            initial_detail="Checking health, registration, and heartbeat.",
        )

    def on_save_only(self) -> None:
        self._run_async(
            lambda: save_config(self._config_from_form()),
            success_message="Configuration saved",
            success_detail="Settings written locally.",
            initial_title="Saving...",
            initial_detail="Writing config.",
        )

    def on_install(self) -> None:
        def work():
            return install_agent(
                self._config_from_form(),
                start_now=True,
                progress_callback=self._update_status_from_worker,
            )

        self._run_async(
            work,
            success_message="Agent installed and started",
            success_detail="Config saved, connection validated, background agent launched.",
            show_success_popup=True,
            initial_title="Installing agent...",
            initial_detail="Saving config, validating, enabling auto-start, launching.",
        )

    def on_remove_autostart(self) -> None:
        self._run_async(
            uninstall_autostart,
            success_message="Auto-start removed",
            success_detail="Agent will no longer start automatically at login.",
            initial_title="Removing auto-start...",
            initial_detail="Cleaning up.",
        )

    def on_remove_agent(self) -> None:
        confirmed = messagebox.askyesno(
            f"Remove {APP_NAME}",
            "This will unregister the agent, stop background processes, remove auto-start, "
            "and delete local config.\n\nContinue?",
            icon=messagebox.WARNING,
        )
        if not confirmed:
            return

        def work():
            return remove_agent(self._config_from_form(), remove_remote=True, purge_related=True)

        self._run_async(
            work,
            success_message="Agent removal finished",
            success_detail="Agent cleaned up locally and server unregister attempted.",
            show_success_popup=True,
            initial_title="Removing agent...",
            initial_detail="Unregistering, stopping, removing auto-start, deleting config.",
        )

    def run(self) -> None:
        self.root.mainloop()
