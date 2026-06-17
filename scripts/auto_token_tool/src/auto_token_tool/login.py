from __future__ import annotations

from .browser import (
    CHECKBOX_SELECTOR,
    CONTINUE_SELECTOR,
    EMAIL_SELECTOR,
    BrowserSession,
    build_signin_url,
    enable_nsfw_preference,
    extract_token,
    fill_code,
    install_blank_popup_cleanup,
    install_external_popup_guard,
    wait_for_turnstile,
    wait_until_enabled,
)
from .config import AppConfig
from .exceptions import LoginError
from .models import LoginResult
from .service import SousakuServiceClient
from .storage import AccountStore, next_gmail_dot_alias
from .verification import VerificationProvider
from .generation import GenerationRunner
from pathlib import Path


def load_outlook_card_emails(path: str | Path) -> list[str]:
    from pathlib import Path
    p = Path(path)
    if not p.exists():
        return []
    emails = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("----")
        if parts:
            emails.append(parts[0].strip())
    return emails


class LoginWorkflow:
    def __init__(
        self,
        config: AppConfig,
        store: AccountStore,
        service: SousakuServiceClient,
        verifier: VerificationProvider,
    ) -> None:
        self.config = config
        self.store = store
        self.service = service
        self.verifier = verifier

    def login_once(
        self,
        share_code: str | None = None,
        *,
        keep_browser_open: bool | None = None,
        interactive: bool | None = None,
    ) -> LoginResult:
        last_error = ""
        for attempt in range(self.config.registration.max_attempts):
            try:
                return self._login_attempt(
                    share_code,
                    attempt,
                    keep_browser_open=keep_browser_open,
                    interactive=interactive,
                )
            except Exception as exc:
                last_error = str(exc)
                print(f"Login attempt {attempt + 1} failed: {last_error}")
                if "防刷风控" in last_error or "risk control" in last_error.lower():
                    print("检测到 IP 或设备触发防刷风控拦截，停止后续尝试。请更换 IP/代理后重试。")
                    break
        return LoginResult(success=False, error=last_error)

    def _login_attempt(
        self,
        share_code: str | None,
        attempt: int,
        *,
        keep_browser_open: bool | None = None,
        interactive: bool | None = None,
    ) -> LoginResult:
        run_name = f"login-{attempt + 1:03d}"
        signin_url = build_signin_url(self.config, share_code)
        with BrowserSession(self.config, run_name, keep_open=keep_browser_open) as browser:
            page = browser.page
            if page is None:
                raise LoginError("Browser page was not created.")
            install_external_popup_guard(page)
            install_blank_popup_cleanup(page)
            page.goto(signin_url, wait_until="domcontentloaded", timeout=60_000)

            email_input = page.locator(EMAIL_SELECTOR).first
            email_input.wait_for(state="visible", timeout=30_000)
            wait_for_turnstile(page, self.config.browser.captcha_wait_seconds)

            email = self._resolve_email(attempt)
            # self.config.update_email_in_file(email)
            print(f"本轮使用邮箱: {email}")
            email_input = page.locator(EMAIL_SELECTOR).first
            email_input.wait_for(state="visible", timeout=30_000)
            email_input.fill(email)
            print("已填写邮箱。")

            checkbox = page.locator(CHECKBOX_SELECTOR).first
            checkbox.wait_for(state="attached", timeout=30_000)
            if not checkbox.is_checked():
                checkbox.check(force=True)
            print("已勾选同意。")

            if not wait_until_enabled(CONTINUE_SELECTOR, page, self.config.browser.captcha_wait_seconds):
                print("继续按钮暂时还是禁用状态，重新触发同意勾选后继续等待。")
                checkbox.click(force=True)
                page.wait_for_timeout(500)
                if not checkbox.is_checked():
                    checkbox.check(force=True)
                page.wait_for_timeout(1000)
            if not wait_until_enabled(CONTINUE_SELECTOR, page, self.config.browser.captcha_wait_seconds):
                raise LoginError("Continue button was not enabled before timeout.")
            page.locator(CONTINUE_SELECTOR).first.click()

            code = self.verifier.get_code(email)
            if not code:
                raise LoginError("No verification code was provided.")
            fill_code(page, code)

            token = extract_token(
                page,
                self.config.browser.token_wait_seconds,
                api_base_url=self.config.service.api_base_url,
            )
            if not token:
                raise LoginError("No token was captured after login.")

            account = self._fetch_account_after_login(token, email)
            self.store.upsert(account)
            account = self._after_login(token, email, page, interactive=interactive) or account
            return LoginResult(success=True, email=email, token=token, account=account)

    def _resolve_email(self, attempt: int) -> str:
        mode = self.config.registration.email_alias_mode
        if mode == "gmail_dot":
            email = self.config.registration.email.strip()
            if not email:
                raise LoginError("registration.email is required.")
            used = {account.email.lower() for account in self.store.list()}
            return next_gmail_dot_alias(
                email, used, offset=attempt, max_dots=self.config.registration.gmail_max_dots
            )
        elif mode == "list":
            card_path = self.config.verification.outlook_cards_path
            resolved_path = self.config.resolve(card_path)
            emails = load_outlook_card_emails(resolved_path)
            if not emails:
                raise LoginError(f"No emails found in card file: {resolved_path}")
            
            used = {account.email.lower() for account in self.store.list()}
            available_emails = [e for e in emails if e.lower() not in used]
            if not available_emails:
                raise LoginError(f"All emails in card file ({resolved_path}) have already been registered.")
            
            if attempt < len(available_emails):
                return available_emails[attempt]
            else:
                return available_emails[-1]
        else:
            email = self.config.registration.email.strip()
            if not email:
                raise LoginError("registration.email is required.")
            return email

    def _after_login(self, token: str, email: str, page, *, interactive: bool | None = None) -> AccountRecord | None:
        is_interactive = interactive if interactive is not None else True
        successful_claims: set[str] = set()
        if self.config.chain.reward_task_ids:
            print("正在自动完成 Twitter/Discord 社交媒体关注任务...")
            self._complete_rewards(token, self.config.chain.reward_task_ids)

            print("正在领取 Twitter/Discord 任务的积分奖励以获得生成额度...")
            social_claims = [
                task_id
                for task_id in self.config.chain.reward_task_ids
                if task_id in self.config.chain.reward_claim_task_ids
            ]
            successful_claims.update(self._claim_rewards(token, social_claims))

        submitted_tasks: list[str] = []
        if self.config.generation.enabled:
            try:
                print("正在自动生成测试图片和视频...")
                submitted_tasks = GenerationRunner(self.config, self.service).run(
                    token, wait_for_result=is_interactive
                )
            except Exception as exc:
                print(f"Generation tasks failed: {exc}")

            if is_interactive:
                print("正在领取生成任务的积分奖励...")
                generation_claims = [
                    task_id
                    for task_id in self.config.chain.reward_claim_task_ids
                    if task_id not in self.config.chain.reward_task_ids
                    and task_id != self.config.chain.final_reward_task_id
                ]
                successful_claims.update(self._claim_rewards(token, generation_claims))

        plus_activated = False
        final_task_id = self.config.chain.final_reward_task_id
        if final_task_id:
            print(f"正在尝试领取最终新手解锁奖励 ({final_task_id}) 以升级为 Plus...")
            if self._claim_reward(token, final_task_id):
                successful_claims.add(final_task_id)
                plus_activated = True

        refreshed = self._refresh_account(token, email)
        if refreshed:
            plus_activated = plus_activated or refreshed.package_level.lower() == "plus"
            if submitted_tasks and not is_interactive:
                refreshed.pending_tasks = submitted_tasks
            self.store.upsert(refreshed)

        if not plus_activated and is_interactive:
            while True:
                print("\n" + "="*60)
                print("[提示] Plus 会员还未激活（这通常是因为您还没有邀请新用户注册）。")
                print("如果您已经成功邀请了新用户，请在此窗口按 ENTER 键触发重试，重新领取所有奖励...")
                print("如果您想放弃升级并直接退出，请输入 'q' 并按 ENTER 键。")
                print("="*60)

                user_choice = input("请选择 (直接按 ENTER 重试 / 输入 q 退出): ").strip()
                if user_choice.lower() == 'q':
                    print("用户选择放弃重试。")
                    break

                print("正在尝试重新自动领取可能失败的所有任务奖励...")
                claims = [t for t in self.config.chain.reward_claim_task_ids if t not in successful_claims]
                if claims:
                    claimed = self._claim_rewards(token, claims)
                    successful_claims.update(claimed)

                if final_task_id and final_task_id not in successful_claims:
                    print(f"正在重新尝试领取最终新手解锁奖励 ({final_task_id}) 以升级为 Plus...")
                    if self._claim_reward(token, final_task_id):
                          plus_activated = True
                          successful_claims.add(final_task_id)

                refreshed = self._refresh_account(token, email)
                if refreshed:
                    plus_activated = plus_activated or refreshed.package_level.lower() == "plus"
                    self.store.upsert(refreshed)

                if plus_activated:
                    print("🎉 Plus 会员已成功激活！")
                    break
                else:
                    print("❌ 激活校验未通过，账户等级仍为 Free。请确认邀请是否已完成。")

        if self.config.preferences.enable_nsfw:
            enable_nsfw_preference(
                page,
                self.config.service.app_base_url,
                self.config.service.shared_storage_key,
            )
        return refreshed

    def _fetch_account_after_login(self, token: str, email: str):
        try:
            return self.service.account_from_token(token, fallback_email=email)
        except Exception as exc:
            print(f"获取用户信息失败，先保存 token，后续可刷新账号状态: {exc}")
            from .models import AccountRecord

            return AccountRecord(email=email, token=token, package_level="unknown")

    def _refresh_account(self, token: str, email: str):
        try:
            print("获取用户信息以验证当前账号状态...")
            return self.service.account_from_token(token, fallback_email=email)
        except Exception as exc:
            print(f"获取/更新用户信息失败: {exc}")
            return None

    def _complete_rewards(self, token: str, task_ids: list[str]) -> None:
        for task_id in task_ids:
            try:
                self.service.complete_reward(token, task_id)
                print(f"已完成奖励任务: {task_id}")
            except Exception as exc:
                print(f"Complete reward skipped for {task_id}: {exc}")

    def _claim_rewards(self, token: str, task_ids: list[str]) -> list[str]:
        claimed: list[str] = []
        for task_id in task_ids:
            if self._claim_reward(token, task_id):
                claimed.append(task_id)
        return claimed

    def _claim_reward(self, token: str, task_id: str) -> bool:
        try:
            if self.service.claim_reward(token, task_id):
                print(f"已领取奖励任务: {task_id}")
                return True
        except Exception as exc:
            print(f"Claim reward skipped for {task_id}: {exc}")
        return False
