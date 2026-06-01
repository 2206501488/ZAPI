from __future__ import annotations

from typing import Any

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .config import AppConfig
from .exceptions import LoginError


EMAIL_SELECTOR = 'input[name="user_email"], input[type="email"]'
CHECKBOX_SELECTOR = 'input[type="checkbox"]'
CONTINUE_SELECTOR = 'form button[type="submit"], button:has-text("继续")'
CODE_SELECTOR = (
    "input[autocomplete='one-time-code'], "
    "input[name*='code' i], "
    "input[id*='code' i], "
    "input[aria-label*='验证码'], "
    "input[placeholder*='验证码'], "
    "input[type='tel'], "
    "input[inputmode='numeric']"
)
LOGIN_SELECTOR = "button:has-text('登录'), form button[type='submit']"
RESEND_SELECTOR = (
    "button:has-text('重新发送'), "
    "a:has-text('重新发送'), "
    "button:has-text('Resend'), "
    "a:has-text('Resend')"
)
TURNSTILE_SELECTOR = 'input[name="cf-turnstile-response"]'
VERIFY_EMAIL_ERROR_TEXTS = (
    "Verify Email Error",
    "Invalid verification code",
    "verification code is invalid",
    "验证码错误",
    "验证码无效",
    "验证码不正确",
)


def parse_share_code(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        query = parse_qs(urlparse(value).query)
        codes = query.get("share_code") or query.get("shareCode")
        if codes and codes[0].strip():
            return codes[0].strip()
        raise LoginError("The URL does not contain share_code.")
    return value


def build_signin_url(config: AppConfig, share_code: str | None = None) -> str:
    code = parse_share_code(share_code or "") or config.service.default_share_code
    if not code:
        return config.service.signin_base_url
    return f"{config.service.signin_base_url}?share_code={code}"


class BrowserSession:
    def __init__(self, config: AppConfig, run_name: str, keep_open: bool | None = None) -> None:
        self.config = config
        self.run_name = run_name
        self.profile_dir = make_run_profile_dir(config.resolve(config.browser.profile_root), run_name)
        self.keep_open = keep_open if keep_open is not None else config.browser.keep_open
        self._playwright = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.process: subprocess.Popen | None = None

    def __enter__(self) -> "BrowserSession":
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        if self.config.browser.channel in {"msedge", "chrome"}:
            return self._enter_real_browser()
        return self._enter_playwright_chromium()

    def _enter_real_browser(self) -> "BrowserSession":
        browser_exe = find_browser_exe(self.config.browser.channel)
        port = find_free_port()
        private_flag = "--inprivate" if self.config.browser.channel == "msedge" else "--incognito"
        args = [
            browser_exe,
            private_flag,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-extensions",
            "--disable-component-extensions-with-background-pages",
            "--disable-features=msEdgeSignIn,EdgeSigninIntercept,msSingleSignOnOSForPrimaryAccount,msAADWebSSO",
            "--disable-popup-blocking",
            "--disable-session-crashed-bubble",
            "--start-maximized",
            "--window-position=0,0",
            "about:blank",
        ]
        if sys.platform == "win32":
            self.process = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        endpoint = f"http://127.0.0.1:{port}"
        last_error: Exception | None = None
        for _ in range(60):
            try:
                self.browser = self._playwright.chromium.connect_over_cdp(endpoint)
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.25)
        if self.browser is None:
            raise LoginError(f"Could not connect to real browser over CDP: {last_error}")

        self.context = self.browser.contexts[0] if self.browser.contexts else self.browser.new_context()
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def _enter_playwright_chromium(self) -> "BrowserSession":
        launch_kwargs = {
            "headless": self.config.browser.headless,
            "args": ["--no-first-run", "--no-default-browser-check"],
        }
        self.context = self._playwright.chromium.launch_persistent_context(
            str(self.profile_dir),
            **launch_kwargs,
        )
        self.page = self.context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        keep = self.keep_open and exc_type is None
        if not keep:
            self.close(remove_profile=True)
            return
        print(f"Browser is open for inspection. Profile: {self.profile_dir}")
        closed_by_user = False
        try:
            if self.page:
                keep_browser_session_alive(self.page)
        except KeyboardInterrupt:
            print("\n收到退出信号，正在关闭浏览器并清理临时文件...")
            closed_by_user = True
        finally:
            self.close(remove_profile=closed_by_user)

    def close(self, *, remove_profile: bool = False) -> None:
        if not remove_profile:
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            return

        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass

        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                    self.process.wait(timeout=2)
                except Exception:
                    pass

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

        if remove_profile and self.profile_dir.exists():
            remove_profile_dir(self.profile_dir)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_browser_exe(channel: str) -> str:
    candidates: list[str]
    if channel == "msedge":
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
    elif channel == "chrome":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
    else:
        raise LoginError(f"Real browser mode does not support channel: {channel}")

    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise LoginError(f"Cannot find browser executable for channel={channel}.")


