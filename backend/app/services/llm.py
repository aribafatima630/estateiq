from __future__ import annotations

import logging
import time

import httpx

from app.core.config import Settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


def _now() -> float:
    return time.time()


class _RateLimited(LLMUnavailable):
    pass


class _Transient(LLMUnavailable):
    pass


class OpenRouterClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.resolved_model: str | None = None
        self._cooled_until: dict[str, float] = {}
        self._catalog: list[str] | None = None
        self._catalog_until = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.settings.openrouter_api_key.strip())

    def resolve_model(self) -> str | None:
        models = self.candidate_models()
        if models and self.resolved_model not in models:
            self.resolved_model = models[0]
        return self.resolved_model

    def candidate_models(self) -> list[str]:
        if not self.configured:
            return []
        now = _now()
        if self._catalog is not None and now < self._catalog_until:
            return self._prefer_ready(self._catalog)
        configured = self.settings.fallback_model_list
        try:
            response = httpx.get(
                f"{self.settings.openrouter_base_url}/models",
                timeout=20.0,
                headers={"Authorization": f"Bearer {self.settings.openrouter_api_key}"},
            )
            response.raise_for_status()
            available = {
                model["id"]
                for model in response.json().get("data", [])
                if _is_free_text_model(model)
            }
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Could not list OpenRouter models: %s", exc)
            return configured
        ordered = [model for model in configured if model in available]
        if not ordered and available:
            ordered = [next(iter(available))]
        self._catalog = ordered
        self._catalog_until = now + 600
        return self._prefer_ready(ordered)

    def complete(self, messages: list[dict[str, str]]) -> str:
        models = self.candidate_models()
        if not models:
            raise LLMUnavailable("OpenRouter is not configured or no free model is available.")
        last_error: Exception | None = None
        for model in models:
            for attempt in range(2):
                try:
                    answer = self._complete_once(model, messages)
                    self.resolved_model = model
                    logger.info("Using OpenRouter model %s", model)
                    return answer
                except _RateLimited as exc:
                    last_error = exc
                    self._cooled_until[model] = _now() + 120
                    logger.warning("%s is rate limited. Trying the next free model.", model)
                    break
                except (_Transient, httpx.HTTPError, KeyError, IndexError, TypeError, LLMUnavailable) as exc:
                    last_error = exc
                    logger.warning("OpenRouter %s attempt %s failed: %s", model, attempt + 1, exc)
                    if attempt == 0 and isinstance(exc, _Transient):
                        time.sleep(1.0)
                        continue
                    break
        raise LLMUnavailable(str(last_error or "OpenRouter request failed"))

    def _complete_once(self, model: str, messages: list[dict[str, str]]) -> str:
        response = httpx.post(
            f"{self.settings.openrouter_base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "HTTP-Referer": self.settings.openrouter_site_url,
                "X-Title": self.settings.openrouter_app_name,
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.1,
                "max_tokens": 700,
            },
            timeout=60.0,
        )
        if response.status_code == 429:
            raise _RateLimited(f"{model} returned HTTP 429")
        if response.status_code in {500, 502, 503, 504}:
            raise _Transient(f"{model} returned HTTP {response.status_code}")
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise LLMUnavailable("OpenRouter returned an empty answer.")
        return content.strip()

    def _prefer_ready(self, models: list[str]) -> list[str]:
        now = _now()
        ready = [model for model in models if self._cooled_until.get(model, 0) <= now]
        cooled = [model for model in models if model not in ready]
        return ready + cooled


def _is_free_text_model(model: dict) -> bool:
    model_id = str(model.get("id") or "")
    modality = ""
    architecture = model.get("architecture")
    if isinstance(architecture, dict):
        modality = str(architecture.get("modality") or "")
    if "audio" in modality.split("->")[-1:]:
        return False
    if modality.endswith("audio"):
        return False
    pricing = model.get("pricing") or {}
    try:
        prompt = float(pricing.get("prompt") or 0)
        completion = float(pricing.get("completion") or 0)
    except (TypeError, ValueError):
        return False
    free_id = model_id.endswith(":free") or model_id == "openrouter/free"
    return free_id and prompt == 0 and completion == 0
