"""Drop-in handlers for `claude_fix` and `git_push` task command types.

Wire this into the existing agent_daemon by importing the handlers in
`task_executor.py` and routing matching command_types to them. The helpers
are stdlib-only so they work on a freshly-installed Windows / Linux / Mac
agent without extra dependencies.

Usage in task_executor.py:

    from app.modules.projects.client import handle_task  # if vendored, or:
    from .claude_fix_executor import run_claude_fix, run_git_push

    if device_command_type == "claude_fix":
        return run_claude_fix(payload)
    if device_command_type == "git_push":
        return run_git_push(payload)

Both functions return (status, result_text, error_text, metadata) — the
shape the existing executor expects. They never raise; on failure they
return ("failed", None, error_text, metadata).
"""
from __future__ import annotations

import os
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# --- Public entry points ---------------------------------------------------


def run_claude_fix(payload: dict[str, Any]) -> tuple[str, str | None, str | None, dict[str, Any]]:
    """Execute a Claude Code fix prompt for a project.

    Required payload fields:
      - local_path : str   (filesystem path to the project on this machine)
      - issue_text : str   (what the user asked to fix)
      - branch     : str   (branch to pull and base the fix on; default "main")
      - project_slug : str (for logging only)
    """
    project_slug = str(payload.get("project_slug") or "unknown")
    local_path = str(payload.get("local_path") or "")
    issue_text = str(payload.get("issue_text") or "").strip()
    branch = str(payload.get("branch") or "main")

    metadata: dict[str, Any] = {"project_slug": project_slug, "branch": branch}

    if not local_path or not Path(local_path).is_dir():
        return "failed", None, f"local_path '{local_path}' is not a directory on this agent", metadata
    if not issue_text:
        return "failed", None, "issue_text is empty", metadata
    if _which("claude") is None:
        return "failed", None, "claude CLI not on PATH — install Claude Code first", metadata

    transcript: list[str] = []
    started = datetime.now(timezone.utc).isoformat()

    # Step 1: sync git
    rc, out, err = _run(["git", "fetch", "origin"], cwd=local_path)
    transcript.append(f"$ git fetch origin\n{_combine(out, err)}")
    if rc != 0:
        metadata["transcript"] = "\n\n".join(transcript)
        return "failed", None, f"git fetch failed: {err.strip()}", metadata

    rc, out, err = _run(["git", "checkout", branch], cwd=local_path)
    transcript.append(f"$ git checkout {branch}\n{_combine(out, err)}")
    if rc != 0:
        metadata["transcript"] = "\n\n".join(transcript)
        return "failed", None, f"git checkout failed: {err.strip()}", metadata

    rc, out, err = _run(["git", "pull", "--ff-only", "origin", branch], cwd=local_path)
    transcript.append(f"$ git pull --ff-only origin {branch}\n{_combine(out, err)}")

    # Step 2: open VS Code (best-effort, non-fatal)
    if _which("code"):
        _run(["code", local_path], cwd=local_path, timeout=10)
        transcript.append(f"$ code {local_path}")

    # Step 3: run Claude Code headless
    prompt = (
        f"You are working on project '{project_slug}'. A user reported this issue:\n\n"
        f"{issue_text}\n\n"
        f"Read AGENTS.md (or CLAUDE.md) first to orient yourself. Diagnose the "
        f"issue, edit files to fix it, and run any relevant tests. Do not commit "
        f"or push — leave changes in the working tree. When done, output a one-paragraph "
        f"summary of what you changed."
    )
    rc, out, err = _run(["claude", "-p", prompt], cwd=local_path, timeout=1800)
    transcript.append(f"$ claude -p '<prompt>'\nrc={rc}\n{_combine(out, err)[-3000:]}")

    # Step 4: collect diff summary
    rc_d, diff_out, _ = _run(["git", "diff", "--stat"], cwd=local_path, timeout=20)
    diff_summary = diff_out.strip() if rc_d == 0 else "(git diff failed)"

    metadata.update({
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "diff_stat": diff_summary,
        "claude_exit_code": rc,
    })
    metadata["transcript"] = "\n\n".join(transcript)

    if rc != 0:
        return "failed", None, f"claude exited {rc}: {err.strip()[:500]}", metadata

    summary = (
        f"✅ claude_fix complete for {project_slug} on branch {branch}.\n\n"
        f"Diff:\n{diff_summary or '(no changes)'}\n\n"
        f"Run /push {project_slug} in Telegram to choose a branch and push."
    )
    return "completed", summary, None, metadata


