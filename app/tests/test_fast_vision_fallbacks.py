import unittest

from app.services.attachment_service import AttachmentService
from app.services.llm_service import LLMService
from app.services.runtime_config_service import RuntimeConfigService


class FastVisionFallbackTests(unittest.TestCase):
    def test_quick_identification_detection(self) -> None:
        self.assertTrue(AttachmentService._looks_like_quick_identification_request("what is this"))
        self.assertTrue(AttachmentService._looks_like_quick_identification_request("can you tell me what this is"))
        self.assertFalse(AttachmentService._looks_like_quick_identification_request("remove background"))

    def test_transient_vision_error_detection(self) -> None:
        self.assertTrue(LLMService._is_transient_vision_error("model is busy, try again"))
        self.assertTrue(LLMService._is_transient_vision_error("request timed out"))
        self.assertFalse(LLMService._is_transient_vision_error("unsupported image format"))

    def test_preferred_fast_vision_model_prefers_small_vision_profiles(self) -> None:
        original = RuntimeConfigService.list_ollama_models
        RuntimeConfigService.list_ollama_models = staticmethod(lambda force_refresh=False: ["gemma3:4b", "qwen2.5vl:7b"])
        try:
            resolved = RuntimeConfigService.get_preferred_fast_vision_model(active_provider="ollama", active_model="qwen2.5:3b")
            self.assertEqual(resolved, "gemma3:4b")
        finally:
            RuntimeConfigService.list_ollama_models = original


if __name__ == "__main__":
    unittest.main()
