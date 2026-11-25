#!/usr/bin/env python3
"""Safely read override/custom-sources.env.

Only `KEY="value"` lines with known keys are accepted. Values must be HTTPS
URLs on an allowlisted host, or 64-character lowercase SHA-256 digests. The
output is tab-separated KEY<TAB>value so the caller never needs eval/source.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse

URL_KEYS = {"ANTIAD_URL", "ADRULES_URL", "NEODEV_URL"}
HASH_KEYS = {"ANTIAD_SHA256", "ADRULES_SHA256", "NEODEV_SHA256"}
KNOWN_KEYS = URL_KEYS | HASH_KEYS
ALLOWED_HOSTS = {
    "raw.githubusercontent.com",
}
LINE_RE = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"\r\n]*)"$')
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: read-custom-sources.py FILE", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    seen: set[str] = set()
    entries: list[tuple[str, str]] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.fullmatch(line)
        if not match:
            print(f"{path}:{number}: unsupported line format", file=sys.stderr)
            return 1
        key, value = match.groups()
        if key not in KNOWN_KEYS:
            print(f"{path}:{number}: unknown key {key}", file=sys.stderr)
            return 1
        if key in seen:
            print(f"{path}:{number}: duplicate key {key}", file=sys.stderr)
            return 1
        seen.add(key)
        if key in URL_KEYS:
            parsed = urlparse(value)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
                print(f"{path}:{number}: URL must be https on {sorted(ALLOWED_HOSTS)}", file=sys.stderr)
                return 1
            # Reject credentials, query strings, fragments and branch-less paths.
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                print(f"{path}:{number}: URL has unsupported components", file=sys.stderr)
                return 1
            parts = parsed.path.strip("/").split("/")
            if len(parts) < 3:
                print(f"{path}:{number}: URL path is too short", file=sys.stderr)
                return 1
            if not re.fullmatch(r"[0-9a-f]{40}", parts[2]):
                print(f"{path}:{number}: upstream ref must be a 40-char commit SHA", file=sys.stderr)
                return 1
        else:
            if not SHA_RE.fullmatch(value):
                print(f"{path}:{number}: expected lowercase 64-char SHA-256", file=sys.stderr)
                return 1
        entries.append((key, value))
    missing = {"ANTIAD_URL", "ADRULES_URL", "NEODEV_URL"} - seen
    if missing:
        print(f"{path}: missing keys: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    for key, value in entries:
        print(f"{key}\t{value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