def run_git_push(payload: dict[str, Any]) -> tuple[str, str | None, str | None, dict[str, Any]]:
    """Stage, commit, and push to a chosen branch.

    Required payload fields:
      - local_path : str
      - branch     : str
      - project_slug : str
      - commit_message : str  (optional; defaults to "fix dispatched via Telegram")
    """
    project_slug = str(payload.get("project_slug") or "unknown")
    local_path = str(payload.get("local_path") or "")
    branch = str(payload.get("branch") or "main")
    commit_msg = str(payload.get("commit_message") or "fix dispatched via Telegram")

    metadata: dict[str, Any] = {"project_slug": project_slug, "branch": branch}
    if not local_path or not Path(local_path).is_dir():
        return "failed", None, f"local_path '{local_path}' is not a directory", metadata

    transcript: list[str] = []

    # Verify there are changes
    rc, out, err = _run(["git", "status", "--porcelain"], cwd=local_path)
    if rc != 0:
        return "failed", None, f"git status failed: {err}", metadata
    if not out.strip():
        return "completed", f"Nothing to push for {project_slug} (working tree clean).", None, metadata
    transcript.append(f"$ git status --porcelain\n{out.strip()}")

    # Switch to / create branch
    rc, out, err = _run(["git", "checkout", branch], cwd=local_path)
    transcript.append(f"$ git checkout {branch}\n{_combine(out, err)}")
    if rc != 0:
        # Try creating a new branch
        rc2, out2, err2 = _run(["git", "checkout", "-b", branch], cwd=local_path)
        transcript.append(f"$ git checkout -b {branch}\n{_combine(out2, err2)}")
        if rc2 != 0:
            metadata["transcript"] = "\n\n".join(transcript)
            return "failed", None, f"could not switch to branch '{branch}'", metadata

    # Stage + commit + push
    for cmd in [
        ["git", "add", "-A"],
        ["git", "commit", "-m", commit_msg],
        ["git", "push", "origin", branch],
    ]:
        rc, out, err = _run(cmd, cwd=local_path, timeout=120)
        transcript.append(f"$ {' '.join(shlex.quote(c) for c in cmd)}\n{_combine(out, err)}")
        if rc != 0 and cmd[1] != "commit":
            # commit can fail if nothing to stage — tolerable; push must succeed
            metadata["transcript"] = "\n\n".join(transcript)
            return "failed", None, f"{' '.join(cmd)} failed: {err.strip()[:300]}", metadata

    metadata["transcript"] = "\n\n".join(transcript)
    summary = (
        f"⬆️ Pushed {project_slug} to origin/{branch}.\n\n"
        f"Run /deploy {project_slug} {branch} in Telegram to redeploy on the VPS."
    )
    return "completed", summary, None, metadata


# --- Helpers ---------------------------------------------------------------


def _which(cmd: str) -> str | None:
    """Tiny shutil.which substitute (works on Windows + posix)."""
    extensions = [""] + (os.environ.get("PATHEXT", "").split(os.pathsep) if os.name == "nt" else [])
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        for ext in extensions:
            candidate = os.path.join(path_dir, cmd + ext)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return None


def _run(args: list[str], cwd: str | None = None, timeout: int = 60) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except FileNotFoundError as exc:
        return 127, "", str(exc)


def _combine(stdout: str, stderr: str) -> str:
    parts = []
    if stdout.strip():
        parts.append(stdout.strip())
    if stderr.strip():
        parts.append("[stderr]\n" + stderr.strip())
    return "\n".join(parts) if parts else "(no output)"
