from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .config import AppConfig
from .service import SousakuServiceClient


class GenerationRunner:
    def __init__(self, config: AppConfig, service: SousakuServiceClient) -> None:
        self.config = config
        self.service = service

    def run(self, token: str, *, wait_for_result: bool | None = None) -> list[str]:
        client = self.service.with_token(token)
        task_ids: list[str] = []
        submitted: list[tuple[dict[str, Any], str]] = []
        for task in self.config.generation.tasks:
            endpoint = task.get("endpoint")
            payload = task.get("payload")
            if not endpoint or not isinstance(payload, dict):
                print("Generation task skipped: missing endpoint/payload.")
                continue
            data = client._json(client.session.post(
                client._url(str(endpoint)),
                headers=client.headers(),
                json=payload,
                timeout=client.timeout,
            ))
            task_id = extract_task_id(data)
            if not task_id:
                print(f"Generation task did not return task_id: {data}")
                continue
            task_ids.append(task_id)
            submitted.append((task, task_id))
            print(f"Submitted generation task: {task.get('type', 'task')} {task_id}")

        wait_flag = wait_for_result if wait_for_result is not None else self.config.generation.wait_for_result
        if wait_flag:
            for task, task_id in submitted:
                result = self.wait_for_task(client, task_id)
                media_items = extract_media(result)
                if self.config.generation.save_dir and media_items:
                    self.download_media(client, task_id, media_items)
                if task.get("type") == "image" and self.config.generation.publish_after_success:
                    file_ids = [item.get("file_id") for item in media_items if item.get("file_id")]
                    if not file_ids:
                        file_ids = find_file_ids(result)
                    if file_ids:
                        self.publish_images(client, file_ids)
        return task_ids

    def wait_for_task(self, client: SousakuServiceClient, task_id: str) -> dict[str, Any]:
        import time

        deadline = time.time() + int(self.config.generation.generation_timeout)
        interval = float(self.config.generation.poll_interval_seconds)
        last: dict[str, Any] = {}
        while time.time() < deadline:
            data = client._json(client.session.get(
                client._url("/v1/generations/task_status"),
                headers=client.headers(),
                params={"task_ids": task_id, "language": "zh-CN"},
                timeout=15,
            ))
            last = extract_task(data, task_id)
            status = str(last.get("status", "")).lower()
            if status in {"success", "completed", "complete", "done", "succeeded", "3", "4"}:
                print(f"Generation task succeeded: {task_id}")
                return last
            if status in {"failed", "failure", "error", "canceled", "cancelled", "-1", "-2"}:
                raise RuntimeError(f"Generation task failed: {task_id}; {last}")
            time.sleep(interval)
        raise TimeoutError(f"Generation task timed out: {task_id}; last={last}")

    def publish_images(self, client: SousakuServiceClient, file_ids: list[str]) -> None:
        client._json(client.session.put(
            client._url("/v1/images/publish_status"),
            headers=client.headers(),
            json={"source": 2, "file_ids": file_ids, "is_published": 1},
            timeout=client.timeout,
        ))
        print(f"Published images: {file_ids}")

    def download_media(self, client: SousakuServiceClient, task_id: str, items: list[dict[str, Any]]) -> None:
        save_dir = self.config.resolve(self.config.generation.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        for index, item in enumerate(items, start=1):
            url = item.get("download_url")
            if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                continue
            response = client.session.get(url, timeout=120)
            response.raise_for_status()
            ext = extension_from_url(url, response.headers.get("content-type", ""))
            suffix = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
            path = save_dir / f"{task_id}_{index:02d}_{suffix}.{ext}"
            path.write_bytes(response.content)
            print(f"Saved generated media: {path}")

    def check_and_claim_pending(self, token: str, pending_tasks: list[str]) -> list[str]:
        if not pending_tasks:
            return []

        client = self.service.with_token(token)
        remaining_tasks = list(pending_tasks)
        completed_any = False

        for task_id in pending_tasks:
            try:
                data = client._json(client.session.get(
                    client._url("/v1/generations/task_status"),
                    headers=client.headers(),
                    params={"task_ids": task_id, "language": "zh-CN"},
                    timeout=15,
                ))
                last = extract_task(data, task_id)
                status = str(last.get("status", "")).lower()

                if status in {"success", "completed", "complete", "done", "succeeded", "3", "4"}:
                    print(f"Pending generation task {task_id} is completed!")
                    media_items = extract_media(last)
                    if self.config.generation.save_dir and media_items:
                        try:
                            self.download_media(client, task_id, media_items)
                        except Exception as e:
                            print(f"Failed to download media for {task_id}: {e}")

                    file_ids = [item.get("file_id") for item in media_items if item.get("file_id")]
                    if not file_ids:
                        file_ids = find_file_ids(last)
                    if file_ids and self.config.generation.publish_after_success:
                        try:
                            self.publish_images(client, file_ids)
                        except Exception as e:
                            print(f"Failed to publish images for {task_id}: {e}")

                    remaining_tasks.remove(task_id)
                    completed_any = True
                elif status in {"failed", "failure", "error", "canceled", "cancelled", "-1", "-2"}:
                    print(f"Pending generation task {task_id} failed on server.")
                    remaining_tasks.remove(task_id)
                else:
                    print(f"Pending generation task {task_id} is still running (status: {status}).")
            except Exception as exc:
                print(f"Failed to check status for task {task_id}: {exc}")

        if completed_any:
            print("发现已完成任务，尝试领取生成积分奖励...")
            generation_claims = [
                task_id
                for task_id in self.config.chain.reward_claim_task_ids
                if task_id not in self.config.chain.reward_task_ids
                and task_id != self.config.chain.final_reward_task_id
            ]
            for claim_id in generation_claims:
                try:
                    self.service.claim_reward(token, claim_id)
                    print(f"已领取积分奖励: {claim_id}")
                except Exception:
                    pass

        return remaining_tasks


def extract_task_id(data: dict[str, Any]) -> str:
    body = data.get("data")
    if isinstance(body, str):
        return body
    if isinstance(body, dict):
        return str(body.get("task_id") or body.get("id") or "")
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return str(body[0].get("task_id") or body[0].get("id") or "")
    return str(data.get("task_id") or data.get("id") or "")


def extract_task(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    body = data.get("data", data)
    if isinstance(body, list):
        for item in body:
            if isinstance(item, dict) and str(item.get("task_id") or item.get("id")) == str(task_id):
                return item
        return body[0] if body and isinstance(body[0], dict) else {}
    if isinstance(body, dict):
        return body
    return {}


def extract_media(task: dict[str, Any]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    for item in task.get("content") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("status", "")).lower() not in {"succeeded", "success", "completed", "done"}:
            continue
        if item.get("download_url"):
            media.append(item)
    return media


def extension_from_url(url: str, content_type: str) -> str:
    content_type = content_type.lower().split(";", 1)[0].strip()
    if content_type == "video/mp4":
        return "mp4"
    if content_type == "image/webp":
        return "webp"
    if content_type in {"image/jpeg", "image/jpg"}:
        return "jpg"
    if content_type == "image/png":
        return "png"
    lower = url.lower().split("?", 1)[0]
    for ext in ("mp4", "webm", "mov", "png", "jpg", "jpeg", "webp"):
        if lower.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ext
    return "bin"


def find_file_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "file_id" and isinstance(item, str) and item:
                found.append(item)
            else:
                found.extend(find_file_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(find_file_ids(item))
    return list(dict.fromkeys(found))
