from __future__ import annotations

import re
from pathlib import Path
import time
from typing import Protocol

import requests

from .config import VerificationConfig
from .exceptions import ConfigError, VerificationTimeout, LoginError


CODE_RE = re.compile(r"(?<!#)\b(\d{6})\b")


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
    def __init__(self, config: VerificationConfig, provider_id: str = "sousaku") -> None:
        if not config.gmail_script_url:
            raise ConfigError("verification.gmail_script_url is required for gmail_script.")
        self.url = config.gmail_script_url
        self.poll_seconds = int(config.poll_seconds)
        self.poll_interval_seconds = int(config.poll_interval_seconds)
        self.proxy = config.proxy
        self.provider_id = provider_id.strip().lower() or "sousaku"

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
                params = {
                    "email": email,
                    "timestamp": str(start_time_ms),
                    "provider_id": self.provider_id,
                }
                response = requests.get(self.url, params=params, proxies=proxies, timeout=20)
                response.raise_for_status()
                data = response.json()
                
                debug = data.get("debug") or ""
                subject = data.get("subject") or ""
                
                if "registration notice" in subject.lower() or "registration notice" in debug.lower() or "未能从正文中匹配到" in debug:
                    raise LoginError("该邮箱注册已被目标服务拒绝（系统判定该邮箱不符合注册资格，通常是因为 IP 或设备触发防刷风控）。")
                
                code = self._extract_code(data)
                if code:
                    print(f"成功获取到验证码: {code}")
                    return code
                last_debug = debug
            except LoginError:
                raise
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


class MicrosoftGraphProvider:
    def __init__(self, config: VerificationConfig, root_dir: Path | None = None) -> None:
        path_str = config.outlook_cards_path
        if root_dir and not Path(path_str).is_absolute():
            self.cards_path = root_dir / path_str
        else:
            self.cards_path = Path(path_str)
        self.poll_seconds = int(config.poll_seconds)
        self.poll_interval_seconds = int(config.poll_interval_seconds)
        self.proxy = config.proxy
        self.cards = self._load_cards()

    def _load_cards(self) -> dict[str, dict[str, str]]:
        if not self.cards_path.exists():
            raise ConfigError(f"Outlook cards file not found at: {self.cards_path}")
        cards = {}
        for line in self.cards_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("----")
            if len(parts) >= 4:
                email = parts[0].strip()
                password = parts[1].strip()
                refresh_token = parts[2].strip()
                client_id = parts[3].strip()
                cards[email.lower()] = {
                    "password": password,
                    "refresh_token": refresh_token,
                    "client_id": client_id
                }
        return cards

    def get_code(self, email: str) -> str:
        email_key = email.lower()
        if email_key not in self.cards:
            raise ConfigError(f"No Microsoft Graph credentials (refresh token / client ID) found for email: {email} in card file {self.cards_path}")

        card = self.cards[email_key]
        client_id = card["client_id"]
        refresh_token = card["refresh_token"]

        print(f"正在获取 {email} 的 Microsoft Graph Access Token...")
        access_token = self._get_access_token(client_id, refresh_token)

        print(f"正在等待获取邮箱 {email} 的验证码 (Microsoft Graph API, 最多等待 {self.poll_seconds} 秒)...")
        deadline = time.time() + self.poll_seconds
        proxies = {
            "http": self.proxy,
            "https": self.proxy,
        } if self.proxy else None

        last_print_time = 0
        last_debug = ""
        
        while time.time() < deadline:
            try:
                headers = {
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json"
                }
                url = "https://graph.microsoft.com/v1.0/me/messages?$orderby=receivedDateTime desc&$top=20"
                response = requests.get(url, headers=headers, proxies=proxies, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                messages = data.get("value", [])
                for msg in messages:
                    to_recipients = msg.get("toRecipients", [])
                    to_addresses = [r.get("emailAddress", {}).get("address", "").lower() for r in to_recipients]
                    
                    if email_key in to_addresses:
                        subject = msg.get("subject", "")
                        # 检查是否为拒绝注册的通知信
                        if "registration notice" in subject.lower():
                            raise LoginError("该邮箱注册已被目标服务拒绝（系统判定该邮箱不符合注册资格，通常是因为 IP 或设备触发防刷风控）。")
                        
                        # 仅处理包含 "verification" 的验证码邮件
                        if "verification" not in subject.lower():
                            continue
                            
                        body_preview = msg.get("bodyPreview", "")
                        body_content = msg.get("body", {}).get("content", "")
                        
                        code = extract_first_code(subject) or extract_first_code(body_preview) or extract_first_code(body_content)
                        if code:
                            print(f"成功获取到验证码: {code}")
                            return code
                last_debug = f"Found {len(messages)} messages, but none matched recipient {email_key} or contained a verification code."
            except LoginError:
                raise
            except Exception as exc:
                last_debug = str(exc)

            current_time = time.time()
            if current_time - last_print_time >= 10:
                print(f"正在轮询验证码 (Microsoft Graph)... 最新状态: {last_debug}")
                last_print_time = current_time

            time.sleep(self.poll_interval_seconds)
            
        raise VerificationTimeout(f"No verification code for {email} via Microsoft Graph. Last status: {last_debug}")

    def _get_access_token(self, client_id: str, refresh_token: str) -> str:
        url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://graph.microsoft.com/.default"
        }
        proxies = {
            "http": self.proxy,
            "https": self.proxy,
        } if self.proxy else None
        
        response = requests.post(url, headers=headers, data=payload, proxies=proxies, timeout=15)
        response.raise_for_status()
        return response.json()["access_token"]


def build_verification_provider(
    config: VerificationConfig,
    root_dir: Path | None = None,
    provider_id: str = "sousaku",
) -> VerificationProvider:
    if config.source == "manual":
        return ManualCodeProvider()
    if config.source == "fixed":
        return FixedCodeProvider(config.fixed_code)
    if config.source == "gmail_script":
        return GmailScriptProvider(config, provider_id=provider_id)
    if config.source == "microsoft_graph":
        return MicrosoftGraphProvider(config, root_dir=root_dir)
    raise ConfigError(f"Unsupported verification.source: {config.source}")


def extract_first_code(text: str) -> str | None:
    match = CODE_RE.search(text or "")
    return match.group(1) if match else None
