"""Redownload failed gallery images and update the database.

Reads the gallery SQLite database, finds images tagged '下载失败' that are
missing a local file on disk, downloads them from the original remote URL,
saves them into the gallery save directory, and updates the database records
(saved_file_path, relative_path, local_path) so the frontend can display them.
Finally removes the '下载失败' tag from successfully recovered images.

Usage:
    python scripts/redownload_and_fix_failed_gallery_images.py
    python scripts/redownload_and_fix_failed_gallery_images.py --dry-run
    python scripts/redownload_and_fix_failed_gallery_images.py --tag 下载失败 --timeout 120
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend_v2"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import config  # noqa: E402


DEFAULT_TAG = "下载失败"
MAX_RETRIES = 3
RETRY_DELAY = 2.0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Redownload gallery images tagged as '下载失败', update DB paths, and remove the tag."
    )
    parser.add_argument("--tag", default=DEFAULT_TAG, help=f"Tag to scan. Default: {DEFAULT_TAG}")
    parser.add_argument("--db", default=str(config.GALLERY_DB_PATH), help="Gallery SQLite path.")
    parser.add_argument("--save-dir", default=str(config.OPENAI_SAVE_DIR), help="Target save directory.")
    parser.add_argument("--timeout", type=int, default=120, help="Download timeout seconds per attempt.")
    parser.add_argument("--retries", type=int, default=MAX_RETRIES, help="Max download retry attempts.")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be done, don't download or modify DB.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    save_dir = Path(args.save_dir).resolve()

    if not db_path.exists():
        print(f"ERROR: Gallery DB not found: {db_path}")
        return 1

    save_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Read failed records from gallery DB
    records = _load_failed_records(db_path, args.tag)
    if not records:
        print("没有找到标记为「下载失败」的图片记录。")
        return 0

    print(f"找到 {len(records)} 条标记为「{args.tag}」的记录，开始处理...\n")

    stats = {"total": len(records), "recovered": 0, "skipped": 0, "failed": 0, "already_exists": 0}

    for index, record in enumerate(records, start=1):
        image_id = record["id"]
        url = record["url"]
        existing_file = record["existing_file"]

        print(f"[{index}/{len(records)}] {image_id}")

        # Skip if no URL to download from
        if not url:
            stats["skipped"] += 1
            print(f"  SKIP: 没有找到可用的远程下载 URL\n")
            continue

        # Check if file already exists on disk
        if existing_file and Path(existing_file).exists():
            stats["already_exists"] += 1
            print(f"  EXISTS: 文件已存在于 {existing_file}")
            if not args.dry_run:
                _fix_db_record(db_path, image_id, existing_file, save_dir, args.tag)
                print(f"  FIXED: 已更新数据库记录并移除「{args.tag}」标签\n")
            else:
                print(f"  DRY: 将会更新数据库记录并移除标签\n")
            stats["recovered"] += 1
            continue

        # Determine save target
        target = _determine_save_path(record, save_dir, url, image_id)
        print(f"  URL:  {url}")
        print(f"  保存: {target}")

        if args.dry_run:
            print(f"  DRY: 将会下载并更新数据库\n")
            continue

        # Download with retries
        success = _download_with_retries(url, target, timeout=args.timeout, retries=args.retries)
        if not success:
            stats["failed"] += 1
            print(f"  FAIL: 下载失败（已重试 {args.retries} 次）\n")
            continue

        file_size = target.stat().st_size
        print(f"  OK:   下载成功 ({file_size:,} bytes)")

        # Update database
        _fix_db_record(db_path, image_id, str(target), save_dir, args.tag)
        print(f"  FIXED: 已更新数据库记录并移除「{args.tag}」标签\n")
        stats["recovered"] += 1

    print("=" * 50)
    print(
        f"完成: 总计={stats['total']} 恢复={stats['recovered']} "
        f"已存在={stats['already_exists']} 跳过={stats['skipped']} 失败={stats['failed']}"
    )
    return 0 if stats["failed"] == 0 else 1


# ---------------------------------------------------------------------------
# Database reading
# ---------------------------------------------------------------------------

def _load_failed_records(db_path: Path, tag: str) -> list[dict[str, Any]]:
    """Load gallery images tagged with the given failure tag."""
    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT gi.id, gi.relative_path, gi.saved_file_path, gi.local_path,
                   gi.original_url_json, gi.extra_json
            FROM gallery_images gi
            JOIN gallery_image_tags gt ON gt.image_id = gi.id
            WHERE gt.tag = ?
            ORDER BY gi.created_at DESC, gi.id ASC
            """,
            (tag,),
        ).fetchall()

    records: list[dict[str, Any]] = []
    for row in rows:
        url = _extract_download_url(row)
        existing_file = _find_existing_file(row)
        records.append({
            "id": row["id"],
            "url": url,
            "existing_file": existing_file,
            "relative_path": row["relative_path"],
            "saved_file_path": row["saved_file_path"],
            "local_path": row["local_path"],
        })
    return records


def _extract_download_url(row: sqlite3.Row) -> str | None:
    """Extract the first HTTP(S) URL from the row's various fields."""
    for value in (
        _json_loads(row["original_url_json"]),
        _json_loads(row["extra_json"]),
        row["local_path"],
        row["saved_file_path"],
    ):
        url = _find_http_url(value)
        if url:
            return url
    return None


