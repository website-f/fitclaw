from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ai_ops_agent.config import AgentConfig
from ai_ops_agent.installer import install_agent, remove_agent, save_config, test_connection, uninstall_autostart
from ai_ops_agent.paths import config_path, log_path


class InstallerWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Personal AI Ops Agent Setup")
        self.root.geometry("640x500")
        self.root.resizable(False, False)

        existing = AgentConfig.load()
        self.server_var = tk.StringVar(value=existing.api_base_url)
        self.agent_name_var = tk.StringVar(value=existing.agent_name)
        self.username_var = tk.StringVar(value=existing.username)
        self.shared_key_var = tk.StringVar(value=existing.shared_key)
        self.capabilities_var = tk.StringVar(value=",".join(existing.capabilities))
        self.poll_var = tk.StringVar(value=str(existing.poll_interval_seconds))
        self.heartbeat_var = tk.StringVar(value=str(existing.heartbeat_interval_seconds))
        self.timeout_var = tk.StringVar(value=str(existing.task_timeout_seconds))
        self.allow_unassigned_var = tk.BooleanVar(value=existing.allow_unassigned)
        self.auto_start_var = tk.BooleanVar(value=existing.auto_start)
        self.status_var = tk.StringVar(value="Ready")
        self.buttons: list[ttk.Button] = []
        self._build_layout()

    def _build_layout(self) -> None:
        wrapper = ttk.Frame(self.root, padding=20)
        wrapper.pack(fill="both", expand=True)

        ttk.Label(wrapper, text="Install Desktop Agent", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(
            wrapper,
            text="Save the daemon config, validate the server, enable auto-start, and launch the agent in the background.",
            wraplength=590,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 18))

        fields = [
            ("Server URL", self.server_var),
            ("Agent Name", self.agent_name_var),
            ("Auth Username", self.username_var),
            ("Shared Key", self.shared_key_var),
            ("Capabilities", self.capabilities_var),
            ("Poll Interval (s)", self.poll_var),
            ("Heartbeat Interval (s)", self.heartbeat_var),
            ("Task Timeout (s)", self.timeout_var),
        ]

        for index, (label_text, variable) in enumerate(fields, start=2):
            ttk.Label(wrapper, text=label_text).grid(row=index, column=0, sticky="w", pady=6)
            entry = ttk.Entry(wrapper, textvariable=variable, width=52, show="*" if label_text == "Shared Key" else "")
            entry.grid(row=index, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(wrapper, text="Allow unassigned tasks", variable=self.allow_unassigned_var).grid(
            row=10, column=0, sticky="w", pady=(8, 2)
        )
        ttk.Checkbutton(wrapper, text="Start automatically on login", variable=self.auto_start_var).grid(
            row=10, column=1, sticky="w", pady=(8, 2)
        )

        ttk.Label(wrapper, textvariable=self.status_var, foreground="#0b5cab", wraplength=590).grid(
            row=11, column=0, columnspan=2, sticky="w", pady=(12, 12)
        )

        button_row = ttk.Frame(wrapper)
        button_row.grid(row=12, column=0, columnspan=2, sticky="w", pady=(4, 0))

        for text, command in [
            ("Test Connection", self.on_test_connection),
            ("Save Config", self.on_save_only),
            ("Install and Start", self.on_install),
            ("Remove Agent", self.on_remove_agent),
            ("Remove Auto-Start", self.on_remove_autostart),
            ("Exit", self.root.destroy),
        ]:
            button = ttk.Button(button_row, text=text, command=command)
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)

        ttk.Label(
            wrapper,
            text=f"Config path: {config_path()}\nLog path: {log_path()}",
            wraplength=590,
        ).grid(row=13, column=0, columnspan=2, sticky="w", pady=(20, 0))

        wrapper.columnconfigure(1, weight=1)

    def _config_from_form(self) -> AgentConfig:
        return AgentConfig(
            api_base_url=self.server_var.get().strip(),
            agent_name=self.agent_name_var.get().strip(),
            username=self.username_var.get().strip() or "agent",
            shared_key=self.shared_key_var.get().strip(),
            capabilities=[item.strip() for item in self.capabilities_var.get().split(",") if item.strip()],
            poll_interval_seconds=float(self.poll_var.get().strip()),
            heartbeat_interval_seconds=float(self.heartbeat_var.get().strip()),
            allow_unassigned=self.allow_unassigned_var.get(),
            task_timeout_seconds=int(float(self.timeout_var.get().strip())),
            auto_start=self.auto_start_var.get(),
        )

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        for button in self.buttons:
            button.configure(state="disabled" if busy else "normal")
        if status:
            self.status_var.set(status)

    def _run_async(self, work, success_message: str | None = None) -> None:
        def task() -> None:
            try:
                work()
            except Exception as exc:
                self.root.after(0, lambda: self._finish_error(str(exc)))
            else:
                self.root.after(0, lambda: self._finish_success(success_message))

        self._set_busy(True, "Working...")
        threading.Thread(target=task, daemon=True).start()

    def _finish_success(self, message: str | None) -> None:
        self._set_busy(False, message or "Done")
        if message:
            messagebox.showinfo("Personal AI Ops Agent", message)

    def _finish_error(self, message: str) -> None:
        self._set_busy(False, "Action failed")
        messagebox.showerror("Personal AI Ops Agent", message)

    def on_test_connection(self) -> None:
        def work() -> None:
            config = self._config_from_form()
            errors = config.validate()
            if errors:
                raise ValueError("\n".join(errors))
            test_connection(config)

        self._run_async(work, "Connection succeeded. The server is reachable, the credentials are valid, and registration + heartbeat were accepted.")

    def on_save_only(self) -> None:
        def work() -> None:
            save_config(self._config_from_form())

        self._run_async(work, "Configuration saved.")

    def on_install(self) -> None:
        def work() -> None:
            config = self._config_from_form()
            message = install_agent(config, start_now=True)
            self.root.after(0, lambda: self.status_var.set(message))

        self._run_async(work, "Agent installed and started in the background.")

    def on_remove_autostart(self) -> None:
        self._run_async(uninstall_autostart, "Auto-start entry removed.")

    def on_remove_agent(self) -> None:
        confirmed = messagebox.askyesno(
            "Remove Personal AI Ops Agent",
            (
                "This will unregister the agent from the server, stop its background process, remove auto-start, "
                "and delete the saved local config.\n\nContinue?"
            ),
            icon=messagebox.WARNING,
        )
        if not confirmed:
            return

        def work() -> None:
            config = self._config_from_form()
            message = remove_agent(config, remove_remote=True, purge_related=True)
            self.root.after(0, lambda: self.status_var.set(message))

        self._run_async(work, "Agent removal finished.")

    def run(self) -> None:
        self.root.mainloop()
