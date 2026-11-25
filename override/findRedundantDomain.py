#!/usr/bin/env python3
"""Find redundant items in domain lists.

'bar.foo.com' is redundant when 'foo.com' is already present. The output file
is truncated on every run so repeated builds cannot accumulate stale entries.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

LABEL = re.compile(r"^[A-Za-z0-9_-]{1,63}$")
LEAF = "\x00leaf"


def load(path: Path) -> list[str]:
    domains: list[str] = []
    with path.open("r", encoding="ascii") as fh:
        for number, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            labels = line.lower().split(".")
            if not all(LABEL.fullmatch(label) for label in labels):
                print(f"WARNING: {path}:{number}: skipping invalid domain {line!r}", file=sys.stderr)
                continue
            domains.append(".".join(labels))
    # Shortest first, then lexicographic: deterministic without mutating input.
    domains.sort(key=lambda value: (len(value.split(".")), value))
    return domains


def find(domains: list[str], output: Path) -> None:
    tree: dict[str, dict] = {}
    redundant: list[str] = []
    for domain in domains:
        path = list(reversed(domain.split(".")))
        node = tree
        is_redundant = False
        for label in path:
            node = node.setdefault(label, {})
            if LEAF in node:
                is_redundant = True
                break
        if is_redundant:
            redundant.append(domain)
        else:
            node[LEAF] = True
    with output.open("w", encoding="ascii") as fh:
        for domain in redundant:
            fh.write(domain + "\n")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: findRedundantDomain.py INPUT OUTPUT", file=sys.stderr)
        return 2
    find(load(Path(sys.argv[1])), Path(sys.argv[2]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
