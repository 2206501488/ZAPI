from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def mask_token(token: str) -> str:
    token = token or ""
    if len(token) <= 12:
        return "*" * len(token)
    return f"{token[:6]}...{token[-6:]}"


@dataclass
class AccountRecord:
    email: str
    token: str
    user_id: str = ""
    nickname: str = ""
    package_level: str = "unknown"
    share_code: str = ""
    inviter_share_code: str = ""
    total_credit: int | None = None
    pending_tasks: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @property
    def token_masked(self) -> str:
        return mask_token(self.token)

    def to_dict(self, *, include_token: bool = True, include_raw: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_token:
            data.pop("token", None)
        data["token_masked"] = self.token_masked
        if not include_raw:
            data.pop("raw", None)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountRecord":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass
class LoginResult:
    success: bool
    email: str = ""
    token: str = ""
    account: AccountRecord | None = None
    error: str = ""
