from __future__ import annotations

import logging
import platform
import socket
import time
from typing import Any

import certifi
import httpx

from ai_ops_agent.config import AgentConfig
from ai_ops_agent.control_actions import available_capabilities, execute_control_command
from ai_ops_agent.task_executor import execute_task


class AgentRunner:
    def __init__(self, config: AgentConfig, logger: logging.Logger) -> None:
        self.config = config.normalized()
        self.logger = logger

    def build_client(self) -> httpx.Client:
        verify: bool | str = certifi.where()
        if self.config.api_base_url.lower().startswith("http://"):
            verify = False

        return httpx.Client(
            base_url=self.config.api_base_url,
            auth=(self.config.username, self.config.shared_key),
            headers={"Content-Type": "application/json"},
            timeout=60,
            verify=verify,
            trust_env=False,
        )

    def agent_metadata(self) -> dict[str, Any]:
        capabilities = available_capabilities(self.config)
        return {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "agent_name": self.config.agent_name,
            "capabilities": capabilities,
        }

    def test_connectivity(self) -> None:
        with self.build_client() as client:
            live = client.get("/health/live")
            live.raise_for_status()
            self.register_agent(client)

    def register_agent(self, client: httpx.Client) -> None:
        capabilities = available_capabilities(self.config)
        response = client.post(
            "/api/v1/agents/register",
            json={
                "name": self.config.agent_name,
                "capabilities_json": capabilities,
                "metadata_json": self.agent_metadata(),
            },
        )
        response.raise_for_status()
        self.logger.info("Registered agent %s", self.config.agent_name)

    def send_heartbeat(self, client: httpx.Client, status: str = "online", current_task_id: str | None = None) -> None:
        response = client.post(
            "/api/v1/agents/heartbeat",
            json={
                "name": self.config.agent_name,
                "status": status,
                "current_task_id": current_task_id,
                "metadata_json": self.agent_metadata(),
            },
        )
        response.raise_for_status()

    def claim_task(self, client: httpx.Client) -> dict[str, Any] | None:
        response = client.post(
            "/api/v1/agent-tasks/claim",
            json={"agent_name": self.config.agent_name, "allow_unassigned": self.config.allow_unassigned},
        )
        response.raise_for_status()
        return response.json()

    def claim_control_command(self, client: httpx.Client) -> dict[str, Any] | None:
        response = client.post(f"/api/v1/agent-control/claim/{self.config.agent_name}")
        response.raise_for_status()
        return response.json()

    def submit_result(
        self,
        client: httpx.Client,
        task_id: str,
        status: str,
        result_text: str | None = None,
        error_text: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        response = client.post(
            f"/api/v1/agent-tasks/{task_id}/result",
            json={
                "agent_name": self.config.agent_name,
                "status": status,
                "result_text": result_text,
                "error_text": error_text,
                "metadata_json": metadata_json or {},
            },
        )
        response.raise_for_status()

    def submit_control_result(
        self,
        client: httpx.Client,
        command_id: str,
        status: str,
        result_json: dict[str, Any] | None = None,
        error_text: str | None = None,
    ) -> None:
        response = client.post(
            f"/api/v1/agent-control/{command_id}/result",
            json={"status": status, "result_json": result_json or {}, "error_text": error_text},
        )
        response.raise_for_status()

    def run_forever(self) -> None:
        failure_delay = max(min(self.config.poll_interval_seconds, 30.0), 5.0)
        idle_sleep = min(self.config.poll_interval_seconds, 1.0)
        while True:
            try:
                with self.build_client() as client:
                    self.register_agent(client)
                    last_heartbeat_at = 0.0
                    while True:
                        now = time.time()
                        if now - last_heartbeat_at >= self.config.heartbeat_interval_seconds:
                            self.send_heartbeat(client)
                            last_heartbeat_at = now

                        control_command = self.claim_control_command(client)
                        if control_command:
                            command_id = control_command["command_id"]
                            self.logger.info("Executing control command %s: %s", command_id, control_command.get("command_type", ""))
                            status, result_json, error_text = execute_control_command(control_command, self.config)
                            self.submit_control_result(
                                client=client,
                                command_id=command_id,
                                status=status,
                                result_json=result_json,
                                error_text=error_text,
                            )
                            continue

                        task = self.claim_task(client)
                        if not task:
                            time.sleep(idle_sleep)
                            continue

                        task_id = task["task_id"]
                        self.logger.info("Claimed task %s: %s", task_id, task.get("title", ""))
                        self.send_heartbeat(client, status="busy", current_task_id=task_id)
                        status, result_text, error_text, metadata_json = execute_task(task, self.config)
                        self.submit_result(
                            client=client,
                            task_id=task_id,
                            status=status,
                            result_text=result_text,
                            error_text=error_text,
                            metadata_json=metadata_json,
                        )
                        self.send_heartbeat(client, status="online", current_task_id=None)
                        self.logger.info("Finished task %s with status %s", task_id, status)
            except Exception:
                self.logger.exception("Agent loop crashed. Retrying in %s seconds.", failure_delay)
                time.sleep(failure_delay)
