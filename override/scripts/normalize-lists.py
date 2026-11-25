#!/usr/bin/env python3
"""Case-insensitively deduplicate and sort generated rule lists in place.

Usage: normalize-lists.py DATA_DIR NAME [NAME ...]

Writes are atomic (temp file + os.replace) and repeated runs are idempotent,
which keeps the final artifacts deterministic for the reproducibility check.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


def normalize(path: Path) -> tuple[int, int]:
    lines = path.read_text(encoding="ascii").splitlines()
    entries = [line for line in lines if line.strip()]
    seen: set[str] = set()
    unique: list[str] = []
    for line in entries:
        key = line.lower()
        if key not in seen:
            seen.add(key)
            unique.append(line)
    unique.sort(key=str.lower)
    fd, tmp_name = tempfile.mkstemp(prefix=".normalize-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as fh:
            for line in unique:
                fh.write(line + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return len(entries), len(unique)


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: normalize-lists.py DATA_DIR NAME [NAME ...]", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    for name in sys.argv[2:]:
        path = root / name
        if not path.is_file():
            print(f"ERROR: {path}: missing", file=sys.stderr)
            return 1
        before, after = normalize(path)
        print(f"{name}: {before} -> {after} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
