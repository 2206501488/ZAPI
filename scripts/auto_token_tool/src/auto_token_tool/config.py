from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigError
from .yamlio import load_yaml_mapping


@dataclass
class ServiceConfig:
    name: str = "sousaku"
    provider_id: str = "sousaku"
    signin_base_url: str = "https://sousaku.ai/zh-CN/signin"
    app_base_url: str = "https://sousaku.ai/zh-CN"
    api_base_url: str = "https://api.sousaku.ai"
    cookie_domain: str = ".sousaku.ai"
    shared_storage_key: str = "Sousaku_Shared"
    version_header: str = "2.0.0"
    default_share_code: str = ""


@dataclass
class BrowserConfig:
    channel: str = "msedge"
    headless: bool = False
    keep_open: bool = True
    captcha_wait_seconds: int = 120
    token_wait_seconds: int = 180
    profile_root: str = "runtime/browser-profiles/sousaku"


@dataclass
class VerificationConfig:
    source: str = "manual"
    fixed_code: str = ""
    gmail_script_url: str = ""
    poll_seconds: int = 600
    poll_interval_seconds: int = 5
    max_code_attempts: int = 3
    proxy: str = "http://127.0.0.1:7890"
    outlook_cards_path: str = "data/sousaku/outlook_cards.txt"


@dataclass
class AccountConfig:
    path: str = "data/sousaku/accounts.yaml"
    tokens_path: str = "data/sousaku/tokens.yaml"


@dataclass
class RegistrationConfig:
    email: str = ""
    email_alias_mode: str = "none"
    max_attempts: int = 1
    gmail_max_dots: int = 3


@dataclass
class ChainConfig:
    enabled: bool = False
    final_reward_task_id: str = "task-times-new-user-unlock-rewards"
    reward_task_ids: list[str] = field(default_factory=list)
    reward_claim_task_ids: list[str] = field(default_factory=list)
    sync_plus_to_proxycanvas: bool = False
    proxycanvas_config_path: str = ""
    proxycanvas_server_port_path: str = ""
    open_final_plus_browser: bool = False


@dataclass
class GenerationConfig:
    enabled: bool = False
    wait_for_result: bool = True
    publish_after_success: bool = True
    save_dir: str = "data/sousaku/generated"
    generation_timeout: int = 1200
    poll_interval_seconds: int = 3
    tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PreferencesConfig:
    enable_nsfw: bool = True


@dataclass
class WebUIConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    refresh_on_open: bool = False


@dataclass
class AppConfig:
    service: ServiceConfig = field(default_factory=ServiceConfig)
    browser: BrowserConfig = field(default_factory=BrowserConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    accounts: AccountConfig = field(default_factory=AccountConfig)
    registration: RegistrationConfig = field(default_factory=RegistrationConfig)
    chain: ChainConfig = field(default_factory=ChainConfig)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    preferences: PreferencesConfig = field(default_factory=PreferencesConfig)
    webui: WebUIConfig = field(default_factory=WebUIConfig)
    root_dir: Path = field(default_factory=Path.cwd)
    config_path: Path | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path).resolve()
        if not config_path.exists():
            raise ConfigError(f"Config file not found: {config_path}")
        data = _load_mapping(config_path)
        app = cls(
            service=_coerce(ServiceConfig, data.get("service", {})),
            browser=_coerce(BrowserConfig, data.get("browser", {})),
            verification=_coerce(VerificationConfig, data.get("verification", {})),
            accounts=_coerce(AccountConfig, data.get("accounts", {})),
            registration=_coerce(RegistrationConfig, data.get("registration", {})),
            chain=_coerce(ChainConfig, data.get("chain", {})),
            generation=_coerce(GenerationConfig, data.get("generation", {})),
            preferences=_coerce(PreferencesConfig, data.get("preferences", {})),
            webui=_coerce(WebUIConfig, data.get("webui", {})),
            root_dir=config_path.parent,
            config_path=config_path,
        )
        app.validate()
        return app

    def resolve(self, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else self.root_dir / path

    def update_email_in_file(self, email: str) -> None:
        self.registration.email = email
        if not self.config_path or not self.config_path.exists():
            return
        import re
        content = self.config_path.read_text(encoding="utf-8")
        pattern = r'(registration:\s*(?:\n\s*(?:#[^\n]*)?)*\n\s*email:\s*)[^\n]*'
        new_content = re.sub(pattern, rf'\g<1>{email}', content)
        self.config_path.write_text(new_content, encoding="utf-8")

    def validate(self) -> None:
        provider_id = self.service.provider_id.strip().lower()
        if provider_id not in {"sousaku", "hotgen"}:
            raise ConfigError("service.provider_id must be one of: sousaku, hotgen")
        self.service.provider_id = provider_id
        if self.verification.source not in {"manual", "fixed", "gmail_script", "microsoft_graph"}:
            raise ConfigError("verification.source must be one of: manual, fixed, gmail_script, microsoft_graph")
        if self.registration.email_alias_mode not in {"none", "gmail_dot", "list"}:
            raise ConfigError("registration.email_alias_mode must be one of: none, gmail_dot, list")
        if self.browser.channel not in {"msedge", "chrome", "chromium"}:
            raise ConfigError("browser.channel must be one of: msedge, chrome, chromium")
        if self.registration.max_attempts < 1:
            raise ConfigError("registration.max_attempts must be >= 1")
        if self.verification.max_code_attempts < 1:
            raise ConfigError("verification.max_code_attempts must be >= 1")
        if self.registration.gmail_max_dots < 0:
            raise ConfigError("registration.gmail_max_dots must be >= 0")


def _load_mapping(path: Path) -> dict[str, Any]:
    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError:
            data = load_yaml_mapping(text)
        else:
            data = yaml.safe_load(text)
    else:
        raise ConfigError("Config file must be .yaml or .yml")
    if not isinstance(data, dict):
        raise ConfigError("Config root must be an object.")
    return data


def _coerce(model: type, data: dict[str, Any]) -> Any:
    if not isinstance(data, dict):
        data = {}
    fields = model.__dataclass_fields__.keys()
    return model(**{key: value for key, value in data.items() if key in fields})
