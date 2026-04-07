import httpx

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
