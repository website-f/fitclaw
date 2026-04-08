import base64
import httpx
from pathlib import Path

from app.core.config import get_settings
from app.services.runtime_config_service import RuntimeConfigService

settings = get_settings()
OLLAMA_CLIENT = httpx.Client(
    timeout=settings.ollama_request_timeout,
    limits=httpx.Limits(max_keepalive_connections=8, max_connections=32),
)
GEMINI_CLIENT = httpx.Client(
    timeout=120,
    limits=httpx.Limits(max_keepalive_connections=8, max_connections=32),
)
TEXT_CONTEXT_CHAR_BUDGET = 9000
VISION_CONTEXT_CHAR_BUDGET = 6000
MAX_OLDER_MESSAGE_CHARS = 1000
MAX_LATEST_MESSAGE_CHARS = 4200
GEMINI_TEXT_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite")
GEMINI_VISION_FALLBACK_MODELS = ("gemini-2.5-flash", "gemini-2.0-flash")
COMPLEXITY_KEYWORDS = (
    "analyze",
    "analysis",
    "compare",
    "comparison",
    "reason step by step",
    "architecture",
    "refactor",
    "debug",
    "root cause",
    "research",
    "strategy",
    "proposal",
    "comprehensive",
    "thorough",
    "synthesize",
    "brainstorm",
    "tradeoff",
    "multiple files",
    "large file",
    "deep analysis",
    "deep dive",
)


class LLMServiceError(RuntimeError):
    pass


