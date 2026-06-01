from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import ServiceConfig
from .exceptions import ServiceAPIError, ServiceAuthError
from .models import AccountRecord


class SousakuServiceClient:
    def __init__(self, config: ServiceConfig, token: str | None = None, timeout: int = 30) -> None:
        self.config = config
        self.token = token or ""
        self.timeout = timeout
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods=("GET", "POST", "PUT"),
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def with_token(self, token: str) -> "SousakuServiceClient":
        return SousakuServiceClient(self.config, token=token, timeout=self.timeout)

    def headers(self) -> dict[str, str]:
        parsed_app = urlparse(self.config.app_base_url)
        origin = f"{parsed_app.scheme}://{parsed_app.netloc}".rstrip("/")
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
            "content-type": "application/json",
            "origin": origin,
            "referer": self.config.app_base_url.rstrip("/") + "/",
            "user-agent": "Mozilla/5.0",
        }
        if self.config.version_header:
            headers["x-sousaku-version"] = self.config.version_header
        if self.token:
            headers["authorization"] = self.token
            headers["cookie"] = f"pp_user_token={self.token}"
        return headers

    def get_user(self) -> dict[str, Any]:
        data = self._json(self.session.get(
            self._url("/v1/user"),
            headers=self.headers(),
            timeout=self.timeout,
        ))
        return data.get("data") or {}

    def account_from_token(self, token: str, fallback_email: str = "") -> AccountRecord:
        user = self.with_token(token).get_user()
        subscription = user.get("subscription") or {}
        task = user.get("task") or {}
        return AccountRecord(
            email=user.get("user_email") or fallback_email,
            token=token,
            user_id=user.get("user_id") or "",
            nickname=user.get("nick_name") or user.get("user_name") or "",
            package_level=subscription.get("package_level") or "unknown",
            share_code=user.get("share_code") or "",
            inviter_share_code=user.get("inviter_share_code") or task.get("inviter_share_code") or "",
            total_credit=_to_int(subscription.get("total_credit")),
            raw=user,
        )

    def complete_reward(self, token: str, task_id: str) -> bool:
        client = self.with_token(token)
        data = client._json(client.session.post(
            client._url("/v1/tasks/complete"),
            headers=client.headers(),
            json={"source": 2, "task_id": task_id},
            timeout=client.timeout,
        ))
        return data.get("success") is not False

    def claim_reward(self, token: str, task_id: str) -> bool:
        client = self.with_token(token)
        response = client.session.post(
            client._url("/v1/tasks/get_reward"),
            headers=client.headers(),
            json={"source": 2, "task_id": task_id},
            timeout=client.timeout,
        )
        try:
            data = response.json()
        except ValueError:
            response.raise_for_status()
            return False
        if data.get("success") is False:
            message = str(data.get("error_message") or data.get("message") or data.get("error") or "")
            lowered = message.lower()
            if "already" in lowered or ("completed" in lowered and "not completed" not in lowered and "not complete" not in lowered):
                return True
            raise ServiceAPIError(f"Service API error: {message or data}")
        response.raise_for_status()
        return data.get("success") is not False

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.config.api_base_url.rstrip('/')}{path}"

    def _json(self, response: requests.Response) -> dict[str, Any]:
        if response.status_code in {401, 403}:
            raise ServiceAuthError(f"Token rejected with HTTP {response.status_code}.")
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            raise ServiceAPIError(f"Invalid JSON response: {response.text[:300]}") from exc
        if data.get("success") is False:
            message = data.get("error_message") or data.get("message") or data
            raise ServiceAPIError(f"Service API error: {message}")
        return data


def _to_int(value: Any) -> int | None:
    try:
        return None if value is None else int(value)
    except (TypeError, ValueError):
        return None
