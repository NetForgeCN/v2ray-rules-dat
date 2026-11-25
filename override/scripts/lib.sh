#!/bin/sh
# Shared, portable helpers for the rules build (POSIX sh, Linux + macOS).
# Requires only curl, python3 and coreutils that ship with the runners.
# No secrets are ever interpolated into a URL or printed by these helpers.

NF_CURL_MAX_TIME=${NF_CURL_MAX_TIME:-120}
NF_CURL_MAX_SIZE=${NF_CURL_MAX_SIZE:-67108864}
NF_CURL_MIN_SIZE=${NF_CURL_MIN_SIZE:-16}

nf_die() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

# SHA-256 of a local file, portable across BSD/GNU coreutils.
nf_sha256() {
    python3 - "$1" <<'PY'
import hashlib
import sys

h = hashlib.sha256()
with open(sys.argv[1], "rb") as fh:
    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
        h.update(chunk)
print(h.hexdigest())
PY
}

# Return success when the first 4 KiB look like an HTML/error document.
nf_looks_like_html() {
    python3 - "$1" <<'PY'
import sys

with open(sys.argv[1], "rb") as fh:
    head = fh.read(4096).lstrip()[:512].lower()
markers = (
    b"<!doctype html", b"<html", b"<head", b"<title", b"<body",
    b"<?xml", b"<error", b"<errors", b"<accessdenied",
    b"access denied", b"rate limit exceeded", b"too many requests",
)
sys.exit(0 if any(marker in head for marker in markers) else 1)
PY
}

# Validate sha256sum file: exactly one line, 64 hex chars, expected basename.
# Prints the expected digest on stdout.
nf_read_sha256sum() {
    python3 - "$1" "$2" <<'PY'
import os
import re
import sys

path, expected = sys.argv[1], sys.argv[2]
with open(path, "r", encoding="utf-8", errors="strict") as fh:
    lines = [line for line in fh.read().splitlines() if line.strip()]
if len(lines) != 1:
    sys.exit("ERROR: %s: expected exactly one checksum line" % path)
parts = lines[0].split()
if len(parts) == 2:
    digest, name = parts
elif len(parts) == 1:
    digest, name = parts[0], expected
else:
    sys.exit("ERROR: %s: malformed checksum line" % path)
if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
    sys.exit("ERROR: %s: digest is not 64 hex characters" % path)
if os.path.basename(name) != expected:
    sys.exit("ERROR: %s: checksum names %r, expected %r" % (path, name, expected))
print(digest.lower())
PY
}

# nf_fetch URL DEST [EXPECTED_SHA256]
# Downloads to a temp file in DEST's directory, checks HTTPS-only redirects,
# size bounds, HTML error pages and an optional digest, then atomically moves
# the result into place. Failing downloads always abort the caller.
nf_fetch() {
    nf_url=$1
    nf_dest=$2
    nf_expect=${3:-}
    case "$nf_url" in
        https://*) ;;
        *) nf_die "refusing non-HTTPS URL: $nf_url" ;;
    esac
    nf_dir=$(dirname "$nf_dest") || nf_die "cannot resolve directory for $nf_dest"
    mkdir -p "$nf_dir" || nf_die "cannot create $nf_dir"
    nf_tmp=$(mktemp "$nf_dir/.nf-download.XXXXXX") || nf_die "mktemp failed in $nf_dir"
    (
        trap 'rm -f "$nf_tmp"' EXIT HUP INT TERM
        curl --silent --show-error --fail \
            --proto '=https' --proto-redir '=https' \
            --location --max-redirs 5 \
            --connect-timeout 15 --max-time "$NF_CURL_MAX_TIME" \
            --retry 3 --retry-delay 2 \
            --max-filesize "$NF_CURL_MAX_SIZE" \
            --output "$nf_tmp" "$nf_url" \
            || nf_die "download failed: $nf_url"
        nf_size=$(wc -c < "$nf_tmp" | tr -d '[:space:]')
        [ "$nf_size" -ge "$NF_CURL_MIN_SIZE" ] 2>/dev/null \
            || nf_die "download too small ($nf_size bytes): $nf_url"
        [ "$nf_size" -le "$NF_CURL_MAX_SIZE" ] 2>/dev/null \
            || nf_die "download too large ($nf_size bytes): $nf_url"
        if nf_looks_like_html "$nf_tmp"; then
            nf_die "download looks like an HTML/error page: $nf_url"
        fi
        if [ -n "$nf_expect" ]; then
            nf_actual=$(nf_sha256 "$nf_tmp") || nf_die "cannot hash $nf_url"
            [ "$nf_actual" = "$nf_expect" ] \
                || nf_die "SHA-256 mismatch for $nf_url (expected $nf_expect, got $nf_actual)"
        fi
        chmod 0644 "$nf_tmp" || nf_die "chmod failed for $nf_dest"
        mv -f "$nf_tmp" "$nf_dest" || nf_die "cannot install $nf_dest"
    )
}

# Verify a downloaded artifact against its (downloaded) .sha256sum file.
# nf_verify_artifact FILE SUMFILE EXPECTED_NAME
nf_verify_artifact() {
    nf_file=$1
    nf_sumfile=$2
    nf_name=$3
    nf_expected=$(nf_read_sha256sum "$nf_sumfile" "$nf_name") \
        || nf_die "invalid checksum file for $nf_name"
    nf_actual=$(nf_sha256 "$nf_file") || nf_die "cannot hash $nf_file"
    [ "$nf_actual" = "$nf_expected" ] \
        || nf_die "SHA-256 mismatch for $nf_name (expected $nf_expected, got $nf_actual)"
}
