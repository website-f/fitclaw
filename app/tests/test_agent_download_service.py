import tempfile
import unittest
from pathlib import Path

from app.services.agent_download_service import AgentDownloadService


class AgentDownloadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._original_root = AgentDownloadService.REPO_ROOT
        self._original_downloads_dir = AgentDownloadService.DOWNLOADS_DIR_OVERRIDE
        self.temp_dir = tempfile.TemporaryDirectory()
        AgentDownloadService.REPO_ROOT = Path(self.temp_dir.name)
        AgentDownloadService.DOWNLOADS_DIR_OVERRIDE = str(
            AgentDownloadService.REPO_ROOT / "published-agent-downloads"
        )

    def tearDown(self) -> None:
        AgentDownloadService.REPO_ROOT = self._original_root
        AgentDownloadService.DOWNLOADS_DIR_OVERRIDE = self._original_downloads_dir
        self.temp_dir.cleanup()

    def test_windows_prefers_setup_installer(self) -> None:
        dist = AgentDownloadService.REPO_ROOT / "agent_daemon" / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        generic = dist / "PersonalAIOpsAgent-0.3.1-windows-x64.exe"
        setup = dist / "PersonalAIOpsAgentSetup.exe"
        generic.write_bytes(b"generic")
        setup.write_bytes(b"setup")

        artifact, _ = AgentDownloadService.get_download("windows")
        self.assertEqual(artifact.name, setup.name)

    def test_release_directory_is_checked_before_dist(self) -> None:
        release_dir = AgentDownloadService.REPO_ROOT / "agent_daemon" / "release"
        release_dir.mkdir(parents=True, exist_ok=True)
        published = release_dir / "PersonalAIOpsAgent-0.4.0-windows-x64.exe"
        published.write_bytes(b"release")

        dist = AgentDownloadService.REPO_ROOT / "agent_daemon" / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        fallback = dist / "PersonalAIOpsAgent-0.3.9-windows-x64.exe"
        fallback.write_bytes(b"dist")

        artifact, _ = AgentDownloadService.get_download("windows")
        self.assertEqual(artifact.name, published.name)

    def test_android_falls_back_to_debug_output(self) -> None:
        debug_dir = (
            AgentDownloadService.REPO_ROOT
            / "agent_daemon"
            / "packaging"
            / "android"
            / "app"
            / "build"
            / "outputs"
            / "apk"
            / "debug"
        )
        debug_dir.mkdir(parents=True, exist_ok=True)
        apk = debug_dir / "app-debug.apk"
        apk.write_bytes(b"apk")

        payload = AgentDownloadService.list_downloads()["android"]
        self.assertTrue(payload["available"])
        self.assertEqual(payload["filename"], apk.name)

    def test_published_downloads_override_gitignored_dist(self) -> None:
        published_dir = AgentDownloadService.REPO_ROOT / "published-agent-downloads"
        published_dir.mkdir(parents=True, exist_ok=True)
        published = published_dir / "PersonalAIOpsAgent-0.4.0-windows-x64.exe"
        published.write_bytes(b"published")

        dist = AgentDownloadService.REPO_ROOT / "agent_daemon" / "dist"
        dist.mkdir(parents=True, exist_ok=True)
        fallback = dist / "PersonalAIOpsAgentSetup.exe"
        fallback.write_bytes(b"fallback")

        artifact, _ = AgentDownloadService.get_download("windows")
        self.assertEqual(artifact.name, published.name)

    def test_missing_download_marks_unavailable(self) -> None:
        payload = AgentDownloadService.list_downloads()["windows"]
        self.assertFalse(payload["available"])
        self.assertIsNone(payload["filename"])


if __name__ == "__main__":
    unittest.main()
