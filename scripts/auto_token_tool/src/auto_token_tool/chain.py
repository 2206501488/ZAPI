from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from .browser import launch_authenticated_browser
from .config import AppConfig
from .exceptions import LoginError, ServiceAPIError
from .login import LoginWorkflow
from .models import AccountRecord, LoginResult
from .service import SousakuServiceClient
from .storage import AccountStore


@dataclass
class ChainResult:
    success: bool
    inviter: AccountRecord | None = None
    invited: AccountRecord | None = None
    bootstrapped: bool = False
    error: str = ""


class ChainWorkflow:
    def __init__(
        self,
        store: AccountStore,
        service: SousakuServiceClient,
        login_workflow: LoginWorkflow,
        config: AppConfig,
        final_reward_task_id: str,
        reward_task_ids: list[str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.login_workflow = login_workflow
        self.config = config
        self.final_reward_task_id = final_reward_task_id
        self.reward_task_ids = reward_task_ids or []

    def run(self, *, bootstrap_if_needed: bool = True) -> ChainResult:
        inviter = None
        invited = None
        bootstrapped = False
        try:
            inviter = self._find_refreshed_free_inviter()
            if inviter is None:
                if not bootstrap_if_needed:
                    raise LoginError("No Free inviter account found.")
                print("[Orchestrator] 本地数据库中无可用的 Free 账号，将进入 Bootstrap 双注册模式...")
                bootstrapped = True
                inviter = self._bootstrap_inviter()

            if not inviter.share_code:
                raise LoginError(f"Inviter account has no share_code: {inviter.email}")

            print(f"正在使用账号 {inviter.email} 的邀请码注册一个新账号...")
            invited_result = self.login_workflow.login_once(
                share_code=inviter.share_code,
                keep_browser_open=False,
                interactive=False,
            )
            if not invited_result.success or not invited_result.account:
                raise LoginError(invited_result.error or "Invited account registration failed.")
            invited = invited_result.account

            self._complete_optional_rewards(inviter.token)

            # Sync inviter from store in case pending tasks were modified
            for acc in self.store.list():
                if acc.email.lower() == inviter.email.lower():
                    inviter = acc
                    break

            # Wait for inviter's own pending tasks if wait_for_result is enabled
            if self.config.generation.wait_for_result and inviter.pending_tasks:
                print(f"正在等待邀请人账号 {inviter.email} 的后台生成任务完成...")
                import time
                from .generation import GenerationRunner

                runner = GenerationRunner(self.config, self.service)
                deadline = time.time() + int(self.config.generation.generation_timeout)
                interval = float(self.config.generation.poll_interval_seconds)
                while inviter.pending_tasks and time.time() < deadline:
                    inviter.pending_tasks = runner.check_and_claim_pending(
                        inviter.token, inviter.pending_tasks
                    )
                    if inviter.pending_tasks:
                        time.sleep(interval)
                self.store.upsert(inviter)

            # Claim final upgrade reward with retries
            refreshed = inviter
            max_retries = 3
            retry_delay = 5.0
            for attempt in range(1, max_retries + 1):
                try:
                    self.service.claim_reward(inviter.token, self.final_reward_task_id)
                except Exception as exc:
                    print(f"Claim final reward attempt {attempt} failed: {exc}")

                refreshed = self.service.account_from_token(inviter.token, fallback_email=inviter.email)
                self.store.upsert(refreshed)
                if refreshed.package_level.lower() == "plus":
                    break

                if attempt < max_retries:
                    print(f"邀请人账号升级验证未通过 (当前等级: {refreshed.package_level})，将在 {retry_delay} 秒后进行第 {attempt + 1} 次尝试...")
                    import time
                    time.sleep(retry_delay)

            if refreshed.package_level.lower() != "plus":
                raise LoginError(
                    f"Inviter account was not upgraded to Plus: "
                    f"{refreshed.email} level={refreshed.package_level}"
                )
            print("\033[1;32m🎉 链式登录完成！邀请人已成功升级为 Plus！\033[0m")
            print("邀请人账号 (Inviter):")
            print(f"  email: {refreshed.email}")
            print(f"  level: {refreshed.package_level}")
            if refreshed.token:
                print(f"  \033[1;32mfull_token: \033[0m\033[1;36m{refreshed.token}\033[0m")
            if invited:
                print("新注册小号 (Invited):")
                print(f"  email: {invited.email}")
                if invited.token:
                    print(f"  \033[1;32mfull_token: \033[0m\033[1;36m{invited.token}\033[0m")
            print()

            self._sync_and_open_final_plus(refreshed)
            return ChainResult(
                success=True,
                inviter=refreshed,
                invited=invited,
                bootstrapped=bootstrapped,
            )
        except Exception as exc:
            return ChainResult(
                success=False,
                error=str(exc),
                inviter=inviter,
                invited=invited,
                bootstrapped=bootstrapped,
            )

    def _bootstrap_inviter(self) -> AccountRecord:
        print("正在注册主账号 A。")
        result: LoginResult = self.login_workflow.login_once(
            keep_browser_open=False,
            interactive=False,
        )
        if not result.success or not result.account:
            raise LoginError(result.error or "Bootstrap inviter registration failed.")
        if not result.account.share_code:
            refreshed = self.service.account_from_token(result.account.token, fallback_email=result.email)
            self.store.upsert(refreshed)
            result.account = refreshed
        print(f"主账号 A 注册成功: {result.account.email}, 邀请码: {result.account.share_code}")
        return result.account

    def _find_refreshed_free_inviter(self) -> AccountRecord | None:
        accounts = self.store.list()
        excluded_emails: set[str] = set()
        for account in reversed(accounts):
            if not account.token:
                continue
            if account.email in excluded_emails:
                continue
            # Optimization: Skip API refresh if local record is already Plus
            if account.package_level.lower() == "plus":
                print(f"[Orchestrator] 本地数据表明账号 {account.email} 已经是 Plus，跳过状态刷新。")
                self._sync_plus_token(account.token)
                continue

            try:
                print(f"[Orchestrator] 找到候选账号: {account.email}，正在刷新其状态...")
                refreshed = self.service.account_from_token(account.token, fallback_email=account.email)

                # Check and claim pending background generation tasks
                pending = list(account.pending_tasks)
                if pending:
                    print(f"账号 {account.email} 存在未完成的后台生成任务，正在检查状态...")
                    from .generation import GenerationRunner
                    remaining = GenerationRunner(self.config, self.service).check_and_claim_pending(
                        account.token, pending
                    )
                    refreshed.pending_tasks = remaining
                else:
                    refreshed.pending_tasks = []

                self.store.upsert(refreshed)
            except Exception as exc:
                print(f"Refresh account skipped for {account.email}: {exc}")
                excluded_emails.add(account.email)
                continue
            if refreshed.package_level.lower() == "plus":
                print(f"[Orchestrator] 账号 {refreshed.email} 已是 Plus，尝试同步后继续寻找 Free 账号。")
                self._sync_plus_token(refreshed.token)
                continue
            if refreshed.package_level.lower() == "free" and refreshed.share_code:
                return refreshed
            if refreshed.package_level.lower() == "free" and not refreshed.share_code:
                print(f"Free account has no share_code, skipped: {refreshed.email}")
        return None

    def _complete_optional_rewards(self, token: str) -> None:
        for task_id in self.reward_task_ids:
            try:
                self.service.complete_reward(token, task_id)
            except ServiceAPIError as exc:
                print(f"Reward completion skipped for {task_id}: {exc}")

    def _claim_final_reward(self, token: str) -> None:
        if not self.final_reward_task_id:
            return
        try:
            self.service.claim_reward(token, self.final_reward_task_id)
        except ServiceAPIError as exc:
            print(f"Final reward claim skipped: {exc}")

    def _sync_and_open_final_plus(self, account: AccountRecord) -> None:
        self._sync_plus_token(account.token)
        if self.config.chain.open_final_plus_browser:
            launch_authenticated_browser(self.config, account.token, account.email)

    def _sync_plus_token(self, token: str) -> None:
        if not self.config.chain.sync_plus_to_proxycanvas:
            return
        if self._sync_token_via_api(token):
            return
        print("[ProxyCanvas] 后端 API 不可用，回退到直接写入配置文件...")
        self._sync_token_via_file(token)

    def _sync_token_via_api(self, token: str) -> bool:
        import requests

        config_path = self.config.chain.proxycanvas_config_path
        server_port_path = self.config.chain.proxycanvas_server_port_path
        if not config_path and not server_port_path:
            return False
        port = self._proxycanvas_port()
        url = f"http://localhost:{port}/api/provider-accounts/sousaku/tokens"
        try:
            response = requests.post(url, json={"tokens": [token]}, timeout=5)
            if response.status_code != 200:
                print(f"[ProxyCanvas API] 接口返回 HTTP {response.status_code}")
                return False
            data = response.json()
            if not data.get("success"):
                print(f"[ProxyCanvas API] 接口返回失败: {data.get('error')}")
                return False
            added = data.get("added", 0)
            skipped = data.get("skipped", 0)
            if added:
                print(f"[ProxyCanvas API] Token 已通过后端 API 导入并自动刷新账号信息 (port={port})")
            else:
                print(f"[ProxyCanvas API] Token 已存在于账号池中 (skipped={skipped})")
            return True
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return False
        except Exception as exc:
            print(f"[ProxyCanvas API] 调用异常: {exc}")
            return False

    def _sync_token_via_file(self, token: str) -> None:
        raw_path = self.config.chain.proxycanvas_config_path
        if not raw_path:
            print("[ProxyCanvas] 未配置 proxycanvas_config_path，跳过文件同步。")
            return
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.config.resolve(raw_path)
        if not path.exists():
            print(f"[ProxyCanvas] 配置文件不存在: {path}，跳过同步。")
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            tokens = data.get("tokens", [])
            if not isinstance(tokens, list):
                tokens = []
            if token not in tokens:
                tokens.insert(0, token)
                data["tokens"] = tokens
                path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print("[ProxyCanvas 文件] 已直接写入 Token 到配置文件。")
            else:
                print("[ProxyCanvas 文件] Token 已存在于配置文件中。")
        except Exception as exc:
            print(f"[ProxyCanvas 文件] 写入失败: {exc}")

    def _proxycanvas_port(self) -> int:
        raw_path = self.config.chain.proxycanvas_server_port_path
        if not raw_path:
            return 5700
        path = Path(raw_path)
        if not path.is_absolute():
            path = self.config.resolve(raw_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data.get("port", 5700))
        except Exception:
            return 5700
