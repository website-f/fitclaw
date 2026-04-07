import base64
import httpx
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class LLMServiceError(RuntimeError):
    pass


class LLMService:
    @staticmethod
    def generate_reply(
        messages: list[dict[str, str]],
        active_provider: str | None = None,
        active_model: str | None = None,
    ) -> tuple[str, str]:
        errors: list[str] = []
        provider = (active_provider or "ollama").strip().lower()
        model = (active_model or settings.ollama_model).strip()

        if provider == "ollama":
            try:
                reply = LLMService._call_ollama(messages, model)
                return reply, f"ollama:{model}"
            except Exception as exc:
                errors.append(f"Ollama failed: {exc}")

            if settings.gemini_enabled:
                try:
                    reply = LLMService._call_gemini(messages, settings.gemini_model)
                    return reply, f"gemini:{settings.gemini_model}"
                except Exception as exc:
                    errors.append(f"Gemini failed: {exc}")
        elif provider == "gemini":
            try:
                reply = LLMService._call_gemini(messages, model)
                return reply, f"gemini:{model}"
            except Exception as exc:
                errors.append(f"Gemini failed: {exc}")

            try:
                reply = LLMService._call_ollama(messages, settings.ollama_model)
                return reply, f"ollama:{settings.ollama_model}"
            except Exception as exc:
                errors.append(f"Ollama fallback failed: {exc}")

        raise LLMServiceError(" | ".join(errors) or "No LLM providers are configured.")

    @staticmethod
    def generate_vision_reply(
        prompt_messages: list[dict[str, str]],
        prompt_text: str,
        image_assets: list,
        active_provider: str | None = None,
        active_model: str | None = None,
    ) -> tuple[str, str]:
        provider = (active_provider or "ollama").strip().lower()
        errors: list[str] = []
        encoded_images = [
            {
                "data": base64.b64encode(Path(asset.stored_path).read_bytes()).decode("ascii"),
                "mime_type": asset.mime_type,
            }
            for asset in image_assets
        ]

        preferred_ollama_model = (
            active_model.strip()
            if provider == "ollama" and (active_model or "").strip()
            else settings.ollama_vision_model or settings.ollama_model
        )
        preferred_gemini_model = (
            active_model.strip()
            if provider == "gemini" and (active_model or "").strip()
            else settings.gemini_vision_model or settings.gemini_model
        )

        if provider == "gemini" and settings.gemini_enabled:
            try:
                reply = LLMService._call_gemini_vision(prompt_messages, prompt_text, encoded_images, preferred_gemini_model)
                return reply, f"gemini:{preferred_gemini_model}"
            except Exception as exc:
                errors.append(f"Gemini vision failed: {exc}")

            try:
                reply = LLMService._call_ollama_vision(prompt_messages, prompt_text, encoded_images, preferred_ollama_model)
                return reply, f"ollama:{preferred_ollama_model}"
            except Exception as exc:
                errors.append(f"Ollama vision failed: {exc}")
        else:
            try:
                reply = LLMService._call_ollama_vision(prompt_messages, prompt_text, encoded_images, preferred_ollama_model)
                return reply, f"ollama:{preferred_ollama_model}"
            except Exception as exc:
                errors.append(f"Ollama vision failed: {exc}")

            if settings.gemini_enabled:
                try:
                    reply = LLMService._call_gemini_vision(prompt_messages, prompt_text, encoded_images, preferred_gemini_model)
                    return reply, f"gemini:{preferred_gemini_model}"
                except Exception as exc:
                    errors.append(f"Gemini vision failed: {exc}")

        raise LLMServiceError(" | ".join(errors) or "No vision providers are configured.")

    @staticmethod
    def _call_ollama(messages: list[dict[str, str]], model: str) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": settings.llm_temperature},
        }
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=settings.ollama_request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise LLMServiceError("Ollama returned an empty response.")
        return content

    @staticmethod
    def _call_ollama_vision(
        prompt_messages: list[dict[str, str]],
        prompt_text: str,
        encoded_images: list[dict[str, str]],
        model: str,
    ) -> str:
        prior_messages = [{"role": item["role"], "content": item["content"]} for item in prompt_messages[:-1] if item.get("content")]
        prior_messages.append(
            {
                "role": "user",
                "content": prompt_text,
                "images": [item["data"] for item in encoded_images],
            }
        )
        payload = {
            "model": model,
            "messages": prior_messages,
            "stream": False,
            "options": {"temperature": settings.llm_temperature},
        }
        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=settings.ollama_request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise LLMServiceError("Ollama vision returned an empty response.")
        return content

    @staticmethod
    def _call_gemini(messages: list[dict[str, str]], model: str) -> str:
        transcript = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in messages)
        payload = {
            "contents": [{"parts": [{"text": transcript}]}],
            "generationConfig": {"temperature": settings.llm_temperature},
        }
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": settings.gemini_api_key},
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMServiceError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_parts = [part.get("text", "") for part in parts if part.get("text")]
        content = "\n".join(text_parts).strip()
        if not content:
            raise LLMServiceError("Gemini returned an empty response.")
        return content

    @staticmethod
    def _call_gemini_vision(
        prompt_messages: list[dict[str, str]],
        prompt_text: str,
        encoded_images: list[dict[str, str]],
        model: str,
    ) -> str:
        transcript = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in prompt_messages[:-1] if item.get("content"))
        parts = [{"text": f"{transcript}\n\nUSER: {prompt_text}".strip()}]
        for item in encoded_images:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": item["mime_type"],
                        "data": item["data"],
                    }
                }
            )
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": settings.llm_temperature},
        }
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": settings.gemini_api_key},
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise LLMServiceError("Gemini vision returned no candidates.")

        text_parts = [part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []) if part.get("text")]
        content = "\n".join(text_parts).strip()
        if not content:
            raise LLMServiceError("Gemini vision returned an empty response.")
        return content