def remove_profile_dir(profile_dir: Path) -> None:
    for attempt in range(1, 6):
        try:
            shutil.rmtree(profile_dir)
            return
        except PermissionError:
            if attempt == 5:
                print(f"Browser profile is still locked, delete later if needed: {profile_dir}")
                return
            time.sleep(1)
        except FileNotFoundError:
            return


def make_run_profile_dir(root: Path, run_name: str) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for index in range(1, 1000):
        path = root / f"{run_name}-{stamp}-{index:03d}"
        if not path.exists():
            return path
    raise LoginError("Could not allocate a browser profile directory.")


def wait_until_enabled(target, page: Page, timeout_seconds: int = 8) -> bool:
    deadline = time.time() + timeout_seconds
    locator = page.locator(target).first if isinstance(target, str) else target
    while time.time() < deadline:
        try:
            if locator.is_visible() and locator.is_enabled():
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def wait_for_turnstile(page: Page, timeout_seconds: int) -> None:
    print("等待 Cloudflare 人机验证完成。")
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = page.locator(TURNSTILE_SELECTOR).first
            if response.count() and (response.get_attribute("value") or "").strip():
                print("Cloudflare 人机验证已成功。")
                return
        except Exception:
            pass
        page.wait_for_timeout(500)

    print("没有等到 Cloudflare 验证结果，刷新页面再试一次。")
    page.reload(wait_until="domcontentloaded", timeout=60_000)
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = page.locator(TURNSTILE_SELECTOR).first
            if response.count() and (response.get_attribute("value") or "").strip():
                print("刷新后 Cloudflare 人机验证已成功。")
                return
        except Exception:
            pass
        page.wait_for_timeout(500)
    print("仍然没有等到 Cloudflare 验证结果。请确认页面下方是否显示成功。")


def fill_code(page: Page, code: str) -> None:
    if not code:
        print("未输入验证码，浏览器会保持打开，等待你手动完成后续步骤。")
        return

    print("等待验证码输入框出现。")
    first = page.locator(CODE_SELECTOR).first
    first.wait_for(state="visible", timeout=120_000)
    inputs = page.locator(CODE_SELECTOR)
    visible = []
    for index in range(inputs.count()):
        item = inputs.nth(index)
        if item.is_visible() and item.is_enabled():
            visible.append(item)
    if len(visible) > 1 and len(code) >= len(visible):
        for item, char in zip(visible, code):
            item.fill(char)
    else:
        first.fill(code)
    print("已填写验证码。")

    login_button = page.locator(LOGIN_SELECTOR).first
    login_button.wait_for(state="visible", timeout=30_000)
    if wait_until_enabled(login_button, page):
        login_button.click()
    else:
        page.keyboard.press("Enter")
    print("已点击登录。")


def wait_for_verify_email_error(page: Page, timeout_seconds: int = 8) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            body = page.locator("body").inner_text(timeout=1000)
            lowered = body.lower()
            if any(text.lower() in lowered for text in VERIFY_EMAIL_ERROR_TEXTS):
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


def resend_verification_code(page: Page) -> bool:
    resend = page.locator(RESEND_SELECTOR).first
    try:
        resend.wait_for(state="visible", timeout=15_000)
    except Exception:
        return False
    if not wait_until_enabled(resend, page, timeout_seconds=15):
        return False
    resend.click()
    print("验证码错误，已点击重新发送。")
    page.wait_for_timeout(1000)
    return True


def extract_token(page: Page, seconds: int, api_base_url: str = "https://api.sousaku.ai") -> str | None:
    captured: dict[str, str] = {}

    def is_valid_token(val: Any) -> bool:
        if not val:
            return False
        s = str(val).strip().lower()
        return s not in {"null", "undefined", ""}

    def on_request(request):
        if "api." not in request.url:
            return
        auth = request.headers.get("authorization") or request.headers.get("Authorization")
        if auth:
            val = auth.removeprefix("Bearer ").strip()
            if is_valid_token(val):
                captured["token"] = val

    page.on("request", on_request)
    deadline = time.time() + seconds
    while time.time() < deadline:
        if captured.get("token"):
            return captured["token"]
        try:
            for cookie in page.context.cookies():
                if cookie.get("name") == "pp_user_token" and cookie.get("value"):
                    val = str(cookie["value"])
                    if is_valid_token(val):
                        return val
        except Exception:
            pass
        try:
            token = page.evaluate(
                """() => {
                    const names = ["pp_user_token", "token", "access_token", "authorization"];
                    for (const storage of [localStorage, sessionStorage]) {
                        for (const name of names) {
                            const value = storage.getItem(name);
                            if (value) return value;
                        }
                        for (let i = 0; i < storage.length; i += 1) {
                            const key = storage.key(i);
                            if (key && key.toLowerCase().includes("token")) {
                                const value = storage.getItem(key);
                                if (value) return value;
                            }
                        }
                    }
                    return "";
                }"""
            )
            if is_valid_token(token):
                return str(token)
        except Exception:
            pass

        try:
            page.evaluate(
                """() => {
                    if (window.__autoTokenFetchLoggerInstalled) return;
                    window.__autoTokenFetchLoggerInstalled = true;
                    const oldFetch = window.fetch;
                    window.fetch = function(...args) {
                        return oldFetch.apply(this, args);
                    };
                }"""
            )
        except Exception:
            pass

        try:
            api_url = api_base_url.rstrip("/") + "/v1/user"
            page.evaluate(
                """(url) => {
                    fetch(url, {
                        method: "GET",
                        credentials: "include",
                        headers: {"content-type": "application/json"}
                    }).catch(() => {});
                }""",
                api_url,
            )
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return None


