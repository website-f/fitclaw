import base64
import httpx
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()
GEMINI_TEXT_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite")
GEMINI_VISION_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")


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
                    reply, resolved_model = LLMService._call_gemini(messages, settings.gemini_model)
                    return reply, f"gemini:{resolved_model}"
                except Exception as exc:
                    errors.append(f"Gemini failed: {exc}")
        elif provider == "gemini":
            try:
                reply, resolved_model = LLMService._call_gemini(messages, model)
                return reply, f"gemini:{resolved_model}"
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
                reply, resolved_model = LLMService._call_gemini_vision(
                    prompt_messages,
                    prompt_text,
                    encoded_images,
                    preferred_gemini_model,
                )
                return reply, f"gemini:{resolved_model}"
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
                    reply, resolved_model = LLMService._call_gemini_vision(
                        prompt_messages,
                        prompt_text,
                        encoded_images,
                        preferred_gemini_model,
                    )
                    return reply, f"gemini:{resolved_model}"
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
        if response.status_code == 404:
            return LLMService._call_ollama_generate(messages, model)

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
        if response.status_code == 404:
            return LLMService._call_ollama_generate(
                prior_messages,
                model,
                images=[item["data"] for item in encoded_images],
            )

        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise LLMServiceError("Ollama vision returned an empty response.")
        return content

    @staticmethod
    def _call_ollama_generate(
        messages: list[dict[str, str]],
        model: str,
        images: list[str] | None = None,
    ) -> str:
        transcript = LLMService._build_transcript(messages)
        payload = {
            "model": model,
            "prompt": transcript,
            "stream": False,
            "options": {"temperature": settings.llm_temperature},
        }
        if images:
            payload["images"] = images

        response = httpx.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=settings.ollama_request_timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = str(data.get("response", "")).strip()
        if not content:
            raise LLMServiceError("Ollama generate returned an empty response.")
        return content

    @staticmethod
    def _call_gemini(messages: list[dict[str, str]], model: str) -> tuple[str, str]:
        transcript = "\n".join(f"{item['role'].upper()}: {item['content']}" for item in messages)
        payload = {
            "contents": [{"parts": [{"text": transcript}]}],
            "generationConfig": {"temperature": settings.llm_temperature},
        }
        errors: list[str] = []
        for candidate_model in LLMService._candidate_gemini_models(model, vision=False):
            try:
                response = httpx.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent",
                    params={"key": settings.gemini_api_key},
                    json=payload,
                    timeout=60,
                )
                response.raise_for_status()
                content = LLMService._extract_gemini_text(response.json())
                return content, candidate_model
            except Exception as exc:
                errors.append(f"{candidate_model}: {exc}")
        raise LLMServiceError(" ; ".join(errors) or "Gemini returned no usable models.")

    @staticmethod
    def _call_gemini_vision(
        prompt_messages: list[dict[str, str]],
        prompt_text: str,
        encoded_images: list[dict[str, str]],
        model: str,
    ) -> tuple[str, str]:
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
        errors: list[str] = []
        for candidate_model in LLMService._candidate_gemini_models(model, vision=True):
            try:
                response = httpx.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent",
                    params={"key": settings.gemini_api_key},
                    json=payload,
                    timeout=120,
                )
                response.raise_for_status()
                content = LLMService._extract_gemini_text(response.json())
                return content, candidate_model
            except Exception as exc:
                errors.append(f"{candidate_model}: {exc}")
        raise LLMServiceError(" ; ".join(errors) or "Gemini vision returned no usable models.")

    @staticmethod
    def _candidate_gemini_models(preferred_model: str, vision: bool) -> list[str]:
        configured = [preferred_model.strip()]
        if vision:
            configured.extend([settings.gemini_vision_model, settings.gemini_model])
            fallback_pool = GEMINI_VISION_FALLBACK_MODELS
        else:
            configured.extend([settings.gemini_model])
            fallback_pool = GEMINI_TEXT_FALLBACK_MODELS

        seen: set[str] = set()
        candidates: list[str] = []
        for item in [*configured, *fallback_pool]:
            model_name = item.strip()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            candidates.append(model_name)
        return candidates

    @staticmethod
    def _extract_gemini_text(data: dict) -> str:
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
    def _build_transcript(messages: list[dict[str, str]]) -> str:
        return "\n".join(f"{item['role'].upper()}: {item['content']}" for item in messages if item.get("content"))
