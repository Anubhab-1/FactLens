from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


PROVIDER_PRIORITY = ("google", "nvidia", "openai")
PROVIDER_LABELS = {
    "google": "Google Gemini",
    "nvidia": "NVIDIA",
    "openai": "OpenAI",
}
DEFAULT_MODELS = {
    "google": {
        "text": "gemini-1.5-pro",
        "vision": "gemini-1.5-flash",
    },
    "nvidia": {
        "text": "meta/llama-3.1-70b-instruct",
        "vision": "meta/llama-3.2-90b-vision-instruct",
    },
    "openai": {
        "text": "gpt-4o-mini",
        "vision": "gpt-4o-mini",
    },
}
PROVIDER_KEY_ENV = {
    "google": ("GOOGLE_API_KEY", "GEMINI_API_KEY"),
    "nvidia": ("NVIDIA_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


@dataclass(frozen=True)
class LLMDescriptor:
    purpose: str
    provider: str | None
    provider_label: str | None
    model: str | None
    status: str
    issue: str | None = None
    vision: bool = False

    def to_payload(self) -> dict:
        return {
            "purpose": self.purpose,
            "provider": self.provider,
            "provider_label": self.provider_label,
            "model": self.model,
            "status": self.status,
            "issue": self.issue,
            "vision": self.vision,
        }


def _model_env_names(purpose: str, vision: bool) -> list[str]:
    normalized_purpose = purpose.upper().replace("-", "_")
    kind = "VISION_MODEL" if vision else "TEXT_MODEL"
    return [
        f"FACTLENS_{normalized_purpose}_MODEL",
        f"FACTLENS_{kind}",
    ]


def _resolve_api_key(provider: str) -> tuple[str | None, str | None]:
    for env_name in PROVIDER_KEY_ENV.get(provider, ()):
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip(), env_name
    return None, PROVIDER_KEY_ENV.get(provider, (None,))[0]


def _resolve_model(provider: str, purpose: str, vision: bool) -> str:
    for env_name in _model_env_names(purpose, vision):
        value = os.getenv(env_name)
        if value and value.strip():
            return value.strip()
    return DEFAULT_MODELS[provider]["vision" if vision else "text"]


def _import_provider(provider: str):
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI
    if provider == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI
    raise ValueError(f"Unsupported LLM provider '{provider}'.")


def _instantiate_model(
    provider: str,
    *,
    model: str,
    api_key: str,
    temperature: float,
    max_tokens: int,
):
    chat_model_cls = _import_provider(provider)
    if provider == "google":
        return chat_model_cls(
            model=model,
            google_api_key=api_key,
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
    if provider == "nvidia":
        return chat_model_cls(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    if provider == "openai":
        return chat_model_cls(
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    raise ValueError(f"Unsupported LLM provider '{provider}'.")


def _requested_provider() -> str:
    return str(os.getenv("FACTLENS_LLM_PROVIDER", "auto") or "auto").strip().lower()


def _provider_candidates(requested_provider: str) -> list[str]:
    if requested_provider == "auto":
        return list(PROVIDER_PRIORITY)
    return [requested_provider]


def create_chat_model(
    purpose: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 2048,
    vision: bool = False,
) -> tuple[Any | None, LLMDescriptor]:
    requested_provider = _requested_provider()
    candidates = _provider_candidates(requested_provider)
    issues: list[str] = []

    for provider in candidates:
        if provider not in PROVIDER_LABELS:
            descriptor = LLMDescriptor(
                purpose=purpose,
                provider=None,
                provider_label=None,
                model=None,
                status="misconfigured",
                issue=f"Unsupported LLM provider '{provider}'.",
                vision=vision,
            )
            return None, descriptor

        api_key, api_key_name = _resolve_api_key(provider)
        if not api_key:
            issues.append(f"{PROVIDER_LABELS[provider]} is unavailable because {api_key_name} is not set.")
            continue

        model = _resolve_model(provider, purpose, vision)
        try:
            model_instance = _instantiate_model(
                provider,
                model=model,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except ImportError:
            package_hint = {
                "google": "langchain-google-genai",
                "nvidia": "langchain-nvidia-ai-endpoints",
                "openai": "langchain-openai",
            }[provider]
            issues.append(
                f"{PROVIDER_LABELS[provider]} is unavailable because {package_hint} is not installed."
            )
            continue
        except Exception as exc:
            issues.append(f"{PROVIDER_LABELS[provider]} could not be initialized: {exc}")
            continue

        descriptor = LLMDescriptor(
            purpose=purpose,
            provider=provider,
            provider_label=PROVIDER_LABELS[provider],
            model=model,
            status="ready",
            issue=None,
            vision=vision,
        )
        return model_instance, descriptor

    status = "unconfigured" if requested_provider == "auto" else "misconfigured"
    descriptor = LLMDescriptor(
        purpose=purpose,
        provider=None,
        provider_label=None,
        model=None,
        status=status,
        issue=" ".join(issues).strip()
        or "No supported LLM provider is configured.",
        vision=vision,
    )
    return None, descriptor
