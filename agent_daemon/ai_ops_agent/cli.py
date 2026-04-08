from __future__ import annotations

import argparse

from ai_ops_agent.config import AgentConfig
from ai_ops_agent.installer import launcher_command, remove_agent, test_connection, uninstall_autostart
from ai_ops_agent.logging_utils import configure_logging
from ai_ops_agent.runtime import AgentRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Personal AI Ops desktop agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run-agent", help="Run the background agent loop")
    run_parser.add_argument("--background", action="store_true", help="Suppress console logging")

    subparsers.add_parser("install-ui", help="Open the setup window")
    subparsers.add_parser("test-connection", help="Validate the saved config against the VPS")
    subparsers.add_parser("show-launch-command", help="Print the auto-start launch command")
    subparsers.add_parser("remove-autostart", help="Remove the auto-start entry")
    subparsers.add_parser("remove-agent", help="Unregister the saved agent and remove local auto-start/config")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "install-ui"

    if command == "install-ui":
        from ai_ops_agent.ui import InstallerWindow

        InstallerWindow().run()
        return 0

    if command == "show-launch-command":
        print(" ".join(launcher_command()))
        return 0

    if command == "remove-autostart":
        uninstall_autostart()
        print("Auto-start removed.")
        return 0

    config = AgentConfig.load()
    logger = configure_logging(background=getattr(args, "background", False))

    if command == "test-connection":
        test_connection(config)
        print("Connection succeeded.")
        return 0

    if command == "remove-agent":
        print(remove_agent(config))
        return 0

    if command == "run-agent":
        runner = AgentRunner(config, logger=logger)
        runner.run_forever()
        return 0

    parser.print_help()
    return 1
