from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.setting import AppSetting

settings = get_settings()
OLLAMA_CLIENT = httpx.Client(
    timeout=15,
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
)


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    label: str
    summary: str
    family: str
    role_group: str
    role_group_label: str
    roles: tuple[str, ...]
    modality: str = "text"
    source: str = "local"
    speed: str = "balanced"
    resource_tier: str = "medium"
    cloud_auth_required: bool = False
    context_length: int | None = None
    max_output_tokens: int | None = None
    priority: int = 500

    def to_option(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "label": self.label,
            "summary": self.summary,
            "family": self.family,
            "role_group": self.role_group,
            "role_group_label": self.role_group_label,
            "roles": list(self.roles),
            "modality": self.modality,
            "source": self.source,
            "speed": self.speed,
            "resource_tier": self.resource_tier,
            "cloud_auth_required": self.cloud_auth_required,
        }


class RuntimeConfigService:
    ACTIVE_LLM_KEY = "active_llm"
    MODEL_PROFILES: tuple[ModelProfile, ...] = (
        ModelProfile(
            provider="ollama",
            model="qwen2.5:3b",
            label="Qwen 2.5 3B",
            summary="Fast local daily chat for reports, status checks, and lightweight ops reasoning.",
            family="Qwen",
            role_group="daily",
            role_group_label="Daily And Reports",
            roles=("daily", "chat", "reports", "files"),
            speed="fast",
            resource_tier="small",
            context_length=6144,
            max_output_tokens=640,
            priority=10,
        ),
        ModelProfile(
            provider="ollama",
            model="gemma2:2b",
            label="Gemma 2 2B",
            summary="Smallest local fallback for quick status replies on low-resource VPS setups.",
            family="Gemma",
            role_group="daily",
            role_group_label="Daily And Reports",
            roles=("daily", "fallback", "chat"),
            speed="fast",
            resource_tier="small",
            context_length=4096,
            max_output_tokens=512,
            priority=20,
        ),
        ModelProfile(
            provider="ollama",
            model="deepseek-r1:1.5b",
            label="DeepSeek R1 1.5B",
            summary="Small reasoning-focused local model for step-by-step planning and compact analysis.",
            family="DeepSeek",
            role_group="reasoning",
            role_group_label="Reasoning And Planning",
            roles=("reasoning", "planning", "analysis"),
            speed="balanced",
            resource_tier="small",
            context_length=8192,
            max_output_tokens=768,
            priority=30,
        ),
        ModelProfile(
            provider="ollama",
            model="qwen2.5-coder:7b",
            label="Qwen 2.5 Coder 7B",
            summary="Light local coding model for scripts, APIs, and medium-size code edits.",
            family="Qwen Coder",
            role_group="coding",
            role_group_label="Coding And Websites",
            roles=("coding", "frontend", "backend", "websites", "files"),
            speed="balanced",
            resource_tier="medium",
            context_length=16384,
            max_output_tokens=1024,
            priority=40,
        ),
        ModelProfile(
            provider="ollama",
            model="qwen3-coder:30b",
            label="Qwen 3 Coder 30B",
            summary="Best local website and app builder in this stack, but heavier on RAM and slower to switch.",
            family="Qwen Coder",
            role_group="coding",
            role_group_label="Coding And Websites",
            roles=("coding", "frontend", "backend", "websites", "refactor"),
            speed="quality",
            resource_tier="large",
            context_length=24576,
            max_output_tokens=1280,
            priority=50,
        ),
        ModelProfile(
            provider="ollama",
            model="devstral",
            label="Devstral",
            summary="Agent-style coding model that is strong at larger engineering tasks and repo-wide changes.",
            family="Devstral",
            role_group="coding",
            role_group_label="Coding And Websites",
            roles=("coding", "agents", "repo-work", "websites"),
            speed="quality",
            resource_tier="large",
            context_length=16384,
            max_output_tokens=1280,
            priority=60,
        ),
        ModelProfile(
            provider="ollama",
            model="gemma3:4b",
            label="Gemma 3 4B",
            summary="Fast local multimodal model for screenshots, image verification, and light UI review.",
            family="Gemma",
            role_group="vision",
            role_group_label="Vision And Files",
            roles=("vision", "screenshots", "images", "files", "ui-review"),
            modality="vision",
            speed="balanced",
            resource_tier="medium",
            context_length=6144,
            max_output_tokens=512,
            priority=70,
        ),
        ModelProfile(
            provider="ollama",
            model="gemma3:12b",
            label="Gemma 3 12B",
            summary="Stronger multimodal local model for UI critique, screenshots, and richer image analysis.",
            family="Gemma",
            role_group="vision",
            role_group_label="Vision And Files",
            roles=("vision", "screenshots", "images", "ui-review", "files"),
            modality="vision",
            speed="quality",
            resource_tier="large",
            context_length=8192,
            max_output_tokens=768,
            priority=80,
        ),
        ModelProfile(
            provider="ollama",
            model="qwen2.5vl:7b",
            label="Qwen 2.5 VL 7B",
            summary="Local vision model for screenshots, OCR-like inspection, and image question answering.",
            family="Qwen Vision",
            role_group="vision",
            role_group_label="Vision And Files",
            roles=("vision", "screenshots", "ocr", "images"),
            modality="vision",
            speed="balanced",
            resource_tier="medium",
            context_length=8192,
            max_output_tokens=768,
            priority=90,
        ),
        ModelProfile(
            provider="ollama",
            model="kimi-k2.5:cloud",
            label="Kimi K2.5 Cloud",
            summary="Fun cloud model through Ollama Cloud. Great long-context option, but needs Ollama auth and cloud quota.",
            family="Kimi",
            role_group="cloud",
            role_group_label="Cloud And Experimental",
            roles=("cloud", "long-context", "research", "fun"),
            source="cloud",
            speed="quality",
            resource_tier="cloud",
            cloud_auth_required=True,
            priority=100,
        ),
        ModelProfile(
            provider="gemini",
            model="gemini-2.5-flash",
            label="Gemini 2.5 Flash",
            summary="Cloud fallback for hard prompts, heavy synthesis, and when local models are unavailable.",
            family="Gemini",
            role_group="cloud",
            role_group_label="Cloud And Experimental",
            roles=("cloud", "analysis", "fallback"),
            source="cloud",
            speed="balanced",
            resource_tier="cloud",
            priority=110,
        ),
    )
    PROFILE_INDEX = {(item.provider, item.model): item for item in MODEL_PROFILES}
    RECOMMENDED_OLLAMA_MODELS = tuple(item.model for item in MODEL_PROFILES if item.provider == "ollama")
    RECOMMENDED_GEMINI_MODELS = tuple(item.model for item in MODEL_PROFILES if item.provider == "gemini")
    _ollama_model_cache: dict[str, object] = {"models": [], "expires_at": 0.0}

    @staticmethod
    def get_default_llm() -> dict[str, str]:
        return {"provider": "ollama", "model": settings.ollama_model}

    @staticmethod
    def get_model_profile(provider: str, model: str) -> ModelProfile | None:
        return RuntimeConfigService.PROFILE_INDEX.get((provider.strip().lower(), model.strip()))

    @staticmethod
    def get_active_llm(db: Session) -> dict[str, str]:
        record = db.scalar(select(AppSetting).where(AppSetting.key == RuntimeConfigService.ACTIVE_LLM_KEY))
        if record and record.value_json.get("provider") and record.value_json.get("model"):
            return {
                "provider": str(record.value_json["provider"]),
                "model": str(record.value_json["model"]),
            }
        return RuntimeConfigService.get_default_llm()

    @staticmethod
    def set_active_llm(db: Session, provider: str, model: str) -> dict[str, str]:
        record = db.scalar(select(AppSetting).where(AppSetting.key == RuntimeConfigService.ACTIVE_LLM_KEY))
        payload = {"provider": provider.strip(), "model": model.strip()}

        if record is None:
            record = AppSetting(key=RuntimeConfigService.ACTIVE_LLM_KEY, value_json=payload)
            db.add(record)
        else:
            record.value_json = payload

        db.commit()
        return payload

    @staticmethod
    def list_ollama_models(force_refresh: bool = False) -> list[str]:
        import time

        cache_expires_at = float(RuntimeConfigService._ollama_model_cache.get("expires_at", 0.0))
        if not force_refresh and cache_expires_at > time.monotonic():
            cached = RuntimeConfigService._ollama_model_cache.get("models", [])
            return list(cached) if isinstance(cached, list) else []

        api_base = settings.ollama_base_url.rstrip("/")
        try:
            response = OLLAMA_CLIENT.get(f"{api_base}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            names = [item.get("name", "").strip() for item in models if item.get("name")]
            resolved = sorted(set(names))
            RuntimeConfigService._store_ollama_model_cache(resolved)
            return resolved
        except Exception:
            pass

        try:
            response = OLLAMA_CLIENT.get(f"{api_base}/v1/models")
            response.raise_for_status()
            data = response.json()
            models = data.get("data", [])
            names = [item.get("id", "").strip() for item in models if item.get("id")]
            resolved = sorted(set(names))
            RuntimeConfigService._store_ollama_model_cache(resolved)
            return resolved
        except Exception:
            return []

    @staticmethod
    def pull_ollama_model(model: str) -> None:
        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/pull",
            json={"name": model, "stream": False},
            timeout=max(settings.ollama_request_timeout, 1800),
        )
        response.raise_for_status()
        RuntimeConfigService.list_ollama_models(force_refresh=True)

    @staticmethod
    def build_ollama_options(model: str, vision: bool = False) -> dict[str, object]:
        profile = RuntimeConfigService.get_model_profile("ollama", model)
        default_context = settings.ollama_vision_context_length if vision else settings.ollama_context_length
        default_output = settings.ollama_vision_num_predict if vision else settings.ollama_num_predict

        context_length = profile.context_length if profile and profile.context_length else default_context
        max_output_tokens = profile.max_output_tokens if profile and profile.max_output_tokens else default_output

        payload: dict[str, object] = {"temperature": settings.llm_temperature}
        if context_length > 0:
            payload["num_ctx"] = context_length
        if max_output_tokens > 0:
            payload["num_predict"] = max_output_tokens
        return payload

    @staticmethod
    def prewarm_ollama_model(model: str, vision: bool = False) -> None:
        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": "",
                "stream": False,
                "keep_alive": settings.ollama_keep_alive,
                "options": RuntimeConfigService.build_ollama_options(model, vision=vision),
            },
            timeout=max(settings.ollama_request_timeout, 180),
        )
        response.raise_for_status()

    @staticmethod
    def unload_ollama_model(model: str) -> None:
        response = OLLAMA_CLIENT.post(
            f"{settings.ollama_base_url.rstrip('/')}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=max(settings.ollama_request_timeout, 60),
        )
        if response.status_code not in {200, 404}:
            response.raise_for_status()

    @staticmethod
    def get_configured_ollama_models() -> list[str]:
        values = [
            settings.ollama_model,
            *settings.ollama_model_list,
            *settings.ollama_optional_model_list,
            settings.ollama_vision_model,
            *settings.ollama_vision_model_list,
        ]
        return RuntimeConfigService._merge_unique(values)

    @staticmethod
    def get_preferred_fast_vision_model(active_provider: str | None = None, active_model: str | None = None) -> str:
        active_provider_normalized = str(active_provider or "").strip().lower()
        active_model_name = str(active_model or "").strip()
        if active_provider_normalized == "ollama" and active_model_name:
            profile = RuntimeConfigService.get_model_profile("ollama", active_model_name)
            if profile and profile.modality == "vision" and profile.resource_tier in {"small", "medium"}:
                return active_model_name

        installed = set(RuntimeConfigService.list_ollama_models())
        preferred_candidates = [
            settings.ollama_vision_model,
            *settings.ollama_vision_model_list,
            "gemma3:4b",
            "qwen2.5vl:7b",
            "gemma3:12b",
        ]
        for model_name in RuntimeConfigService._merge_unique(preferred_candidates):
            profile = RuntimeConfigService.get_model_profile("ollama", model_name)
            if profile and profile.modality == "vision" and profile.resource_tier in {"small", "medium"}:
                if not installed or model_name in installed:
                    return model_name

        return settings.ollama_vision_model.strip() or settings.ollama_model.strip()

    @staticmethod
    def get_available_model_refs(active_provider: str | None = None, active_model: str | None = None) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        installed = RuntimeConfigService.list_ollama_models()
        for model_name in installed:
            results.append({"provider": "ollama", "model": model_name})

        if active_provider == "ollama" and active_model and active_model not in installed:
            results.insert(0, {"provider": "ollama", "model": active_model})

        if settings.gemini_enabled:
            gemini_models = RuntimeConfigService._merge_unique([settings.gemini_model, settings.gemini_vision_model])
            for model_name in gemini_models:
                results.append({"provider": "gemini", "model": model_name})
        return results

    @staticmethod
    def build_model_catalog(active_provider: str, active_model: str) -> dict[str, list[dict[str, object]]]:
        installed = set(RuntimeConfigService.list_ollama_models())
        configured = set(RuntimeConfigService.get_configured_ollama_models())
        ollama_candidates = RuntimeConfigService._merge_unique(
            [
                active_model if active_provider == "ollama" else "",
                *sorted(installed),
                *[
                    model_name
                    for model_name in RuntimeConfigService.get_configured_ollama_models()
                    if model_name in installed or model_name == active_model
                ],
            ]
        )
        gemini_candidates = RuntimeConfigService._merge_unique(
            [
                active_model if active_provider == "gemini" else "",
                settings.gemini_model,
                settings.gemini_vision_model,
                *RuntimeConfigService.RECOMMENDED_GEMINI_MODELS,
            ]
        )

        ollama_choices = [
            RuntimeConfigService._build_option(
                provider="ollama",
                model_name=model_name,
                installed=model_name in installed,
                configured=model_name in configured,
                recommended=model_name in RuntimeConfigService.RECOMMENDED_OLLAMA_MODELS,
                active=active_provider == "ollama" and active_model == model_name,
            )
            for model_name in ollama_candidates
        ]
        gemini_choices = [
            RuntimeConfigService._build_option(
                provider="gemini",
                model_name=model_name,
                installed=settings.gemini_enabled,
                configured=model_name in {settings.gemini_model, settings.gemini_vision_model},
                recommended=model_name in RuntimeConfigService.RECOMMENDED_GEMINI_MODELS,
                active=active_provider == "gemini" and active_model == model_name,
            )
            for model_name in gemini_candidates
            if settings.gemini_enabled and model_name
        ]

        ollama_choices.sort(key=RuntimeConfigService._option_sort_key)
        gemini_choices.sort(key=RuntimeConfigService._option_sort_key)
        return {"ollama_choices": ollama_choices, "gemini_choices": gemini_choices}

    @staticmethod
    def validate_provider_model(provider: str, model: str) -> tuple[str, str]:
        provider_name = provider.strip().lower()
        model_name = model.strip()
        if provider_name not in {"ollama", "gemini"}:
            raise ValueError("Provider must be either 'ollama' or 'gemini'.")
        if not model_name:
            raise ValueError("Model name cannot be empty.")
        if provider_name == "gemini" and not settings.gemini_enabled:
            raise ValueError("Gemini is not enabled. Set GEMINI_API_KEY first.")
        return provider_name, model_name

    @staticmethod
    def _build_option(
        provider: str,
        model_name: str,
        installed: bool,
        configured: bool,
        recommended: bool,
        active: bool,
    ) -> dict[str, object]:
        profile = RuntimeConfigService.PROFILE_INDEX.get((provider, model_name))
        if profile is None:
            profile = RuntimeConfigService._infer_profile(provider, model_name)
        payload = profile.to_option()
        payload.update(
            {
                "installed": installed,
                "configured": configured,
                "recommended": recommended,
                "active": active,
            }
        )
        return payload

    @staticmethod
    def _infer_profile(provider: str, model_name: str) -> ModelProfile:
        lowered = model_name.lower().strip()
        role_group = "general"
        role_group_label = "General"
        roles = ("chat",)
        modality = "text"
        family = model_name.split(":")[0].replace("-", " ").title()
        source = "cloud" if ":cloud" in lowered or provider == "gemini" else "local"
        speed = "balanced"
        resource_tier = "medium"
        cloud_auth_required = ":cloud" in lowered

        if any(token in lowered for token in ("coder", "devstral")):
            role_group = "coding"
            role_group_label = "Coding And Websites"
            roles = ("coding", "websites", "files")
            speed = "quality"
        elif any(token in lowered for token in ("vision", "vl", "gemma3", "llava", "minicpm-v")):
            role_group = "vision"
            role_group_label = "Vision And Files"
            roles = ("vision", "images", "files")
            modality = "vision"
        elif any(token in lowered for token in ("r1", "reason", "think")):
            role_group = "reasoning"
            role_group_label = "Reasoning And Planning"
            roles = ("reasoning", "analysis", "planning")
        elif source == "cloud":
            role_group = "cloud"
            role_group_label = "Cloud And Experimental"
            roles = ("cloud", "analysis")
        else:
            role_group = "daily"
            role_group_label = "Daily And Reports"
            roles = ("daily", "chat", "reports")
            speed = "fast"

        return ModelProfile(
            provider=provider,
            model=model_name,
            label=model_name,
            summary="Available through the configured provider.",
            family=family,
            role_group=role_group,
            role_group_label=role_group_label,
            roles=roles,
            modality=modality,
            source=source,
            speed=speed,
            resource_tier=resource_tier,
            cloud_auth_required=cloud_auth_required,
            priority=900,
        )

    @staticmethod
    def _option_sort_key(item: dict[str, object]) -> tuple[int, int, int, str]:
        profile = RuntimeConfigService.PROFILE_INDEX.get((str(item["provider"]), str(item["model"])))
        priority = profile.priority if profile else 999
        active_rank = 0 if item.get("active") else 1
        installed_rank = 0 if item.get("installed") else 1
        return (active_rank, priority, installed_rank, str(item["model"]))

    @staticmethod
    def _store_ollama_model_cache(models: list[str]) -> None:
        import time

        RuntimeConfigService._ollama_model_cache = {
            "models": list(models),
            "expires_at": time.monotonic() + 30.0,
        }

    @staticmethod
    def _merge_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for item in values:
            model_name = str(item).strip()
            if not model_name or model_name in seen:
                continue
            seen.add(model_name)
            results.append(model_name)
        return results
