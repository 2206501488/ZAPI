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
from auto_token_tool.generation import GenerationRunner  # noqa: E402
from auto_token_tool.service import SousakuServiceClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Complete configured generation tasks and claim rewards for an existing token.",
    )
    parser.add_argument(
        "token",
        nargs="?",
        help="Sousaku/Hotgen token. If omitted, the script prompts for it.",
    )
    parser.add_argument(
        "--config",
        default=str(TOOL_ROOT / "config.yaml"),
        help="Path to config.yaml. Defaults to scripts/auto_token_tool/config.yaml.",
    )
    parser.add_argument(
        "--no-generation",
        action="store_true",
        help="Skip generation tasks and only complete/claim rewards.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Submit generation tasks without waiting for results.",
    )
    parser.add_argument(
        "--skip-final",
        action="store_true",
        help="Do not claim the final unlock reward.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    token = (args.token or input("Token: ")).strip()
    if not token:
        print("Token is required.", file=sys.stderr)
        return 2

    config = AppConfig.from_file(args.config)
    service = SousakuServiceClient(config.service)

    print(f"Using provider: {config.service.provider_id}")
    account = service.account_from_token(token)
    print(f"Account: {account.email or '<unknown>'} level={account.package_level} credit={account.total_credit}")

    complete_tasks(service, token, config.chain.reward_task_ids)

    submitted_tasks: list[str] = []
    if not args.no_generation:
        if not config.generation.tasks:
            print("No generation.tasks configured; skip generation.")
        else:
            print("Submitting configured generation tasks...")
            submitted_tasks = GenerationRunner(config, service).run(
                token,
                wait_for_result=not args.no_wait,
            )
            if submitted_tasks:
                print("Submitted task IDs:")
                for task_id in submitted_tasks:
                    print(f"  {task_id}")

    claim_ids = ordered_unique([
        *config.chain.reward_task_ids,
        *[
            task_id
            for task_id in config.chain.reward_claim_task_ids
            if not args.skip_final or task_id != config.chain.final_reward_task_id
        ],
    ])
    if not args.skip_final and config.chain.final_reward_task_id:
        claim_ids = ordered_unique([*claim_ids, config.chain.final_reward_task_id])

    claim_tasks(service, token, claim_ids)

    refreshed = service.account_from_token(token, fallback_email=account.email)
    print(f"Done. Account now: {refreshed.email or '<unknown>'} level={refreshed.package_level} credit={refreshed.total_credit}")
    return 0


def complete_tasks(service: SousakuServiceClient, token: str, task_ids: list[str]) -> None:
    for task_id in ordered_unique(task_ids):
        try:
            service.complete_reward(token, task_id)
            print(f"Completed task: {task_id}")
        except Exception as exc:
            print(f"Complete skipped: {task_id}; {exc}")


def claim_tasks(service: SousakuServiceClient, token: str, task_ids: list[str]) -> None:
    for task_id in ordered_unique(task_ids):
        try:
            service.claim_reward(token, task_id)
            print(f"Claimed reward: {task_id}")
        except Exception as exc:
            print(f"Claim skipped: {task_id}; {exc}")


def ordered_unique(values: list[str]) -> list[str]:
    return [item for item in dict.fromkeys(str(value).strip() for value in values if str(value).strip())]


if __name__ == "__main__":
    raise SystemExit(main())
