from __future__ import annotations

from pathlib import Path

from .models import AccountRecord, utc_now
from .yamlio import dump_yaml, load_yaml_mapping


class AccountStore:
    def __init__(self, path: str | Path, tokens_path: str | Path | None = None) -> None:
        self.path = Path(path)
        self.tokens_path = Path(tokens_path) if tokens_path else None

    def list(self) -> list[AccountRecord]:
        if not self.path.exists():
            return []
        content = self.path.read_text(encoding="utf-8")
        if self.path.suffix.lower() == ".json":
            import json
            try:
                data = json.loads(content)
            except Exception:
                return []
            if isinstance(data, list):
                return [AccountRecord.from_dict(item) for item in data if isinstance(item, dict)]
            elif isinstance(data, dict):
                records = data.get("accounts", [])
                return [AccountRecord.from_dict(item) for item in records if isinstance(item, dict)]
            return []
        else:
            data = load_yaml_mapping(content)
            records = data.get("accounts", [])
            if not isinstance(records, list):
                return []
            return [AccountRecord.from_dict(item) for item in records if isinstance(item, dict)]

    def save_all(self, accounts: list[AccountRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = []
        for account in accounts:
            item = account.to_dict(include_token=True, include_raw=False)
            item.pop("token_masked", None)
            records.append(item)

        if self.path.suffix.lower() == ".json":
            import json
            is_flat_list = True
            if self.path.exists():
                try:
                    old_data = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(old_data, dict):
                        is_flat_list = False
                except Exception:
                    pass
            if "config" in self.path.name.lower():
                is_flat_list = False

            if is_flat_list:
                payload = records
            else:
                payload = {"accounts": records}
                if self.path.exists():
                    try:
                        old_data = json.loads(self.path.read_text(encoding="utf-8"))
                        if isinstance(old_data, dict):
                            old_data["accounts"] = records
                            payload = old_data
                    except Exception:
                        pass
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            payload = {"accounts": records}
            self.path.write_text(dump_yaml(payload), encoding="utf-8")
        self._write_tokens(accounts)

    def upsert(self, account: AccountRecord) -> AccountRecord:
        accounts = self.list()
        now = utc_now()
        account.updated_at = now
        for index, existing in enumerate(accounts):
            if existing.email == account.email or existing.token == account.token:
                account.created_at = existing.created_at
                accounts[index] = account
                self.save_all(accounts)
                return account
        account.created_at = account.created_at or now
        accounts.append(account)
        self.save_all(accounts)
        return account

    def find_latest_free(self) -> AccountRecord | None:
        for account in reversed(self.list()):
            if account.token and account.package_level.lower() == "free" and account.share_code:
                return account
        return None

    def _write_tokens(self, accounts: list[AccountRecord]) -> None:
        if not self.tokens_path:
            return
        tokens = [account.token for account in accounts if account.token]
        self.tokens_path.parent.mkdir(parents=True, exist_ok=True)
        if self.tokens_path.suffix.lower() == ".json":
            import json
            payload = {"tokens": tokens}
            if self.tokens_path.exists():
                try:
                    old = json.loads(self.tokens_path.read_text(encoding="utf-8"))
                    if isinstance(old, dict):
                        old["tokens"] = tokens
                        payload = old
                except Exception:
                    pass
            self.tokens_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            self.tokens_path.write_text(dump_yaml({"tokens": tokens}), encoding="utf-8")


def next_gmail_dot_alias(
    base_email: str, used_emails: set[str], offset: int = 0, max_dots: int = 3
) -> str:
    username, sep, domain = base_email.partition("@")
    if sep != "@" or domain.lower() != "gmail.com":
        return base_email

    # Strip existing dots from username to get a clean base username
    clean_username = username.replace(".", "")
    if len(clean_username) <= 1:
        return base_email

    # Exclude base_email and dot-free username from being treated as available aliases
    used_emails_set = {email.lower() for email in used_emails}
    used_emails_set.add(base_email.lower())
    used_emails_set.add(f"{clean_username}@{domain}".lower())

    import itertools

    def make_alias(username_str: str, domain_str: str, dot_indices: set[int]) -> str:
        chars = []
        for pos, char in enumerate(username_str):
            chars.append(char)
            if pos in dot_indices:
                chars.append(".")
        return "".join(chars) + "@" + domain_str

    num_positions = len(clean_username) - 1
    skipped = 0

    # Generate combinations from 1 dot up to max_dots
    for k in range(1, max_dots + 1):
        for combo in itertools.combinations(range(num_positions), k):
            dot_indices = set(combo)
            alias = make_alias(clean_username, domain, dot_indices)
            if alias.lower() in used_emails_set:
                continue
            if skipped == offset:
                return alias
            skipped += 1

    return base_email