class LLMService:
    @staticmethod
    def generate_reply(
        messages: list[dict[str, str]],
        active_provider: str | None = None,
        active_model: str | None = None,
    ) -> tuple[str, str]:
        prepared_messages = LLMService._prepare_messages(messages, max_total_chars=TEXT_CONTEXT_CHAR_BUDGET)
        errors: list[str] = []
        provider = (active_provider or "ollama").strip().lower()
        model = (active_model or settings.ollama_model).strip()
        should_escalate_to_gemini = (
            provider == "ollama"
            and settings.gemini_enabled
            and LLMService._should_prefer_gemini(prepared_messages)
        )

        if should_escalate_to_gemini:
            try:
                reply, resolved_model = LLMService._call_gemini(prepared_messages, settings.gemini_model)
                return reply, f"gemini:{resolved_model}"
            except Exception as exc:
                errors.append(f"Gemini escalation failed: {exc}")

            try:
                reply, resolved_model = LLMService._call_ollama_with_fallbacks(prepared_messages, model)
                return reply, f"ollama:{resolved_model}"
            except Exception as exc:
                errors.append(f"Ollama fallback failed: {exc}")
        elif provider == "ollama":
            try:
                reply, resolved_model = LLMService._call_ollama_with_fallbacks(prepared_messages, model)
                return reply, f"ollama:{resolved_model}"
            except Exception as exc:
                errors.append(f"Ollama failed: {exc}")
        elif provider == "gemini":
            try:
                reply, resolved_model = LLMService._call_gemini(prepared_messages, model)
                return reply, f"gemini:{resolved_model}"
            except Exception as exc:
                errors.append(f"Gemini failed: {exc}")

            try:
                reply, resolved_model = LLMService._call_ollama_with_fallbacks(prepared_messages, settings.ollama_model)
                return reply, f"ollama:{resolved_model}"
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
        prepared_messages = LLMService._prepare_messages(prompt_messages, max_total_chars=VISION_CONTEXT_CHAR_BUDGET)
        provider = (active_provider or "ollama").strip().lower()
        errors: list[str] = []
        encoded_images = [
            {
                "data": base64.b64encode(Path(asset.stored_path).read_bytes()).decode("ascii"),
                "mime_type": asset.mime_type,
            }
            for asset in image_assets
        ]

        preferred_ollama_model = LLMService._resolve_preferred_vision_model(
            provider=provider,
            active_model=active_model,
        )
        preferred_gemini_model = (
            active_model.strip()
            if provider == "gemini" and (active_model or "").strip()
            else settings.gemini_vision_model or settings.gemini_model
        )

        if provider == "gemini" and settings.gemini_enabled:
            try:
                reply, resolved_model = LLMService._call_gemini_vision(
                    prepared_messages,
                    prompt_text,
                    encoded_images,
                    preferred_gemini_model,
                )
                return reply, f"gemini:{resolved_model}"
            except Exception as exc:
                errors.append(f"Gemini vision failed: {exc}")

            try:
                reply, resolved_model = LLMService._call_ollama_vision_with_fallbacks(
                    prepared_messages,
                    prompt_text,
                    encoded_images,
                    preferred_ollama_model,
                )
                return reply, f"ollama:{resolved_model}"
            except Exception as exc:
                errors.append(f"Ollama vision failed: {exc}")
        else:
            try:
                reply, resolved_model = LLMService._call_ollama_vision_with_fallbacks(
                    prepared_messages,
                    prompt_text,
                    encoded_images,
                    preferred_ollama_model,
                )
                return reply, f"ollama:{resolved_model}"
            except Exception as exc:
                errors.append(f"Ollama vision failed: {exc}")

            if settings.gemini_enabled:
                try:
                    reply, resolved_model = LLMService._call_gemini_vision(
                        prepared_messages,
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
            "keep_alive": settings.ollama_keep_alive,
            "options": RuntimeConfigService.build_ollama_options(model, vision=False),
        }
        errors: list[str] = []

        try:
            response = OLLAMA_CLIENT.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json=payload,
            )
            if response.status_code != 404:
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "").strip()
                if not content:
                    raise LLMServiceError("Ollama returned an empty response.")
                return content
            not_found_reason = LLMService._extract_ollama_not_found_reason(response)
            if not_found_reason:
                raise LLMServiceError(not_found_reason)
            errors.append("POST /api/chat returned 404")
        except Exception as exc:
            errors.append(f"/api/chat failed: {exc}")

        try:
            return LLMService._call_ollama_generate(messages, model)
        except Exception as exc:
            errors.append(f"/api/generate failed: {exc}")

        try:
            return LLMService._call_ollama_openai_chat(messages, model)
        except Exception as exc:
            errors.append(f"/v1/chat/completions failed: {exc}")

        raise LLMServiceError(" ; ".join(errors))

    @staticmethod
    def _call_ollama_with_fallbacks(messages: list[dict[str, str]], preferred_model: str) -> tuple[str, str]:
        errors: list[str] = []
        for candidate_model in LLMService._candidate_ollama_models(preferred_model, vision=False):
            try:
                reply = LLMService._call_ollama(messages, candidate_model)
                return reply, candidate_model
            except Exception as exc:
                errors.append(f"{candidate_model}: {exc}")
        raise LLMServiceError(" ; ".join(errors) or "No Ollama text models are configured.")

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
            "keep_alive": settings.ollama_keep_alive,
            "options": RuntimeConfigService.build_ollama_options(model, vision=True),
        }
        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/chat",
            json=payload,
        )
        if response.status_code == 404:
            not_found_reason = LLMService._extract_ollama_not_found_reason(response)
            if not_found_reason:
                raise LLMServiceError(not_found_reason)
            try:
                return LLMService._call_ollama_generate(
                    prior_messages,
                    model,
                    images=[item["data"] for item in encoded_images],
                )
            except Exception as exc:
                raise LLMServiceError(f"Ollama vision endpoints are unavailable: {exc}") from exc

        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "").strip()
        if not content:
            raise LLMServiceError("Ollama vision returned an empty response.")
        return content

    @staticmethod
    def _call_ollama_vision_with_fallbacks(
        prompt_messages: list[dict[str, str]],
        prompt_text: str,
        encoded_images: list[dict[str, str]],
        preferred_model: str,
    ) -> tuple[str, str]:
        errors: list[str] = []
        for candidate_model in LLMService._candidate_ollama_models(preferred_model, vision=True):
            try:
                reply = LLMService._call_ollama_vision(
                    prompt_messages,
                    prompt_text,
                    encoded_images,
                    candidate_model,
                )
                return reply, candidate_model
            except Exception as exc:
                errors.append(f"{candidate_model}: {exc}")
        raise LLMServiceError(" ; ".join(errors) or "No Ollama vision models are configured.")

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
            "keep_alive": settings.ollama_keep_alive,
            "options": RuntimeConfigService.build_ollama_options(model, vision=bool(images)),
        }
        if images:
            payload["images"] = images

        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json=payload,
        )
        not_found_reason = LLMService._extract_ollama_not_found_reason(response)
        if not_found_reason:
            raise LLMServiceError(not_found_reason)
        response.raise_for_status()
        data = response.json()
        content = str(data.get("response", "")).strip()
        if not content:
            raise LLMServiceError("Ollama generate returned an empty response.")
        return content

    @staticmethod
    def _call_ollama_openai_chat(messages: list[dict[str, str]], model: str) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "keep_alive": settings.ollama_keep_alive,
            "temperature": settings.llm_temperature,
        }
        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/v1/chat/completions",
            json=payload,
        )
        not_found_reason = LLMService._extract_ollama_not_found_reason(response)
        if not_found_reason:
            raise LLMServiceError(not_found_reason)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            raise LLMServiceError("Ollama OpenAI-compatible endpoint returned no choices.")

        message = choices[0].get("message", {})
        content = str(message.get("content", "")).strip()
        if not content:
            raise LLMServiceError("Ollama OpenAI-compatible endpoint returned an empty response.")
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
                response = GEMINI_CLIENT.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent",
                    params={"key": settings.gemini_api_key},
                    json=payload,
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
                response = GEMINI_CLIENT.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent",
                    params={"key": settings.gemini_api_key},
                    json=payload,
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
    def _candidate_ollama_models(preferred_model: str, vision: bool) -> list[str]:
        configured = [preferred_model.strip()]
        if vision:
            configured.extend([settings.ollama_vision_model, *settings.ollama_vision_model_list])
        else:
            configured.extend([settings.ollama_model, *settings.ollama_model_list, *settings.ollama_optional_model_list])

        seen: set[str] = set()
        candidates: list[str] = []
        for item in configured:
            model_name = item.strip()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            candidates.append(model_name)
        return candidates

    @staticmethod
    def _resolve_preferred_vision_model(provider: str, active_model: str | None) -> str:
        active_name = (active_model or "").strip()
        if provider == "ollama" and active_name and LLMService._looks_like_vision_model(active_name):
            return active_name
        if settings.ollama_vision_model.strip():
            return settings.ollama_vision_model.strip()
        if settings.ollama_vision_model_list:
            return settings.ollama_vision_model_list[0]
        return settings.ollama_model

    @staticmethod
    def _looks_like_vision_model(model_name: str) -> bool:
        lowered = model_name.lower().strip()
        if not lowered:
            return False
        if lowered in {item.lower() for item in settings.ollama_vision_model_list}:
            return True
        if lowered == settings.ollama_vision_model.lower().strip():
            return True
        return any(token in lowered for token in ("vision", "vl", "gemma3", "llava", "minicpm-v"))

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

    @staticmethod
    def _prepare_messages(messages: list[dict[str, str]], max_total_chars: int) -> list[dict[str, str]]:
        if not messages:
            return messages

        system_message = None
        non_system_messages: list[dict[str, str]] = []
        for item in messages:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            if role == "system" and system_message is None:
                system_message = {"role": role, "content": content[:MAX_LATEST_MESSAGE_CHARS]}
            else:
                non_system_messages.append({"role": role, "content": content})

        prepared_reversed: list[dict[str, str]] = []
        total_chars = len(system_message["content"]) if system_message else 0
        newest_added = False
        for item in reversed(non_system_messages):
            per_message_cap = MAX_LATEST_MESSAGE_CHARS if not newest_added else MAX_OLDER_MESSAGE_CHARS
            remaining_budget = max_total_chars - total_chars
            if remaining_budget <= 0:
                break
            allowed_chars = min(per_message_cap, remaining_budget)
            if allowed_chars <= 0:
                break
            content = item["content"][:allowed_chars].strip()
            if not content:
                continue
            prepared_reversed.append({"role": item["role"], "content": content})
            total_chars += len(content)
            newest_added = True

        prepared = list(reversed(prepared_reversed))
        if system_message is not None:
            prepared.insert(0, system_message)
        return prepared or messages[-1:]

    @staticmethod
    def _should_prefer_gemini(messages: list[dict[str, str]]) -> bool:
        latest_user_message = ""
        for item in reversed(messages):
            if item.get("role") == "user" and item.get("content"):
                latest_user_message = str(item["content"]).strip().lower()
                break

        if not latest_user_message:
            return False

        if len(latest_user_message) >= 2400:
            return True
        if latest_user_message.count("\n") >= 24:
            return True
        if any(keyword in latest_user_message for keyword in ("deep analysis", "deep dive", "thorough research", "comprehensive report")):
            return True
        return len(latest_user_message) >= 900 and any(keyword in latest_user_message for keyword in COMPLEXITY_KEYWORDS)

    @staticmethod
    def _extract_ollama_not_found_reason(response: httpx.Response) -> str | None:
        if response.status_code != 404:
            return None
        try:
            data = response.json()
        except Exception:
            return None

        raw_message = data.get("error") or data.get("message") or ""
        message = str(raw_message).strip()
        if "model" in message.lower() and "not found" in message.lower():
            return (
                f"Ollama model is not ready yet: {message}. "
                "It is usually still being pulled, or the configured model name does not exist on that server."
            )
        return None
