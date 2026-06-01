from pathlib import Path
import sys


SDK_SRC = Path(__file__).resolve().parents[1] / "src"
if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from auto_token_tool import AutoTokenTool  # noqa: E402


def main() -> None:
    config_path = Path(__file__).resolve().parents[1] / "examples" / "example.yaml"
    tool = AutoTokenTool.from_file(config_path)
    for account in tool.list_accounts():
        print(account.email, account.package_level, account.token_masked)


if __name__ == "__main__":
    main()
