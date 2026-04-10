#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_SERVER_URL = os.environ.get("MEMORYCORE_SERVER_URL", "http://localhost:8000").rstrip("/")
DEFAULT_USER_ID = os.environ.get("MEMORYCORE_USER_ID", "fitclaw")
KNOWN_AREAS = {"profile", "project", "say"}
SKIP_DIRS = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".nuxt",
    ".mypy_cache",
    ".pytest_cache",
    ".gradle",
    "Pods",
    "build-output",
    "data",
}
IMPORTANT_FILE_NAMES = (
    "README.md",
    "README.txt",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    "Makefile",
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "project"


def _request_json(
    method: str,
    server_url: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{server_url.rstrip('/')}{path}"
    if query:
        url += "?" + urlencode(query)
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"MemoryCore request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"MemoryCore request failed: {exc}") from exc
    return json.loads(raw) if raw else {}


def _request_optional_json(server_url: str, path: str, *, query: dict[str, str] | None = None) -> Any | None:
    url = f"{server_url.rstrip('/')}{path}"
    if query:
        url += "?" + urlencode(query)
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        if exc.code == 404:
            return None
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"MemoryCore request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"MemoryCore request failed: {exc}") from exc
    return json.loads(raw) if raw else {}


def _request_text(server_url: str, path: str, *, query: dict[str, str] | None = None) -> str:
    url = f"{server_url.rstrip('/')}{path}"
    if query:
        url += "?" + urlencode(query)
    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"MemoryCore request failed ({exc.code}): {detail}") from exc
    except URLError as exc:
        raise SystemExit(f"MemoryCore request failed: {exc}") from exc


def _first_readme_summary(project_path: Path) -> str:
    for name in ("README.md", "README.txt", "README"):
        candidate = project_path / name
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")
        lines = [line.strip() for line in text.splitlines()]
        paragraphs = []
        current: list[str] = []
        for line in lines:
            if not line:
                if current:
                    paragraphs.append(" ".join(current).strip())
                    current = []
                continue
            if line.startswith("#") and not current:
                continue
            current.append(line)
        if current:
            paragraphs.append(" ".join(current).strip())
        for paragraph in paragraphs:
            cleaned = paragraph.strip()
            if cleaned:
                return cleaned[:500]
    return ""


def _collect_structure(project_path: Path, max_dirs: int = 24, max_files: int = 40) -> tuple[list[str], list[str]]:
    directories: list[str] = []
    files: list[str] = []

    for root, dirnames, filenames in os.walk(project_path):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        rel_root = Path(root).relative_to(project_path)
        if len(rel_root.parts) > 2:
            dirnames[:] = []
            continue
        if rel_root != Path("."):
            rel_text = rel_root.as_posix()
            if rel_text not in directories and len(directories) < max_dirs:
                directories.append(rel_text + "/")

        for filename in sorted(filenames):
            if (
                filename.startswith(".memorycore-")
                or filename.startswith("=")
                or filename.lower().endswith((".pyc", ".pyo", ".pyd", ".db"))
            ):
                continue
            rel_path = (rel_root / filename).as_posix() if rel_root != Path(".") else filename
            if len(Path(rel_path).parts) > 3:
                continue
            if rel_path not in files and len(files) < max_files:
                files.append(rel_path)
        if len(directories) >= max_dirs and len(files) >= max_files:
            break

    return directories, files


def _important_files(files: list[str]) -> list[str]:
    results: list[str] = []
    file_set = {item.lower(): item for item in files}
    for item in IMPORTANT_FILE_NAMES:
        match = file_set.get(item.lower())
        if match:
            results.append(match)
    if "app/main.py" in files:
        results.append("app/main.py")
    if "app/services/message_service.py" in files:
        results.append("app/services/message_service.py")
    return results[:20]


def _detect_stack(project_path: Path, files: list[str]) -> list[str]:
    joined = "\n".join(files).lower()
    results: list[str] = []
    if "package.json" in joined:
        results.append("Node.js / npm")
    if "pyproject.toml" in joined or "requirements.txt" in joined:
        results.append("Python")
    if "dockerfile" in joined:
        results.append("Docker")
    if "docker-compose.yml" in joined or "docker-compose.yaml" in joined:
        results.append("Docker Compose")
    requirements = project_path / "requirements.txt"
    if requirements.exists():
        try:
            contents = requirements.read_text(encoding="utf-8", errors="replace").lower()
        except Exception:
            contents = ""
        if "fastapi" in contents:
            results.append("FastAPI")
    if any(name.endswith(".tsx") or name.endswith(".jsx") for name in files):
        results.append("React-style frontend")
    if any("capacitor" in name.lower() for name in files):
        results.append("Capacitor mobile wrapper")
    return results[:12]


def _detect_commands(project_path: Path) -> list[str]:
    commands: list[str] = []
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8", errors="replace"))
            scripts = data.get("scripts", {})
            if isinstance(scripts, dict):
                for name in list(scripts.keys())[:8]:
                    commands.append(f"npm run {name}")
        except Exception:
            pass
    if (project_path / "docker-compose.yml").exists() or (project_path / "docker-compose.yaml").exists():
        commands.append("docker compose up -d")
    if (project_path / "requirements.txt").exists():
        commands.append("python -m compileall app")
    if (project_path / "Makefile").exists():
        commands.append("make")
    return commands[:12]


def _git_origin(project_path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(project_path), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception:
        return None
    origin = result.stdout.strip()
    return origin or None


def _build_project_payload(args) -> tuple[str, dict[str, Any], Path]:
    project_path = Path(getattr(args, "path", ".")).expanduser().resolve()
    if not project_path.exists():
        raise SystemExit(f"Project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise SystemExit(f"Project path must be a directory: {project_path}")

    project_key = _slugify(getattr(args, "project_key", None) or project_path.name)
    directories, files = _collect_structure(project_path)
    summary = (getattr(args, "summary", None) or _first_readme_summary(project_path) or f"Memory snapshot for {project_path.name}.").strip()
    payload = {
        "title": getattr(args, "title", None) or project_path.name.replace("-", " ").replace("_", " ").title(),
        "summary": summary,
        "root_hint": str(project_path),
        "repo_origin": getattr(args, "repo_origin", None) or _git_origin(project_path),
        "stack": list(dict.fromkeys([*(getattr(args, "stack", []) or []), *_detect_stack(project_path, files)])),
        "goals": getattr(args, "goal", []) or [],
        "important_files": list(dict.fromkeys([*(getattr(args, "important_file", []) or []), *_important_files(files)])),
        "commands": list(dict.fromkeys([*(getattr(args, "command", []) or []), *_detect_commands(project_path)])),
        "structure": list(dict.fromkeys([*directories, *files[:20]]))[:60],
        "preferences": getattr(args, "preference", []) or [],
        "notes": getattr(args, "note", []) or [],
        "tags": getattr(args, "tag", []) or [],
    }
    return project_key, payload, project_path


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _default_output_for_project(path: str | Path) -> Path:
    return Path(path).expanduser().resolve() / "MEMORYCORE.md"


def _normalize_phrase(text: str) -> str:
    normalized = " ".join((text or "").strip().split())
    normalized = re.sub(r"^\s*hey\s+[\w-]+[,\s:;-]*", "", normalized, flags=re.IGNORECASE)
    return normalized.strip()


def _project_key_from_args(args) -> str:
    project_path = Path(getattr(args, "path", ".")).expanduser().resolve()
    return _slugify(getattr(args, "project_key", None) or project_path.name)


def _build_args_namespace(args, **overrides):
    data = vars(args).copy()
    data.update(overrides)
    return argparse.Namespace(**data)


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(pattern in text for pattern in patterns)


def _extract_preference(text: str) -> str | None:
    patterns = (
        r"remember (?:that )?i prefer (?P<value>.+)",
        r"remember this preference[:\s]+(?P<value>.+)",
        r"my preference is (?P<value>.+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group("value").strip(" .")
            if value:
                return value[0].upper() + value[1:]
    return None


def cmd_profile_show(args) -> int:
    data = _request_json("GET", args.server_url, "/api/v1/memorycore/profile", query={"user_id": args.user_id})
    print(json.dumps(data, indent=2, default=str))
    return 0


def cmd_profile_set(args) -> int:
    existing = _request_optional_json(args.server_url, "/api/v1/memorycore/profile", query={"user_id": args.user_id}) or {}
    payload = {
        "display_name": args.display_name if args.display_name is not None else existing.get("display_name"),
        "about": args.about if args.about is not None else existing.get("about"),
        "preferences": list(dict.fromkeys([*(existing.get("preferences") or []), *(args.preference or [])])),
        "coding_preferences": list(dict.fromkeys([*(existing.get("coding_preferences") or []), *(args.coding_preference or [])])),
        "workflow_preferences": list(dict.fromkeys([*(existing.get("workflow_preferences") or []), *(args.workflow_preference or [])])),
        "notes": list(dict.fromkeys([*(existing.get("notes") or []), *(args.note or [])])),
        "tags": list(dict.fromkeys([*(existing.get("tags") or []), *(args.tag or [])])),
    }
    data = _request_json("PUT", args.server_url, "/api/v1/memorycore/profile", query={"user_id": args.user_id}, body=payload)
    print(f"Saved MemoryCore profile for {data['user_id']}.")
    return 0


def cmd_profile_clear(args) -> int:
    data = _request_json("DELETE", args.server_url, "/api/v1/memorycore/profile", query={"user_id": args.user_id})
    print("Deleted MemoryCore profile." if data.get("deleted") else "No MemoryCore profile was stored.")
    return 0


def cmd_project_list(args) -> int:
    items = _request_json("GET", args.server_url, "/api/v1/memorycore/projects", query={"user_id": args.user_id})
    if not items:
        print("No MemoryCore projects stored yet.")
        return 0
    for item in items:
        print(f"- {item['project_key']}: {item['title']} ({item['updated_at']})")
    return 0


def cmd_project_save(args) -> int:
    project_key, payload, project_path = _build_project_payload(args)
    data = _request_json(
        "PUT",
        args.server_url,
        f"/api/v1/memorycore/projects/{project_key}",
        query={"user_id": args.user_id},
        body=payload,
    )
    print(f"Saved project memory `{data['project_key']}` to {args.server_url}.")
    if args.write_local:
        markdown = _request_text(
            args.server_url,
            f"/api/v1/memorycore/projects/{project_key}/markdown",
            query={"user_id": args.user_id},
        )
        output = Path(args.output).expanduser().resolve() if args.output else project_path / "MEMORYCORE.md"
        _write_text(output, markdown)
        print(f"Wrote local MemoryCore file to {output}")
    return 0


def cmd_project_pull(args) -> int:
    markdown = _request_text(
        args.server_url,
        f"/api/v1/memorycore/projects/{_slugify(args.project_key)}/markdown",
        query={"user_id": args.user_id},
    )
    output = Path(args.output).expanduser().resolve()
    _write_text(output, markdown)
    print(f"Wrote MemoryCore file to {output}")
    return 0


def cmd_project_show(args) -> int:
    markdown = _request_text(
        args.server_url,
        f"/api/v1/memorycore/projects/{_slugify(args.project_key)}/markdown",
        query={"user_id": args.user_id},
    )
    print(markdown.rstrip())
    return 0


def cmd_project_delete(args) -> int:
    data = _request_json(
        "DELETE",
        args.server_url,
        f"/api/v1/memorycore/projects/{_slugify(args.project_key)}",
        query={"user_id": args.user_id},
    )
    print(f"Deleted project memory `{_slugify(args.project_key)}`." if data.get("deleted") else "No matching project memory was found.")
    return 0


def cmd_project_clear(args) -> int:
    data = _request_json("DELETE", args.server_url, "/api/v1/memorycore/projects", query={"user_id": args.user_id})
    deleted = int(data.get("deleted") or 0)
    print(f"Deleted {deleted} project memory item{'s' if deleted != 1 else ''}.")
    return 0


def cmd_clear_all(args) -> int:
    data = _request_json("DELETE", args.server_url, "/api/v1/memorycore", query={"user_id": args.user_id})
    print(
        "Cleared MemoryCore. "
        f"Deleted profile: {int(data.get('deleted_profile') or 0)}, "
        f"deleted projects: {int(data.get('deleted_projects') or 0)}."
    )
    return 0


def cmd_say(args) -> int:
    phrase = _normalize_phrase(" ".join(args.phrase or []).strip())
    if not phrase:
        raise SystemExit("Please provide a MemoryCore instruction, for example: hey memorycore, please remember this whole thing")

    lowered = phrase.lower()
    project_key = args.project_key or _project_key_from_args(args)
    project_output = args.output or str(_default_output_for_project(args.path))

    if _contains_any(lowered, ("clear all memory", "forget everything", "wipe memorycore", "wipe all memory")):
        return cmd_clear_all(args)

    if _contains_any(lowered, ("list my projects", "list projects", "show my projects", "show my memories", "list my memories")):
        return cmd_project_list(args)

    if _contains_any(lowered, ("show this project memory", "view this project memory", "show this memory", "open this memory")):
        return cmd_project_show(_build_args_namespace(args, project_key=project_key))

    if _contains_any(lowered, ("pull this project memory", "pull this memory", "pull this project", "restore this project memory")):
        return cmd_project_pull(_build_args_namespace(args, project_key=project_key, output=project_output))

    if _contains_any(lowered, ("forget this project", "delete this project memory", "remove this project memory", "forget this memory")):
        return cmd_project_delete(_build_args_namespace(args, project_key=project_key))

    if _contains_any(lowered, ("remember this whole thing", "remember this project", "save this project memory", "save this whole project", "remember everything in this project")):
        note = args.note or []
        if phrase and phrase.lower() not in {"remember this whole thing", "remember this project"}:
            note = [*note, f"Saved via natural command: {phrase}"]
        return cmd_project_save(
            _build_args_namespace(
                args,
                project_key=project_key,
                output=project_output,
                write_local=not args.no_write_local,
                note=note,
            )
        )

    preference = _extract_preference(phrase)
    if preference:
        return cmd_profile_set(_build_args_namespace(args, preference=[*(args.preference or []), preference]))

    if _contains_any(lowered, ("show my profile", "show my preferences", "show profile memory")):
        return cmd_profile_show(args)

    if _contains_any(lowered, ("forget my profile", "clear my profile", "delete my profile")):
        return cmd_profile_clear(args)

    if "remember" in lowered:
        return cmd_project_save(
            _build_args_namespace(
                args,
                project_key=project_key,
                output=project_output,
                write_local=not args.no_write_local,
                note=[*(args.note or []), f"MemoryCore note: {phrase}"],
            )
        )

    raise SystemExit(
        "I could not map that MemoryCore instruction yet. Try phrases like "
        "`hey memorycore, please remember this whole thing`, "
        "`hey memorycore, list my projects`, or "
        "`hey memorycore, forget this project`."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MemoryCore project memory sync for Personal AI Ops Platform.")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help="MemoryCore server URL.")
    parser.add_argument("--user-id", default=DEFAULT_USER_ID, help="MemoryCore user id.")

    subparsers = parser.add_subparsers(dest="area", required=True)

    profile_parser = subparsers.add_parser("profile", help="Manage your global MemoryCore profile.")
    profile_sub = profile_parser.add_subparsers(dest="action", required=True)

    profile_show = profile_sub.add_parser("show", help="Show the current profile.")
    profile_show.set_defaults(func=cmd_profile_show)

    profile_set = profile_sub.add_parser("set", help="Save or update the current profile.")
    profile_set.add_argument("--display-name")
    profile_set.add_argument("--about")
    profile_set.add_argument("--preference", action="append", default=[])
    profile_set.add_argument("--coding-preference", action="append", default=[])
    profile_set.add_argument("--workflow-preference", action="append", default=[])
    profile_set.add_argument("--note", action="append", default=[])
    profile_set.add_argument("--tag", action="append", default=[])
    profile_set.set_defaults(func=cmd_profile_set)

    profile_clear = profile_sub.add_parser("clear", help="Delete the stored profile.")
    profile_clear.set_defaults(func=cmd_profile_clear)

    project_parser = subparsers.add_parser("project", help="Manage per-project memory snapshots.")
    project_sub = project_parser.add_subparsers(dest="action", required=True)

    project_list = project_sub.add_parser("list", help="List stored project memories.")
    project_list.set_defaults(func=cmd_project_list)

    project_save = project_sub.add_parser("save", help="Capture a project memory snapshot.")
    project_save.add_argument("--path", default=".")
    project_save.add_argument("--project-key")
    project_save.add_argument("--title")
    project_save.add_argument("--summary")
    project_save.add_argument("--repo-origin")
    project_save.add_argument("--goal", action="append", default=[])
    project_save.add_argument("--stack", action="append", default=[])
    project_save.add_argument("--command", action="append", default=[])
    project_save.add_argument("--important-file", action="append", default=[])
    project_save.add_argument("--preference", action="append", default=[])
    project_save.add_argument("--note", action="append", default=[])
    project_save.add_argument("--tag", action="append", default=[])
    project_save.add_argument("--write-local", action="store_true")
    project_save.add_argument("--output", help="Optional local output path for MEMORYCORE.md.")
    project_save.set_defaults(func=cmd_project_save)

    project_pull = project_sub.add_parser("pull", help="Pull a stored project into a local MEMORYCORE.md file.")
    project_pull.add_argument("--project-key", required=True)
    project_pull.add_argument("--output", required=True)
    project_pull.set_defaults(func=cmd_project_pull)

    project_show = project_sub.add_parser("show", help="Print a stored project memory markdown to stdout.")
    project_show.add_argument("--project-key", required=True)
    project_show.set_defaults(func=cmd_project_show)

    project_delete = project_sub.add_parser("delete", help="Delete a single stored project memory.")
    project_delete.add_argument("--project-key", required=True)
    project_delete.set_defaults(func=cmd_project_delete)

    project_clear = project_sub.add_parser("clear", help="Delete every stored project memory.")
    project_clear.set_defaults(func=cmd_project_clear)

    say_parser = subparsers.add_parser("say", help="Use a natural-language MemoryCore command.")
    say_parser.add_argument("phrase", nargs="+")
    say_parser.add_argument("--path", default=".")
    say_parser.add_argument("--project-key")
    say_parser.add_argument("--output")
    say_parser.add_argument("--preference", action="append", default=[])
    say_parser.add_argument("--note", action="append", default=[])
    say_parser.add_argument("--no-write-local", action="store_true")
    say_parser.set_defaults(func=cmd_say)

    return parser


def _extract_global_flags(argv: list[str]) -> tuple[list[str], list[str]]:
    extracted: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(argv):
        token = argv[index]
        if token in {"--server-url", "--user-id"} and index + 1 < len(argv):
            extracted.extend([token, argv[index + 1]])
            index += 2
            continue
        remaining.append(token)
        index += 1
    return extracted, remaining


def _preprocess_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    global_flags, remaining = _extract_global_flags(argv)
    if not remaining:
        return global_flags
    if remaining[0].startswith("-"):
        return [*global_flags, *remaining]
    if remaining[0] in KNOWN_AREAS:
        return [*global_flags, *remaining]
    return [*global_flags, "say", *remaining]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    processed_argv = _preprocess_argv(list(sys.argv[1:] if argv is None else argv))
    args = parser.parse_args(processed_argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
