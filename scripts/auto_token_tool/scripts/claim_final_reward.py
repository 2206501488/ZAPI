from __future__ import annotations

import argparse
from pathlib import Path
import sys
import types


TOOL_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = TOOL_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if "auto_token_tool" not in sys.modules:
    package = types.ModuleType("auto_token_tool")
    package.__path__ = [str(SRC_DIR / "auto_token_tool")]
    sys.modules["auto_token_tool"] = package

from auto_token_tool.config import AppConfig  # noqa: E402
from auto_token_tool.service import SousakuServiceClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Claim only the final membership reward for a token.")
    parser.add_argument("token", nargs="?", help="Sousaku/Hotgen token. If omitted, the script prompts for it.")
    parser.add_argument(
        "--config",
        default=str(TOOL_ROOT / "config.yaml"),
        help="Path to config.yaml. Defaults to scripts/auto_token_tool/config.yaml.",
    )
    parser.add_argument(
        "--task-id",
        default="",
        help="Override final reward task id. Defaults to chain.final_reward_task_id from config.yaml.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = (args.token or input("Token: ")).strip()
    if not token:
        print("Token is required.", file=sys.stderr)
        return 2

    config = AppConfig.from_file(args.config)
    task_id = (args.task_id or config.chain.final_reward_task_id).strip()
    if not task_id:
        print("No final reward task id configured.", file=sys.stderr)
        return 2

    service = SousakuServiceClient(config.service)
    before = service.account_from_token(token)
    print(f"Using provider: {config.service.provider_id}")
    print(f"Before: {before.email or '<unknown>'} level={before.package_level} credit={before.total_credit}")
    print(f"Claiming final reward: {task_id}")

    service.claim_reward(token, task_id)

    after = service.account_from_token(token, fallback_email=before.email)
    print(f"After: {after.email or '<unknown>'} level={after.package_level} credit={after.total_credit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
