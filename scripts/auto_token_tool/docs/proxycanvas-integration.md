# ProxyCanvas Integration Notes

This repository is designed to be embedded, not installed globally.

## Python Integration

Add the SDK source path from ProxyCanvas before importing:

```python
from pathlib import Path
import sys

AUTO_TOKEN_TOOL_DIR = Path("scripts/auto_token_tool")
AUTO_TOKEN_TOOL_SRC = AUTO_TOKEN_TOOL_DIR / "src"
if str(AUTO_TOKEN_TOOL_SRC) not in sys.path:
    sys.path.insert(0, str(AUTO_TOKEN_TOOL_SRC))

from auto_token_tool import AutoTokenTool

tool = AutoTokenTool.from_file(AUTO_TOKEN_TOOL_DIR / "config.yaml")
result = tool.login_once()
```

For chain mode:

```python
result = tool.chain_login()
```

For account status:

```python
accounts = [
    account.to_dict(include_token=False)
    for account in tool.list_accounts()
]
```

## Recommended Runtime Layout

Keep runtime files outside git:

```text
scripts/auto_token_tool/
  examples/sousaku.yaml
  examples/hotgen.yaml
  config.yaml          # local only
  data/sousaku/        # local only, Sousaku accounts/tokens/cards/generated
  data/hotgen/         # local only, Hotgen accounts/tokens/cards/generated
  runtime/browser-profiles/sousaku/  # local only, Sousaku browser profiles
  runtime/browser-profiles/hotgen/   # local only, Hotgen browser profiles
```

Set `service.provider_id` to choose the ProxyCanvas token sync target. `sousaku`
posts to `/api/provider-accounts/sousaku/tokens`; `hotgen` posts to
`/api/provider-accounts/hotgen/tokens`.

## Contract For ProxyCanvas

Useful SDK methods:

- `AutoTokenTool.from_file(path)`
- `tool.login_once(share_code=None)`
- `tool.chain_login(bootstrap_if_needed=True)`
- `tool.list_accounts()`
- `tool.refresh_accounts()`

Returned account objects expose:

- `email`
- `token`
- `token_masked`
- `package_level`
- `share_code`
- `total_credit`
- `to_dict(include_token=False)`
