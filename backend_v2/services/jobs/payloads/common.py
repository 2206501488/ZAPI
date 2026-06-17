from __future__ import annotations

from typing import Any


# Keep the shared mapping here so the provider-specific translators stay small.
CLIPROXY_PIXEL_SIZE_MAP: dict[str, dict[str, str]] = {
    "1:1": {"1K": "1024x1024", "2K": "2048x2048", "4K": "2880x2880"},
    "3:2": {"1K": "1536x1024", "2K": "2048x1360", "4K": "3504x2336"},
    "2:3": {"1K": "1024x1536", "2K": "1360x2048", "4K": "2336x3504"},
    "4:3": {"1K": "1024x768", "2K": "2048x1536", "4K": "3264x2448"},
    "3:4": {"1K": "768x1024", "2K": "1536x2048", "4K": "2448x3264"},
    "5:4": {"1K": "1280x1024", "2K": "2560x2048", "4K": "3200x2560"},
    "4:5": {"1K": "1024x1280", "2K": "2048x2560", "4K": "2560x3200"},
    "16:9": {"1K": "1536x864", "2K": "2048x1152", "4K": "3840x2160"},
    "9:16": {"1K": "864x1536", "2K": "1152x2048", "4K": "2160x3840"},
    "2:1": {"1K": "2048x1024", "2K": "2688x1344", "4K": "3840x1920"},
    "1:2": {"1K": "1024x2048", "2K": "1344x2688", "4K": "1920x3840"},
    "21:9": {"1K": "2016x864", "2K": "2688x1152", "4K": "3840x1648"},
    "9:21": {"1K": "864x2016", "2K": "1152x2688", "4K": "1648x3840"},
}


def flatten_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge nested `params` into the top-level payload.

    The unified job system stores the original request under `params`, but the
    compatibility layer needs a flat view so provider translators can stay
    simple and deterministic.
    """
    source = dict(payload or {})
    nested = source.get("params")
    if isinstance(nested, dict):
        merged = dict(nested)
        for key, value in source.items():
            if key != "params":
                merged[key] = value
        source = merged
    return source


def request_model_config(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("model_config") or payload.get("modelConfig")
    return value if isinstance(value, dict) else {}


def lookup_model_config(provider: str, model: str) -> dict[str, Any]:
    if not provider or not model:
        return {}
    try:
        import config

        provider_data = config.normalized_providers_settings().get("providers", {}).get(provider, {})
        models = provider_data.get("models") if isinstance(provider_data, dict) else []
        if not isinstance(models, list):
            return {}
        for item in models:
            if isinstance(item, dict) and str(item.get("value") or "") == model:
                return item
    except Exception:
        return {}
    return {}


def model_value(provider: str, payload: dict[str, Any], model_config: dict[str, Any]) -> str:
    configured = str(model_config.get("value") or "").strip()
    if configured:
        return configured
    if payload.get("model"):
        return str(payload["model"])
    provider_key = {
        "apimart": "apimartModel",
        "cliproxy": "cliproxyModel",
        "sousaku": "sousakuModel",
        "hotgen": "sousakuModel",
    }.get(provider)
    return str(payload.get(provider_key) or "").strip() if provider_key else ""


def default(model_config: dict[str, Any], key: str) -> Any:
    defaults = model_config.get("defaults")
    return defaults.get(key) if isinstance(defaults, dict) else None


def constraints(model_config: dict[str, Any]) -> dict[str, Any]:
    value = model_config.get("constraints")
    return value if isinstance(value, dict) else {}


def payload_config(model_config: dict[str, Any]) -> dict[str, Any]:
    value = model_config.get("payload")
    return value if isinstance(value, dict) else {}


def has_control(model_config: dict[str, Any], key: str) -> bool:
    controls = model_config.get("controls")
    return isinstance(controls, list) and any(isinstance(item, dict) and item.get("key") == key for item in controls)


def image_count(payload: dict[str, Any], model_config: dict[str, Any]) -> int:
    fixed = int_value(constraints(model_config).get("fixedImageCount"))
    if fixed:
        return fixed
    for key in ("n", "imageCount", "number"):
        value = int_value(payload.get(key))
        if value:
            return value
    return int_value(default(model_config, "imageCount")) or 1


def size_for_model(model_config: dict[str, Any], ratio: str, resolution: str, *, fallback: str) -> str:
    resolution = canonical_resolution(resolution) or resolution
    config = payload_config(model_config)
    if config.get("size") == "pixelSizeMap":
        pixel_map = config.get("pixelSizeMap")
        if isinstance(pixel_map, dict):
            by_ratio = pixel_map.get(ratio)
            if isinstance(by_ratio, dict):
                value = by_ratio.get(resolution)
                if value:
                    return str(value)
    return fallback


def cliproxy_pixel_size(ratio: str, resolution: str) -> str:
    ratio = ratio or "16:9"
    resolution = canonical_resolution(resolution) or "2K"
    return CLIPROXY_PIXEL_SIZE_MAP.get(ratio, {}).get(resolution) or CLIPROXY_PIXEL_SIZE_MAP.get(ratio, {}).get("2K") or "2048x1152"


def canonical_resolution(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"1K", "2K", "4K"} else ""


def sousaku_resolution(value: Any) -> str:
    normalized = canonical_resolution(value)
    return normalized.lower() if normalized else ""


def normalize_sousaku_model(model: str) -> str:
    aliases = {
        "low": "gpt-image-2-low",
        "medium": "gpt-image-2",
        "high": "gpt-image-2-high",
        "gpt-image-2-4k": "gpt-image-2",
        "gpt-image-2-medium": "gpt-image-2",
        "gpt-image-2-high-4k": "gpt-image-2-high",
    }
    return aliases.get(model, model)


def sousaku_default_resolution(model: str) -> str | None:
    if model in {"gpt-image-2-low", "gpt-image-2", "gpt-image-2-high", "wan-image-2.7-pro"}:
        return "4K"
    if model == "seedream-4.5":
        return "2K"
    return None


def sousaku_fixed_image_count(model: str) -> int | None:
    return 4 if model in {"mj-image-v7", "mj-image-niji-7"} else None


def bool_value(value: Any, default_value: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default_value
    return bool(value)


def int_value(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def strip_schema_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove schema-only keys before the payload leaves the compatibility layer."""
    payload = dict(payload)
    for key in ("params", "model_config", "modelConfig", "imageCount", "apimartModel", "cliproxyModel", "sousakuModel", "thinkingLevel", "sousakuAutoOptimize", "inputMaxEdge"):
        payload.pop(key, None)
    return payload
