from __future__ import annotations

from typing import Any

from .common import (
    bool_value,
    has_control,
    normalize_sousaku_model,
    size_for_model,
    strip_schema_fields,
    sousaku_default_resolution,
    sousaku_fixed_image_count,
    sousaku_resolution,
)


def translate(
    source: dict[str, Any],
    *,
    model: str,
    model_config: dict[str, Any],
    ratio: str,
    resolution: str,
    quality: Any,
    n: int,
) -> dict[str, Any]:
    translated = dict(source)
    translated["prompt"] = source.get("prompt") or ""

    sousaku_model = normalize_sousaku_model(model or str(source.get("sousakuModel") or "gpt-image-2"))
    translated["model"] = sousaku_model
    translated["size"] = size_for_model(model_config, ratio, resolution, fallback=ratio or "1:1")

    default_resolution = sousaku_default_resolution(sousaku_model)
    if has_control(model_config, "resolution") or default_resolution:
        translated["resolution"] = sousaku_resolution(resolution) or sousaku_resolution(default_resolution)

    translated["auto_optimize"] = bool_value(source.get("sousakuAutoOptimize"), True)

    fixed_count = sousaku_fixed_image_count(sousaku_model)
    if fixed_count:
        translated["n"] = fixed_count
    elif n:
        translated["n"] = n

    # Midjourney models have a fixed batch size in Sousaku; keeping the limit
    # in the translator prevents the UI from having to special-case execution.
    return strip_schema_fields(translated)
