from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .config import AppConfig
from .sdk import AutoTokenTool
from .webui import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="auto-token-tool")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("login", help="Run one browser-assisted login.")
    sub.add_parser("chain", help="Run chain login flow.")
    sub.add_parser("accounts", help="List stored accounts.")
    sub.add_parser("webui", help="Start local account status WebUI.")
    return parser


def main(argv: list[str] | None = None) -> int:
    import os
    if os.name == "nt":
        os.system("")  # Enable ANSI terminal colors on Windows console

    args = build_parser().parse_args(argv)
    command = args.command or prompt_command()
    tool = load_tool_interactively()

    if command == "login":
        default_code = tool.config.service.default_share_code
        prompt = "请输入邀请链接或邀请码"
        if default_code:
            prompt += f"，直接回车使用默认 {default_code}"
        share_code = prompt_text(prompt + ": ")
        result = tool.login_once(share_code=share_code, keep_browser_open=True, interactive=True)
        if not result.success:
            print(result.error, file=sys.stderr)
            return 1
        print("登录成功")
        print_account(result.account)
        return 0

    if command == "chain":
        result = tool.chain_login(bootstrap_if_needed=True)
        if not result.success:
            print(result.error, file=sys.stderr)
            if result.inviter:
                print("inviter:")
                print_account(result.inviter, indent="  ")
            if result.invited:
                print("invited:")
                print_account(result.invited, indent="  ")
            return 1
        print("链式登录完成")
        print(f"bootstrapped: {result.bootstrapped}")
        print("inviter:")
        print_account(result.inviter, indent="  ")
        print("invited:")
        print_account(result.invited, indent="  ")
        return 0

    if command == "accounts":
        accounts = tool.list_accounts()
        if not accounts:
            print("暂无账号。")
            return 0
        for index, account in enumerate(accounts, start=1):
            print(f"[{index}]")
            print_account(account, indent="  ")
        return 0

    if command == "webui":
        if yes_no("启动前刷新账号状态吗", default=tool.config.webui.refresh_on_open):
            tool.refresh_accounts()
        serve(tool, tool.config.webui.host, tool.config.webui.port)
        return 0

    return 1


def load_tool_interactively() -> AutoTokenTool:
    config_path = find_default_config()
    if not config_path.exists():
        raw = prompt_text("未找到 config.yaml，请输入配置文件路径，直接回车使用 examples/example.yaml: ")
        config_path = Path(raw or "examples/example.yaml")
    config = AppConfig.from_file(config_path)
    return AutoTokenTool(config)


def prompt_command() -> str:
    print("请选择要执行的操作：")
    print("  1. 单次登录")
    print("  2. 链式登录")
    print("  3. 查看账号（默认）")
    print("  4. 启动 WebUI")
    while True:
        choice = prompt_text("> ", default="3")
        if choice in {"", "3", "accounts", "查看账号"}:
            return "accounts"
        if choice in {"1", "login", "单次登录"}:
            return "login"
        if choice in {"2", "chain", "链式登录"}:
            return "chain"
        if choice in {"4", "webui", "WebUI", "web"}:
            return "webui"
        print("请输入 1、2、3 或 4。")


def yes_no(question: str, *, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    raw = prompt_text(f"{question}？({suffix}): ").lower()
    if not raw:
        return default
    return raw in {"y", "yes", "1", "true", "是", "好"}


def prompt_text(prompt: str, default: str = "") -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        print()
        return default


def find_default_config() -> Path:
    for name in ("config.yaml", "config.yml"):
        path = Path(name)
        if path.exists():
            return path
    return Path("config.yaml")


def print_account(account, indent: str = "") -> None:
    if account is None:
        print(f"{indent}<none>")
        return
    print(f"{indent}email: {account.email}")
    print(f"{indent}level: {account.package_level}")
    print(f"{indent}credit: {account.total_credit if account.total_credit is not None else ''}")
    print(f"{indent}share_code: {account.share_code}")
    print(f"{indent}token: {account.token_masked}")
    if account.token:
        # Print full token in bright bold cyan color
        print(f"{indent}\033[1;32mfull_token: \033[0m\033[1;36m{account.token}\033[0m")


if __name__ == "__main__":
    raise SystemExit(main())
