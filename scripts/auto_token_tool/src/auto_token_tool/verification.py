from __future__ import annotations

import re
import time
from typing import Protocol

import requests

from .config import VerificationConfig
from .exceptions import ConfigError, VerificationTimeout


CODE_RE = re.compile(r"\b(\d{6})\b")


class VerificationProvider(Protocol):
    def get_code(self, email: str) -> str:
        ...


class FixedCodeProvider:
    def __init__(self, code: str) -> None:
        self.code = code.strip()

    def get_code(self, email: str) -> str:
        if not self.code:
            raise ConfigError("verification.fixed_code is empty.")
        return self.code


class ManualCodeProvider:
    def get_code(self, email: str) -> str:
        return input(f"Enter the verification code sent to {email}: ").strip()


class GmailScriptProvider:
    def __init__(self, config: VerificationConfig) -> None:
        if not config.gmail_script_url:
            raise ConfigError("verification.gmail_script_url is required for gmail_script.")
        self.url = config.gmail_script_url
        self.poll_seconds = int(config.poll_seconds)
        self.poll_interval_seconds = int(config.poll_interval_seconds)
        self.proxy = config.proxy

    def get_code(self, email: str) -> str:
        print(f"正在等待获取邮箱 {email} 的验证码 (最多等待 {self.poll_seconds} 秒)...")
        start_time_ms = int(time.time() * 1000)
        deadline = time.time() + self.poll_seconds
        last_debug = ""
        proxies = {
            "http": self.proxy,
            "https": self.proxy,
        } if self.proxy else None

        last_print_time = 0
        while time.time() < deadline:
            try:
                params = {"email": email, "timestamp": str(start_time_ms)}
                response = requests.get(self.url, params=params, proxies=proxies, timeout=20)
                response.raise_for_status()
                data = response.json()
                code = self._extract_code(data)
                if code:
                    print(f"成功获取到验证码: {code}")
                    return code
                last_debug = str(data.get("debug") or "")
            except Exception as exc:
                last_debug = str(exc)

            # Print status every 10 seconds or when it changes
            current_time = time.time()
            if current_time - last_print_time >= 10:
                print(f"正在轮询验证码... 最新状态: {last_debug}")
                last_print_time = current_time

            time.sleep(self.poll_interval_seconds)
        raise VerificationTimeout(f"No verification code for {email}. Last response: {last_debug}")

    @staticmethod
    def _extract_code(data: dict) -> str:
        direct = str(data.get("code") or "").strip()
        if direct:
            return direct
        for key in ("body", "text", "message"):
            code = extract_first_code(str(data.get(key) or ""))
            if code:
                return code
        return ""


def build_verification_provider(config: VerificationConfig) -> VerificationProvider:
    if config.source == "manual":
        return ManualCodeProvider()
    if config.source == "fixed":
        return FixedCodeProvider(config.fixed_code)
    if config.source == "gmail_script":
        return GmailScriptProvider(config)
    raise ConfigError(f"Unsupported verification.source: {config.source}")


def extract_first_code(text: str) -> str | None:
    match = CODE_RE.search(text or "")
    return match.group(1) if match else None
