#!/usr/bin/env python3
"""Validate a staged publish directory before any artifact is released.

Checks required assets, protobuf-looking .dat headers, plaintext rule syntax,
sane entry counts, checksum files and the rules.zip member list.
"""

from __future__ import annotations

import hashlib
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from validate_list import validate as validate_entries  # noqa: E402

# filename -> (minimum entries, maximum entries)
TEXT_FILES = {
    "proxy-list.txt": (1000, 5_000_000),
    "direct-list.txt": (1000, 5_000_000),
    "reject-list.txt": (1000, 5_000_000),
    "china-list.txt": (1000, 5_000_000),
    "apple-cn.txt": (10, 100_000),
    "google-cn.txt": (10, 100_000),
    "gfw.txt": (100, 5_000_000),
    "greatfire.txt": (1, 100_000),
    "win-spy.txt": (1, 100_000),
    "win-update.txt": (1, 100_000),
    "win-extra.txt": (1, 100_000),
    "netforge-ads.txt": (100, 5_000_000),
    "netforge-antiad.txt": (100, 5_000_000),
    "netforge-adrules.txt": (100, 5_000_000),
    "netforge-neodev.txt": (100, 5_000_000),
    "nf-direct-exception.txt": (100, 100_000),
    "nf-proxy-exception.txt": (10, 100_000),
}
BINARY_FILES = ("geoip.dat", "geosite.dat")
CHECKSUMS = {
    "geoip.dat.sha256sum": "geoip.dat",
    "geosite.dat.sha256sum": "geosite.dat",
    "netforge-ads.txt.sha256sum": "netforge-ads.txt",
}
ZIP_MEMBERS = {
    "proxy-list.txt", "direct-list.txt", "reject-list.txt", "geoip.dat", "geosite.dat"
}
def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def check_binary(path: Path, errors: list[str]) -> None:
    try:
        with path.open("rb") as fh:
            header = fh.read(1)
        size = path.stat().st_size
    except OSError as exc:
        errors.append(f"{path.name}: {exc}")
        return
    if size < 100_000:
        errors.append(f"{path.name}: suspiciously small binary ({size} bytes)")
    if header != b"\x0a":
        errors.append(f"{path.name}: unexpected first byte {header!r} (expected protobuf field 1)")


def check_checksum(path: Path, target: Path, errors: list[str]) -> None:
    try:
        lines = [line for line in path.read_text(encoding="ascii").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(f"{path.name}: {exc}")
        return
    if len(lines) != 1:
        errors.append(f"{path.name}: expected exactly one checksum line")
        return
    parts = lines[0].split()
    if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
        errors.append(f"{path.name}: malformed checksum line")
        return
    if Path(parts[1]).name != target.name:
        errors.append(f"{path.name}: names {parts[1]!r}, expected {target.name!r}")
        return
    actual = sha256(target)
    if actual.lower() != parts[0].lower():
        errors.append(f"{path.name}: digest mismatch ({parts[0]} != {actual})")


def check_zip(path: Path, errors: list[str]) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            missing = ZIP_MEMBERS - set(names)
            if missing:
                errors.append(f"{path.name}: missing members {sorted(missing)}")
            for name in names:
                if name.startswith("/") or ".." in Path(name).parts or "\\" in name:
                    errors.append(f"{path.name}: unsafe member path {name!r}")
            bad = archive.testzip()
            if bad:
                errors.append(f"{path.name}: corrupt member {bad!r}")
    except (OSError, zipfile.BadZipFile) as exc:
        errors.append(f"{path.name}: {exc}")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_publish.py PUBLISH_DIR", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    errors: list[str] = []
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        return 1

    for name in BINARY_FILES:
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: missing")
        else:
            check_binary(path, errors)

    for name, (minimum, maximum) in TEXT_FILES.items():
        path = root / name
        if not path.is_file():
            errors.append(f"{name}: missing")
            continue
        args = type("Args", (), {
            "mode": "rule", "min": minimum, "max": maximum,
            "sorted": False, "unique": True,
        })()
        errors.extend(validate_entries(path, args))

    for sum_name, target_name in CHECKSUMS.items():
        sum_path, target = root / sum_name, root / target_name
        if not sum_path.is_file():
            errors.append(f"{sum_name}: missing")
        elif not target.is_file():
            errors.append(f"{target_name}: missing (needed by {sum_name})")
        else:
            check_checksum(sum_path, target, errors)

    zip_path = root / "rules.zip"
    if not zip_path.is_file():
        errors.append("rules.zip: missing")
    else:
        check_zip(zip_path, errors)

    for error in errors[:80]:
        print(f"ERROR: {error}", file=sys.stderr)
    if len(errors) > 80:
        print(f"ERROR: {len(errors) - 80} more errors suppressed", file=sys.stderr)
    if errors:
        return 1
    print(f"publish validation passed: {len(TEXT_FILES)} text lists, {len(BINARY_FILES)} binaries, rules.zip")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