def _find_existing_file(row: sqlite3.Row) -> str | None:
    """Check if any of the row's path fields point to an existing file."""
    # Check relative_path
    if row["relative_path"]:
        abs_path = Path(config.OPENAI_SAVE_DIR) / row["relative_path"]
        if abs_path.exists():
            return str(abs_path)

    # Check saved_file_path
    if row["saved_file_path"] and Path(row["saved_file_path"]).exists():
        return row["saved_file_path"]

    # Check local_path (might be a serve URL)
    local_path = _path_from_serve_url(row["local_path"] or "")
    if local_path and Path(local_path).exists():
        return local_path

    return None


# ---------------------------------------------------------------------------
# Database writing
# ---------------------------------------------------------------------------

def _fix_db_record(db_path: Path, image_id: str, file_path: str, save_dir: Path, tag: str) -> None:
    """Update the database record with the correct file paths and remove the failure tag."""
    resolved = Path(file_path).resolve()
    timestamp = datetime.now(timezone.utc).isoformat()

    # Compute relative_path (relative to save_dir / gallery root)
    try:
        relative_path = resolved.relative_to(Path(save_dir).resolve()).as_posix()
    except ValueError:
        relative_path = None

    # Build local_path as a serve URL
    if relative_path:
        local_path = f"/api/serve-image?path={quote(relative_path, safe='')}"
    else:
        local_path = f"/api/serve-image?path={quote(str(resolved), safe='')}"

    with sqlite3.connect(db_path, timeout=30) as connection:
        connection.row_factory = sqlite3.Row

        # Update file paths in gallery_images
        connection.execute(
            """
            UPDATE gallery_images
            SET saved_file_path = ?,
                relative_path = ?,
                local_path = ?,
                thumbnail = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                str(resolved),
                relative_path,
                local_path,
                local_path,
                timestamp,
                image_id,
            ),
        )

        # Remove the failure tag
        connection.execute(
            "DELETE FROM gallery_image_tags WHERE image_id = ? AND tag = ?",
            (image_id, tag),
        )

        connection.commit()


# ---------------------------------------------------------------------------
# Download logic
# ---------------------------------------------------------------------------

def _download_with_retries(url: str, target: Path, *, timeout: int, retries: int) -> bool:
    """Download a file with retry logic. Returns True on success."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(f"{target.name}.tmp")

    for attempt in range(1, retries + 1):
        try:
            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                with tmp_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            file.write(chunk)
            # Atomic rename
            tmp_path.replace(target)
            return True
        except Exception as exc:
            print(f"  RETRY {attempt}/{retries}: {exc}")
            # Clean up partial tmp file
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            if attempt < retries:
                time.sleep(RETRY_DELAY * attempt)

    return False


# ---------------------------------------------------------------------------
# Path determination
# ---------------------------------------------------------------------------

def _determine_save_path(record: dict[str, Any], save_dir: Path, url: str, image_id: str) -> Path:
    """Determine where to save the downloaded file."""
    # Prefer existing relative_path if set
    relative_path = record.get("relative_path")
    if relative_path:
        return save_dir / relative_path

    # Try to extract from saved_file_path
    saved = record.get("saved_file_path") or ""
    if saved:
        candidate = Path(saved)
        if candidate.is_absolute():
            # If it was supposed to be under save_dir, use same relative structure
            try:
                rel = candidate.relative_to(Path(save_dir).resolve())
                return save_dir / rel
            except ValueError:
                return save_dir / candidate.name
        return save_dir / saved

    # Try to extract from local_path (serve URL)
    serve_path = _path_from_serve_url(record.get("local_path") or "")
    if serve_path:
        candidate = Path(serve_path)
        if candidate.is_absolute():
            try:
                rel = candidate.relative_to(Path(save_dir).resolve())
                return save_dir / rel
            except ValueError:
                return save_dir / candidate.name
        return save_dir / serve_path

    # Fall back to generating a filename from the URL
    return save_dir / _filename_from_url(url, image_id)


def _filename_from_url(url: str, image_id: str) -> str:
    """Generate a filename from a URL or image ID."""
    if url:
        parsed = urlparse(url)
        url_name = Path(unquote(parsed.path)).name
        if url_name and Path(url_name).suffix:
            # Add a short hash to avoid collisions
            url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
            stem = Path(url_name).stem
            suffix = Path(url_name).suffix
            return f"{stem}_{url_hash}{suffix}"

    # Use image ID + guess extension from URL
    suffix = ".png"
    if url:
        content_type_hint = parse_qs(urlparse(url).query).get("content_type", [None])[0]
        suffix = mimetypes.guess_extension(content_type_hint or "") or suffix
    return f"recovered_{image_id[:32]}{suffix}"


# ---------------------------------------------------------------------------
# URL / JSON helpers
# ---------------------------------------------------------------------------

def _find_http_url(value: Any) -> str | None:
    """Recursively search for an HTTP(S) URL in a value."""
    if isinstance(value, str):
        text = value.strip()
        return text if text.startswith(("http://", "https://")) else None
    if isinstance(value, dict):
        for key in ("url", "originalUrl", "original_url", "data", "image", "src"):
            url = _find_http_url(value.get(key))
            if url:
                return url
        for item in value.values():
            url = _find_http_url(item)
            if url:
                return url
    if isinstance(value, list):
        for item in value:
            url = _find_http_url(item)
            if url:
                return url
    return None


def _path_from_serve_url(value: str) -> str | None:
    """Extract a filesystem path from a /api/serve-image?path=... URL."""
    if "/api/serve-image" not in value:
        return None
    parsed = urlparse(value)
    raw_path = parse_qs(parsed.query).get("path", [None])[0]
    return unquote(raw_path) if raw_path else None


def _json_loads(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


if __name__ == "__main__":
    raise SystemExit(main())
