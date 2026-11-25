#!/usr/bin/env python3
"""Validate generated plaintext rule lists.

Examples:
  validate_list.py --mode domain --min 100 --max 2000000 data/cn
  validate_list.py --mode rule --min 1 --max 10000 data/geolocation-'!cn'
  validate_list.py --mode domain --sorted --unique publish/*.txt

The validator is intentionally strict: anything that is not a plain ASCII
domain (or an explicit full:/regexp:/keyword: rule) is a build failure.
"""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys
from pathlib import Path

LABEL = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
RULE_PREFIX = ("full:", "regexp:", "keyword:")


def valid_domain(value: str) -> bool:
    if not value or len(value) > 253:
        return False
    labels = value.split(".")
    if not all(LABEL.fullmatch(label) for label in labels):
        return False
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        return False
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return False
    return True


def valid_rule(value: str) -> bool:
    for prefix in RULE_PREFIX:
        if value.startswith(prefix):
            body = value[len(prefix):]
            if not body:
                return False
            if prefix == "regexp:":
                return len(body) <= 512 and all(32 < ord(ch) < 127 for ch in body)
            return valid_domain(body)
    return valid_domain(value)


def validate(path: Path, args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="ascii")
    except UnicodeDecodeError:
        return [f"{path}: non-ASCII bytes are not allowed"]
    except OSError as exc:
        return [f"{path}: {exc}"]
    lines = [line.rstrip("\r") for line in text.splitlines()]
    entries = [line for line in lines if line.strip()]
    if not entries and path.stat().st_size != 0:
        errors.append(f"{path}: only blank lines found")
    count = len(entries)
    if args.min is not None and count < args.min:
        errors.append(f"{path}: {count} entries, below minimum {args.min}")
    if args.max is not None and count > args.max:
        errors.append(f"{path}: {count} entries, above maximum {args.max}")
    validator = valid_rule if args.mode == "rule" else valid_domain
    for number, line in enumerate(entries, 1):
        if not validator(line):
            errors.append(f"{path}:{number}: invalid entry {line!r}")
    if args.unique:
        seen: set[str] = set()
        for number, line in enumerate(entries, 1):
            key = line.lower()
            if key in seen:
                errors.append(f"{path}:{number}: duplicate entry {line!r}")
            seen.add(key)
    if args.sorted:
        keys = [line.lower() for line in entries]
        if keys != sorted(keys):
            errors.append(f"{path}: entries are not sorted case-insensitively")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("domain", "rule"), default="domain")
    parser.add_argument("--min", type=int)
    parser.add_argument("--max", type=int)
    parser.add_argument("--sorted", action="store_true")
    parser.add_argument("--unique", action="store_true")
    parser.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    errors: list[str] = []
    for path in args.files:
        errors.extend(validate(path, args))
    for error in errors[:50]:
        print(f"ERROR: {error}", file=sys.stderr)
    if len(errors) > 50:
        print(f"ERROR: {len(errors) - 50} more errors suppressed", file=sys.stderr)
    if errors:
        return 1
    print(f"validated {len(args.files)} list(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