def install_external_popup_guard(page: Page) -> None:
    script = r"""
    (() => {
      if (window.__autoTokenPopupGuardInstalled) return;
      window.__autoTokenPopupGuardInstalled = true;
      const originalOpen = window.open.bind(window);
      const openRealUrl = (url, target, features) => {
        if (!url || url === "about:blank") return null;
        return originalOpen(url, target || "_blank", features || "noopener,noreferrer");
      };
      window.open = function(url, target, features) {
        if (url && url !== "about:blank") {
          return openRealUrl(url, target, features);
        }
        const fakeWindow = {};
        const fakeLocation = {};
        Object.defineProperty(fakeLocation, "href", {
          get() { return "about:blank"; },
          set(value) { openRealUrl(value, target, features); }
        });
        fakeLocation.assign = (value) => openRealUrl(value, target, features);
        fakeLocation.replace = (value) => openRealUrl(value, target, features);
        fakeWindow.location = fakeLocation;
        fakeWindow.focus = () => {};
        fakeWindow.close = () => {};
        return fakeWindow;
      };
    })();
    """
    try:
        page.add_init_script(script)
        page.evaluate(script)
    except Exception as exc:
        print(f"Popup guard install failed: {exc}")


def install_blank_popup_cleanup(page: Page) -> None:
    def cleanup_popup(popup):
        try:
            popup.wait_for_load_state("domcontentloaded", timeout=3000)
        except Exception:
            pass
        try:
            if popup.url == "about:blank":
                popup.close()
                try:
                    page.keyboard.press("Escape")
                except Exception:
                    pass
        except Exception:
            pass

    def on_new_page(new_page):
        cleanup_popup(new_page)

    page.context.on("page", on_new_page)
    page.on("popup", on_new_page)


def enable_nsfw_preference(page: Page, app_url: str) -> None:
    for attempt in range(1, 4):
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
            page.evaluate("""() => {
                let shared = localStorage.getItem("Sousaku_Shared");
                let parsed = {};
                if (shared) {
                  try { parsed = JSON.parse(shared); } catch (e) {}
                }
                if (!parsed.state) parsed.state = {};
                if (!parsed.state.preference) parsed.state.preference = {};
                parsed.state.preference.allowNSFWContent = true;
                localStorage.setItem("Sousaku_Shared", JSON.stringify(parsed));
            }""")
            page.goto(app_url, wait_until="domcontentloaded", timeout=10000)
            return
        except Exception as exc:
            if attempt == 3:
                print(f"Enable NSFW preference failed: {exc}")
            else:
                page.wait_for_timeout(1000)


def keep_browser_session_alive(page: Page) -> None:
    print("浏览器会保持打开。需要结束脚本时，在这个命令行窗口按 Ctrl+C。")
    try:
        while True:
            page.wait_for_timeout(1000)
    except KeyboardInterrupt:
        raise


def launch_authenticated_browser(config: AppConfig, token: str, label: str = "plus") -> None:
    print(f"\n正在打开已登录并启用 NSFW 的浏览器窗口: {label}")
    session = BrowserSession(config, f"final-{safe_run_name(label)}")
    browser = session.__enter__()
    try:
        page = browser.page
        if page is None:
            raise LoginError("Browser page was not created.")
        app_url = config.service.app_base_url.rstrip("/")
        signin_url = config.service.signin_base_url
        page.goto(signin_url, wait_until="domcontentloaded", timeout=60_000)
        try:
            page.context.add_cookies([
                {
                    "name": "pp_user_token",
                    "value": token,
                    "domain": ".sousaku.ai",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                    "sameSite": "Lax",
                }
            ])
        except Exception:
            pass
        page.evaluate(
            """(token) => {
                localStorage.setItem("pp_user_token", token);
                document.cookie = "pp_user_token=" + token + "; path=/; domain=.sousaku.ai; max-age=31536000";
                let shared = localStorage.getItem("Sousaku_Shared") || "{}";
                let parsed = {};
                try { parsed = JSON.parse(shared); } catch (e) {}
                if (!parsed.state) parsed.state = {};
                if (!parsed.state.preference) parsed.state.preference = {};
                parsed.state.preference.allowNSFWContent = true;
                localStorage.setItem("Sousaku_Shared", JSON.stringify(parsed));
            }""",
            token,
        )
        page.goto(app_url, wait_until="domcontentloaded", timeout=60_000)
        print("浏览器登录与 NSFW 注入完成。")
        keep_browser_session_alive(page)
    finally:
        session.close(remove_profile=True)


def safe_run_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in value)[:80] or "plus"
