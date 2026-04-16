import unittest

from ai_ops_agent.config import AgentConfig


class AgentConfigUrlNormalizationTests(unittest.TestCase):
    def test_normalized_strips_common_ui_paths(self) -> None:
        cfg = AgentConfig(api_base_url="https://fitclaw.example.com/app")
        self.assertEqual(cfg.normalized().api_base_url, "https://fitclaw.example.com")

    def test_normalized_preserves_root_with_port(self) -> None:
        cfg = AgentConfig(api_base_url="http://84.46.249.133:8000/")
        self.assertEqual(cfg.normalized().api_base_url, "http://84.46.249.133:8000")

    def test_validate_rejects_non_root_paths(self) -> None:
        cfg = AgentConfig(api_base_url="https://fitclaw.example.com/custom/path")
        self.assertIn(
            "Server URL must point to the server root, for example https://your-domain.com, not /app or another page.",
            cfg.validate(),
        )


if __name__ == "__main__":
    unittest.main()
