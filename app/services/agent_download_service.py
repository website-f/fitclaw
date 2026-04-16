from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings


class AgentDownloadService:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    DOWNLOADS_DIR_OVERRIDE: str | None = None

    _PLATFORMS = {
        "windows": {
            "label": "Windows Desktop Agent",
            "description": "Installer-ready desktop agent for Windows (.exe).",
            "media_type": "application/octet-stream",
            "locations": [
                ("$agent_downloads_dir", ["*Setup*.exe", "*windows*.exe", "*.exe"]),
                ("$agent_downloads_dir/windows", ["*Setup*.exe", "*windows*.exe", "*.exe"]),
                ("agent_daemon/dist", ["*Setup*.exe", "*windows*.exe", "*.exe"]),
            ],
        },
        "android": {
            "label": "Android Agent APK",
            "description": "Installable Android companion agent (.apk).",
            "media_type": "application/vnd.android.package-archive",
            "locations": [
                ("$agent_downloads_dir", ["*mobile-agent-android*.apk", "*.apk"]),
                ("$agent_downloads_dir/android", ["*mobile-agent-android*.apk", "*.apk"]),
                ("agent_daemon/dist", ["*mobile-agent-android*.apk", "*.apk"]),
                ("agent_daemon/packaging/android/app/build/outputs/apk/debug", ["*.apk"]),
            ],
        },
    }

    @classmethod
    def list_downloads(cls) -> dict[str, dict]:
        return {platform: cls._serialize(platform, cls._find_artifact(platform)) for platform in cls._PLATFORMS}

    @classmethod
    def get_download(cls, platform: str) -> tuple[Path, dict]:
        artifact = cls._find_artifact(platform)
        if artifact is None:
            raise FileNotFoundError(f"No downloadable installer is currently available for {platform}.")
        return artifact, cls._PLATFORMS[platform]

    @classmethod
    def _serialize(cls, platform: str, artifact: Path | None) -> dict:
        config = cls._PLATFORMS[platform]
        payload = {
            "platform": platform,
            "label": config["label"],
            "description": config["description"],
            "download_url": f"/api/v1/downloads/agents/{platform}",
            "available": artifact is not None,
            "filename": None,
            "size_bytes": None,
            "updated_at": None,
        }
        if artifact is not None:
            payload.update(
                {
                    "filename": artifact.name,
                    "size_bytes": artifact.stat().st_size,
                    "updated_at": datetime.fromtimestamp(
                        artifact.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return payload

    @classmethod
    def _find_artifact(cls, platform: str) -> Path | None:
        config = cls._PLATFORMS.get(platform)
        if config is None:
            raise KeyError(platform)

        for location, patterns in config["locations"]:
            directory = cls._resolve_directory(location)
            if directory is None:
                continue
            if not directory.exists():
                continue
            for pattern in patterns:
                matches = sorted(
                    (path for path in directory.glob(pattern) if path.is_file()),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                )
                if matches:
                    return matches[0]
        return None

    @classmethod
    def _resolve_directory(cls, location: str) -> Path | None:
        if location.startswith("$agent_downloads_dir"):
            base_dir = cls._configured_downloads_dir()
            if base_dir is None:
                return None
            suffix = location.removeprefix("$agent_downloads_dir").strip("/\\")
            return base_dir / suffix if suffix else base_dir

        directory = Path(location)
        if not directory.is_absolute():
            directory = cls.REPO_ROOT / directory
        return directory

    @classmethod
    def _configured_downloads_dir(cls) -> Path | None:
        raw_dir = cls.DOWNLOADS_DIR_OVERRIDE
        if raw_dir is None:
            raw_dir = get_settings().agent_downloads_dir
        raw_dir = str(raw_dir or "").strip()
        if not raw_dir:
            return None
        directory = Path(raw_dir)
        if not directory.is_absolute():
            directory = cls.REPO_ROOT / directory
        return directory
