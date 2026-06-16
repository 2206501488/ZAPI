from __future__ import annotations

from pathlib import Path

from .chain import ChainResult, ChainWorkflow
from .config import AppConfig
from .login import LoginWorkflow
from .models import AccountRecord, LoginResult
from .service import SousakuServiceClient
from .storage import AccountStore
from .verification import build_verification_provider


class AutoTokenTool:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.store = AccountStore(
            config.resolve(config.accounts.path),
            config.resolve(config.accounts.tokens_path),
        )
        self.service = SousakuServiceClient(config.service)
        self.verifier = build_verification_provider(config.verification, root_dir=config.root_dir)
        self.login_workflow = LoginWorkflow(config, self.store, self.service, self.verifier)
        self.chain_workflow = ChainWorkflow(
            self.store,
            self.service,
            self.login_workflow,
            config,
            final_reward_task_id=config.chain.final_reward_task_id,
            reward_task_ids=config.chain.reward_task_ids,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "AutoTokenTool":
        return cls(AppConfig.from_file(path))

    def login_once(
        self,
        share_code: str | None = None,
        *,
        keep_browser_open: bool | None = None,
        interactive: bool | None = None,
    ) -> LoginResult:
        return self.login_workflow.login_once(
            share_code=share_code,
            keep_browser_open=keep_browser_open,
            interactive=interactive,
        )

    def chain_login(self, *, bootstrap_if_needed: bool = True) -> ChainResult:
        return self.chain_workflow.run(bootstrap_if_needed=bootstrap_if_needed)

    def list_accounts(self) -> list[AccountRecord]:
        return self.store.list()

    def refresh_accounts(self) -> list[AccountRecord]:
        refreshed: list[AccountRecord] = []
        for account in self.store.list():
            if not account.token:
                refreshed.append(account)
                continue
            try:
                updated = self.service.account_from_token(account.token, fallback_email=account.email)

                # Check and claim pending background tasks
                pending = list(account.pending_tasks)
                if pending:
                    print(f"账号 {account.email} 存在未完成的后台生成任务，正在检查状态...")
                    from .generation import GenerationRunner
                    remaining = GenerationRunner(self.config, self.service).check_and_claim_pending(
                        account.token, pending
                    )
                    updated.pending_tasks = remaining
                else:
                    updated.pending_tasks = []

                self.store.upsert(updated)
                refreshed.append(updated)
            except Exception as exc:
                account.raw = {"refresh_error": str(exc)}
                refreshed.append(account)
        return refreshed
