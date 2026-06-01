from __future__ import annotations

import re
from typing import Any

from .exceptions import ConfigError


def load_yaml_mapping(text: str) -> dict[str, Any]:
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any]] = [(-1, root)]

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = strip_yaml_comment(raw_line).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2 != 0:
            raise ConfigError(f"YAML indentation must use 2 spaces at line {line_no}.")
        item = line.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigError(f"Invalid YAML indentation at line {line_no}.")
        parent = stack[-1][1]

        if item == "-" or item.startswith("- "):
            if not isinstance(parent, list):
                raise ConfigError(f"Unexpected YAML list item at line {line_no}.")
            value = "" if item == "-" else item[2:].strip()
            if not value:
                child: dict[str, Any] = {}
                parent.append(child)
                stack.append((indent, child))
            elif ":" in value and not value.startswith(("'", '"')):
                key, scalar = value.split(":", 1)
                child = {key.strip(): parse_yaml_scalar(scalar.strip())}
                parent.append(child)
                stack.append((indent, child))
            else:
                parent.append(parse_yaml_scalar(value))
            continue

        if ":" not in item:
            raise ConfigError(f"Invalid YAML line {line_no}: {raw_line}")
        key, value = item.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigError(f"Missing YAML key at line {line_no}.")

        if isinstance(parent, list):
            raise ConfigError(f"Cannot assign mapping key inside list at line {line_no}.")
        if value == "":
            child = [] if _next_significant_line_is_list(text, line_no, indent) else {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = parse_yaml_scalar(value)

    return root


def dump_yaml(value: Any, indent: int = 0) -> str:
    lines: list[str] = []
    _dump_value(value, lines, indent)
    return "\n".join(lines) + "\n"


def strip_yaml_comment(line: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = ""
            elif not quote:
                quote = char
            continue
        if char == "#" and not quote:
            return line[:index]
    return line


def parse_yaml_scalar(value: str) -> Any:
    if value in {'""', "''"}:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_yaml_scalar(item.strip()) for item in split_inline_list(inner)]
    if value == "{}":
        return {}
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def split_inline_list(value: str) -> list[str]:
    items: list[str] = []
    current: list[str] = []
    quote = ""
    escaped = False
    for char in value:
        if escaped:
            current.append(char)
            escaped = False
            continue
        if char == "\\":
            current.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            current.append(char)
            if quote == char:
                quote = ""
            elif not quote:
                quote = char
            continue
        if char == "," and not quote:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    items.append("".join(current).strip())
    return items


def _dump_value(value: Any, lines: list[str], indent: int, key: str | None = None) -> None:
    prefix = " " * indent
    if isinstance(value, dict):
        if key is not None:
            lines.append(f"{prefix}{key}:")
            indent += 2
            prefix = " " * indent
        for item_key, item_value in value.items():
            _dump_value(item_value, lines, indent, str(item_key))
        return
    if isinstance(value, list):
        if key is not None:
            lines.append(f"{prefix}{key}:")
            indent += 2
            prefix = " " * indent
        if not value:
            if key is not None:
                lines[-1] = f"{' ' * (indent - 2)}{key}: []"
            else:
                lines.append(f"{prefix}[]")
            return
        for item in value:
            if isinstance(item, dict):
                lines.append(f"{prefix}-")
                for item_key, item_value in item.items():
                    _dump_value(item_value, lines, indent + 2, str(item_key))
            else:
                lines.append(f"{prefix}- {format_yaml_scalar(item)}")
        return
    if key is None:
        lines.append(f"{prefix}{format_yaml_scalar(value)}")
    else:
        lines.append(f"{prefix}{key}: {format_yaml_scalar(value)}")


def format_yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        if value == "":
            return '""'
        if re.fullmatch(r"[A-Za-z0-9_./:@-]+", value) and value.lower() not in {
            "true",
            "false",
            "null",
            "~",
        }:
            return value
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return format_yaml_scalar(str(value))


def _next_significant_line_is_list(text: str, line_no: int, indent: int) -> bool:
    for raw in text.splitlines()[line_no:]:
        line = strip_yaml_comment(raw).rstrip()
        if not line.strip():
            continue
        next_indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        return next_indent > indent and (stripped == "-" or stripped.startswith("- "))
    return False
