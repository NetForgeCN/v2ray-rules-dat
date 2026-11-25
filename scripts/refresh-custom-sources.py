#!/usr/bin/env python3
"""Refresh the three pinned ad sources in override/custom-sources.env.

For every source this script resolves the default branch head through the
GitHub API, downloads the asset at that immutable commit and computes its
SHA-256.  The env file is only rewritten when *all* sources resolved,
downloaded and validated successfully, so any API/download/content failure
leaves the previous pins untouched (fail closed).

Usage:
    python3 scripts/refresh-custom-sources.py [--config FILE] [--dry-run]

GH_TOKEN or GITHUB_TOKEN is used for the GitHub API when available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Tuple

API_ROOT = "https://api.github.com"
RAW_HOST = "raw.githubusercontent.com"
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LINE_RE = re.compile(r'^([A-Z][A-Z0-9_]*)="([^"\r\n]*)"$')
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
DOMAIN_RE = re.compile(r"^(?:domain:)?[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z-]{2,}$")
ERROR_MARKERS = (
    b"<!doctype html", b"<html", b"<head", b"<title", b"<body", b"<?xml",
    b"<error", b"<errors", b"<accessdenied", b"access denied",
    b"rate limit exceeded", b"too many requests", b"404: not found",
)
MIN_ASSET_BYTES = 16 * 1024
MAX_ASSET_BYTES = 64 * 1024 * 1024
MIN_DOMAIN_LINES = 1000
MAX_ATTEMPTS = 3


class Source(NamedTuple):
    key: str
    repo: str
    asset: str
    # AdRules moved its generated lists from the default branch (script) to
    # main; try this explicit fallback only when the asset is absent (404).
    fallback_refs: Tuple[str, ...] = ()


SOURCES = (
    Source("ANTIAD", "privacy-protection-tools/anti-AD", "anti-ad-domains.txt"),
    Source("ADRULES", "Cats-Team/AdRules", "mosdns_adrules.txt", ("main",)),
    Source("NEODEV", "neodevpro/neodevhost", "domain"),
)
BY_KEY = {source.key: source for source in SOURCES}
KNOWN_KEYS = {f"{source.key}_{suffix}" for source in SOURCES for suffix in ("URL", "SHA256")}


class RefreshError(Exception):
    """Any error that must leave the existing pins unchanged."""


def api_get(path: str, token: Optional[str]) -> dict:
    url = API_ROOT + path
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "netforgecn-custom-sources-refresh",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                final = urllib.parse.urlparse(response.geturl())
                if final.scheme != "https" or final.hostname != "api.github.com":
                    raise RefreshError(f"unexpected API redirect: {final.scheme}://{final.hostname}")
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise RefreshError(f"unexpected API response for {path}")
            return payload
        except urllib.error.HTTPError as exc:
            if attempt < MAX_ATTEMPTS and (exc.code == 429 or exc.code >= 500):
                time.sleep(2 ** (attempt - 1))
                continue
            raise RefreshError(f"GitHub API failed for {path}: HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RefreshError(f"GitHub API failed for {path}: {exc}") from exc
            time.sleep(2 ** (attempt - 1))
    raise RefreshError(f"GitHub API failed for {path}")


def download_asset(source: Source, commit: str) -> Optional[bytes]:
    """Return asset bytes, or None only when the asset is missing (HTTP 404)."""
    quoted_repo = urllib.parse.quote(source.repo, safe="/")
    url = f"{RAW_HOST}/{quoted_repo}/{commit}/{urllib.parse.quote(source.asset)}"
    request = urllib.request.Request(
        "https://" + url,
        headers={"User-Agent": "netforgecn-custom-sources-refresh"},
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                final = urllib.parse.urlparse(response.geturl())
                if final.scheme != "https" or final.hostname != RAW_HOST:
                    raise RefreshError(f"unexpected asset redirect: {final.scheme}://{final.hostname}")
                data = response.read(MAX_ASSET_BYTES + 1)
            if len(data) > MAX_ASSET_BYTES:
                raise RefreshError(f"asset too large: {url}")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            if attempt == MAX_ATTEMPTS:
                raise RefreshError(f"asset download failed: {url}: HTTP {exc.code}") from exc
            time.sleep(2 ** (attempt - 1))
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == MAX_ATTEMPTS:
                raise RefreshError(f"asset download failed: {url}: {exc}") from exc
            time.sleep(2 ** (attempt - 1))
    raise RefreshError(f"asset download failed: {url}")


def validate_asset(source: Source, data: bytes) -> None:
    """Reject error pages, truncated downloads and non-domain content."""
    label = f"{source.repo}@{source.asset}"
    if len(data) < MIN_ASSET_BYTES:
        raise RefreshError(f"asset too small ({len(data)} bytes): {label}")
    head = data[:4096].lstrip()[:512].lower()
    if any(marker in head for marker in ERROR_MARKERS):
        raise RefreshError(f"asset looks like an error page: {label}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RefreshError(f"asset is not valid UTF-8: {label}") from exc
    domain_lines = sum(
        1 for line in text.splitlines()
        if line and not line.startswith("#") and DOMAIN_RE.fullmatch(line.strip())
    )
    if domain_lines < MIN_DOMAIN_LINES:
        raise RefreshError(
            f"asset has only {domain_lines} domain lines (minimum {MIN_DOMAIN_LINES}): {label}"
        )


def validate_config_text(text: str) -> Dict[str, str]:
    """Strict parser mirroring override/scripts/read-custom-sources.py."""
    values: Dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = LINE_RE.fullmatch(line)
        if not match:
            raise RefreshError(f"config line {number}: unsupported format")
        key, value = match.groups()
        if key not in KNOWN_KEYS or key in values:
            raise RefreshError(f"config line {number}: unknown or duplicate key {key}")
        source = BY_KEY[key.rsplit("_", 1)[0]]
        if key.endswith("_URL"):
            parts = urllib.parse.urlparse(value)
            path = parts.path.strip("/").split("/")
            if (
                parts.scheme != "https" or parts.hostname != RAW_HOST
                or parts.username or parts.password or parts.query or parts.fragment
                or len(path) != 4 or path[0] + "/" + path[1] != source.repo
                or path[3] != source.asset or not COMMIT_RE.fullmatch(path[2])
            ):
                raise RefreshError(f"config line {number}: unexpected {key} pin: {value}")
        elif not SHA256_RE.fullmatch(value):
            raise RefreshError(f"config line {number}: {key} must be 64 lowercase hex chars")
        values[key] = value
    missing = KNOWN_KEYS - values.keys()
    if missing:
        raise RefreshError("config missing keys: " + ", ".join(sorted(missing)))
    return values


def resolve_source(source: Source, token: Optional[str]) -> Tuple[str, str, str]:
    """Return (commit, sha256, ref) for the newest valid upstream asset."""
    meta = api_get(f"/repos/{urllib.parse.quote(source.repo, safe='/')}", token)
    default_branch = meta.get("default_branch")
    if not isinstance(default_branch, str) or not BRANCH_RE.fullmatch(default_branch):
        raise RefreshError(f"invalid default branch for {source.repo}: {default_branch!r}")
    candidates = [default_branch] + [
        ref for ref in source.fallback_refs if ref != default_branch
    ]
    for ref in candidates:
        escaped = urllib.parse.quote(ref, safe="")
        commit_info = api_get(
            f"/repos/{urllib.parse.quote(source.repo, safe='/')}/commits/{escaped}", token
        )
        commit = commit_info.get("sha")
        if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
            raise RefreshError(f"invalid commit SHA for {source.repo}@{ref}: {commit!r}")
        data = download_asset(source, commit)
        if data is None:
            print(f"  {source.repo}@{ref}: asset absent, trying next ref", file=sys.stderr)
            continue
        validate_asset(source, data)
        digest = hashlib.sha256(data).hexdigest()
        if not SHA256_RE.fullmatch(digest):
            raise RefreshError(f"invalid computed SHA-256 for {source.repo}@{ref}")
        return commit, digest, default_branch if ref == default_branch else ref
    raise RefreshError(f"no valid asset found for {source.repo}@{source.asset}")


def render_config(text: str, values: Dict[str, str]) -> str:
    """Replace only the six known KEY= lines; keep comments and ordering."""
    seen = set()
    rendered = []
    for raw in text.splitlines(keepends=True):
        ending = "\n" if raw.endswith("\n") else ""
        body = raw[:-1] if raw.endswith("\n") else raw
        if body.endswith("\r"):
            body, ending = body[:-1], "\r" + ending
        match = LINE_RE.fullmatch(body)
        if match and match.group(1) in KNOWN_KEYS:
            key = match.group(1)
            rendered.append(f'{key}="{values[key]}"{ending}')
            seen.add(key)
        else:
            rendered.append(raw)
    if seen != KNOWN_KEYS:
        raise RefreshError("config does not contain all expected keys")
    return "".join(rendered)


def write_atomically(path: Path, text: str) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".custom-sources.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        # Never replace the original with a file we cannot parse ourselves.
        validate_config_text(Path(temporary).read_text(encoding="utf-8"))
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_config = Path(__file__).resolve().parents[1] / "override" / "custom-sources.env"
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--dry-run", action="store_true", help="resolve and validate without writing")
    args = parser.parse_args()

    try:
        original = args.config.read_text(encoding="utf-8")
        old_values = validate_config_text(original)
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            print("warning: no GH_TOKEN/GITHUB_TOKEN; API rate limits may fail closed", file=sys.stderr)
        new_values = dict(old_values)
        for source in SOURCES:
            commit, digest, ref = resolve_source(source, token)
            url = f"https://{RAW_HOST}/{source.repo}/{commit}/{source.asset}"
            print(f"{source.key}: ref={ref} commit={commit} sha256={digest}")
            new_values[f"{source.key}_URL"] = url
            new_values[f"{source.key}_SHA256"] = digest
        rendered = render_config(original, new_values)
        changed = rendered != original
        if args.dry_run:
            print("DRY RUN: " + ("pins would change" if changed else "pins already current"))
            return 0
        if changed:
            write_atomically(args.config, rendered)
            print(f"updated {args.config}")
        else:
            print(f"no changes to {args.config}")
        return 0
    except (RefreshError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
