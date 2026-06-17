from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import uuid
from typing import Any

from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from services.image_files import import_dir, is_allowed_image_filename, serve_url_for_path


def import_uploaded_files(
    files: list[FileStorage],
    *,
    prompt: str = "外部导入图片",
    api_type: str = "other",
    ratio: str = "auto",
    quality: str = "imported",
    created_at: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for file in files:
        if not file or not file.filename:
            continue
        if not is_allowed_image_filename(file.filename):
            raise ValueError(f"Unsupported image type: {file.filename}")

        target_path = _target_path(file.filename)
        file.save(target_path)
        imported.append(
            build_gallery_item(
                target_path,
                prompt=prompt,
                api_type=api_type,
                ratio=ratio,
                quality=quality,
                created_at=created_at,
                tags=tags,
            )
        )
    return imported


def import_local_paths(
    paths: list[str],
    *,
    prompt: str = "外部导入图片",
    api_type: str = "other",
    ratio: str = "auto",
    quality: str = "imported",
    created_at: str | None = None,
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    imported: list[dict[str, Any]] = []
    for raw_path in paths:
        source = Path(raw_path)
        if not source.exists() or not source.is_file():
            raise ValueError(f"File not found: {raw_path}")
        if not is_allowed_image_filename(source.name):
            raise ValueError(f"Unsupported image type: {source.name}")

        target_path = _target_path(source.name)
        shutil.copy2(source, target_path)
        imported.append(
            build_gallery_item(
                target_path,
                prompt=prompt,
                api_type=api_type,
                ratio=ratio,
                quality=quality,
                created_at=created_at,
                tags=tags,
            )
        )
    return imported


def build_gallery_item(
    path: str | Path,
    *,
    prompt: str,
    api_type: str,
    ratio: str,
    quality: str,
    created_at: str | None,
    tags: list[str] | None,
) -> dict[str, Any]:
    path = Path(path).resolve()
    width, height = _image_size(path)
    serve_url = serve_url_for_path(path)

    return {
        "id": str(uuid.uuid4()),
        "status": "success",
        "localPath": serve_url,
        "thumbnail": serve_url,
        "prompt": prompt,
        "apiType": _normalize_api_type(api_type),
        "params": {
            "ratio": ratio,
            "quality": quality,
            "size": f"{width}x{height}" if width and height else "",
            "resolution": _resolution_label(width, height),
            "imageCount": 1,
        },
        "createdAt": created_at or datetime.now(timezone.utc).isoformat(),
        "isFavorite": False,
        "tags": tags if tags is not None else [],
        "savedFilePath": str(path),
        "width": width,
        "height": height,
    }


def _target_path(original_filename: str) -> Path:
    suffix = Path(original_filename).suffix.lower() or ".png"
    stem = secure_filename(Path(original_filename).stem) or "image"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return import_dir() / f"import_{timestamp}_{uuid.uuid4().hex[:8].upper()}_{stem}{suffix}"


def _image_size(path: Path) -> tuple[int | None, int | None]:
    with Image.open(path) as img:
        width, height = img.size
    return width, height


def _resolution_label(width: int | None, height: int | None) -> str:
    max_dim = max(width or 0, height or 0)
    if max_dim >= 3200:
        return "4K"
    if max_dim >= 1600:
        return "2K"
    return "1K"


def _normalize_api_type(value: str) -> str:
    allowed = {"apimart", "openai", "nanobanana2", "cliproxy", "sousaku", "hotgen", "other"}
    return value if value in allowed else "other"
