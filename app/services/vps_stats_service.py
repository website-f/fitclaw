"""Thin client for the vps_stats Go microservice.

Single source of truth for how the Python side reaches the Go service.
Keep the surface small so if we later move vps_stats behind k8s or swap
transports, only this file changes.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class VpsStatsUnavailable(RuntimeError):
    """Raised when vps_stats is unreachable or returns an error."""


class UsageService:
    """Thin client for the MemoryCore usage ledger (in-process).

    We call our own HTTP surface so the formatting path is identical to
    what external callers see. Cheap — same process, localhost, no TLS.
    """

    @staticmethod
    def fetch_summary(period: str = "today") -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.api_internal_url.rstrip('/')}/api/v1/memorycore/usage/summary"
        params = {"user_id": "fitclaw", "period": period}
        try:
            response = httpx.get(url, params=params, timeout=5.0)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise VpsStatsUnavailable(f"usage API unreachable: {exc}") from exc

    @staticmethod
    def format_summary_for_telegram(summary: dict[str, Any]) -> str:
        total = summary.get("total", {})
        lines = [
            f"💰 Token usage — {summary.get('period', '?')}",
            f"Calls:  {total.get('calls', 0)}",
            f"Input:  {total.get('input_tokens', 0):,} tokens",
            f"Output: {total.get('output_tokens', 0):,} tokens",
            f"Cost:   ${total.get('cost_usd', 0):.4f}",
        ]
        by_tool = summary.get("by_tool") or {}
        if by_tool:
            lines.append("")
            lines.append("By tool:")
            for tool, b in sorted(by_tool.items()):
                lines.append(
                    f"  {tool:<14} {b.get('calls', 0):>3}×  "
                    f"${b.get('cost_usd', 0):.4f}"
                )
        by_model = summary.get("by_model") or {}
        if by_model:
            lines.append("")
            lines.append("By model:")
            for model, b in sorted(by_model.items()):
                lines.append(
                    f"  {model:<28} {b.get('calls', 0):>3}×  "
                    f"${b.get('cost_usd', 0):.4f}"
                )
        return "\n".join(lines)


class VpsStatsService:
    @staticmethod
    def fetch() -> dict[str, Any]:
        settings = get_settings()
        url = f"{settings.vps_stats_internal_url.rstrip('/')}/stats"
        headers: dict[str, str] = {}
        if settings.vps_stats_token:
            headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
        try:
            response = httpx.get(url, headers=headers, timeout=5.0)
        except httpx.HTTPError as exc:
            logger.warning("vps_stats unreachable at %s: %s", url, exc)
            raise VpsStatsUnavailable(f"vps_stats unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise VpsStatsUnavailable(
                f"vps_stats returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    @staticmethod
    def fetch_processes(top: int = 10, by: str = "cpu") -> list[dict[str, Any]]:
        settings = get_settings()
        url = f"{settings.vps_stats_internal_url.rstrip('/')}/processes"
        params = {"top": str(top), "by": by}
        headers: dict[str, str] = {}
        if settings.vps_stats_token:
            headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
        try:
            response = httpx.get(url, headers=headers, params=params, timeout=10.0)
        except httpx.HTTPError as exc:
            raise VpsStatsUnavailable(f"vps_stats unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise VpsStatsUnavailable(
                f"vps_stats returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    @staticmethod
    def fetch_vscode_windows() -> list[dict[str, Any]]:
        settings = get_settings()
        url = f"{settings.vps_stats_internal_url.rstrip('/')}/vscode"
        headers: dict[str, str] = {}
        if settings.vps_stats_token:
            headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
        try:
            response = httpx.get(url, headers=headers, timeout=10.0)
        except httpx.HTTPError as exc:
            raise VpsStatsUnavailable(f"vps_stats unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise VpsStatsUnavailable(
                f"vps_stats returned {response.status_code}: {response.text[:200]}"
            )
        return response.json() or []

    @staticmethod
    def fetch_claude_sessions() -> list[dict[str, Any]]:
        settings = get_settings()
        url = f"{settings.vps_stats_internal_url.rstrip('/')}/claude_sessions"
        headers: dict[str, str] = {}
        if settings.vps_stats_token:
            headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
        try:
            response = httpx.get(url, headers=headers, timeout=10.0)
        except httpx.HTTPError as exc:
            raise VpsStatsUnavailable(f"vps_stats unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise VpsStatsUnavailable(
                f"vps_stats returned {response.status_code}: {response.text[:200]}"
            )
        return response.json() or []

    @staticmethod
    def format_vscode_for_telegram(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No open VS Code windows detected."
        lines = [f"VS Code windows ({len(rows)}):"]
        for row in rows:
            lines.append(
                f"  • {row.get('project_name', '?')}  "
                f"({row.get('workspace_path', '?')})"
            )
        return "\n".join(lines)

    @staticmethod
    def format_sessions_for_telegram(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No recent Claude Code sessions found."
        lines = [f"Recent Claude sessions ({len(rows)}):"]
        for row in rows:
            ago_min = int((row.get("updated_ago_ms") or 0) / 60000)
            preview = row.get("last_user_msg") or ""
            if len(preview) > 60:
                preview = preview[:60] + "…"
            lines.append(
                f"  • {row.get('project_name', '?')}  "
                f"({ago_min}m ago)  {row.get('session_id', '')[:8]}\n"
                f"      {preview}"
            )
        return "\n".join(lines)

    @staticmethod
    def fetch_disks() -> list[dict[str, Any]]:
        settings = get_settings()
        url = f"{settings.vps_stats_internal_url.rstrip('/')}/disks"
        headers: dict[str, str] = {}
        if settings.vps_stats_token:
            headers["Authorization"] = f"Bearer {settings.vps_stats_token}"
        try:
            response = httpx.get(url, headers=headers, timeout=5.0)
        except httpx.HTTPError as exc:
            raise VpsStatsUnavailable(f"vps_stats unreachable: {exc}") from exc
        if response.status_code >= 400:
            raise VpsStatsUnavailable(
                f"vps_stats returned {response.status_code}: {response.text[:200]}"
            )
        return response.json()

    @staticmethod
    def format_processes_for_telegram(rows: list[dict[str, Any]], by: str) -> str:
        if not rows:
            return "No processes returned."
        sort_label = "CPU%" if by != "mem" else "MEM%"
        lines = [f"Top {len(rows)} processes by {sort_label}:"]
        for row in rows:
            name = (row.get("name") or "?")[:24]
            lines.append(
                f"  {row.get('pid', 0):>6}  {name:<24} "
                f"cpu={row.get('cpu_percent', 0):>5.1f}%  "
                f"mem={row.get('mem_percent', 0):>5.1f}%  "
                f"rss={row.get('mem_rss_mb', 0)}MB"
            )
        return "\n".join(lines)

    @staticmethod
    def format_disks_for_telegram(rows: list[dict[str, Any]]) -> str:
        if not rows:
            return "No mounted disks reported."
        lines = ["Disks:"]
        for row in rows:
            lines.append(
                f"  {row.get('mountpoint', '?'):<16} "
                f"{row.get('used_gb', 0):>6.1f} / {row.get('total_gb', 0):>6.1f} GB "
                f"({row.get('used_percent', 0):>5.1f}%)  "
                f"{row.get('fstype', '?')}"
            )
        return "\n".join(lines)

    @staticmethod
    def format_for_telegram(stats: dict[str, Any]) -> str:
        uptime = timedelta(seconds=int(stats.get("uptime_sec", 0)))
        load = (
            stats.get("load_avg_1", 0.0),
            stats.get("load_avg_5", 0.0),
            stats.get("load_avg_15", 0.0),
        )
        lines = [
            f"📊 VPS stats — {stats.get('hostname', 'unknown')}",
            f"CPU:    {stats.get('cpu_percent', 0):.1f}%  ({stats.get('cpu_cores', '?')} cores)",
            f"Memory: {stats.get('mem_used_mb', 0):,} / {stats.get('mem_total_mb', 0):,} MB"
            f"  ({stats.get('mem_percent', 0):.1f}%)",
            f"Disk:   {stats.get('disk_used_gb', 0):.1f} / {stats.get('disk_total_gb', 0):.1f} GB"
            f"  ({stats.get('disk_percent', 0):.1f}%)",
            f"Load:   {load[0]:.2f} / {load[1]:.2f} / {load[2]:.2f}",
            f"Procs:  {stats.get('processes', 0):,}",
            f"Up:     {uptime}",
            f"At:     {stats.get('collected_at', '?')}",
        ]
        return "\n".join(lines)
