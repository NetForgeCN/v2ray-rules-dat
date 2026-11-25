#!/bin/sh
# Local/offline checks for the rules build. No network access required.
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OVERRIDE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$OVERRIDE_DIR/.." && pwd)
FIXTURES="$OVERRIDE_DIR/tests/fixtures"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/nf-rules-tests.XXXXXX")
trap 'rm -rf "$TMP"' EXIT HUP INT TERM

printf '== shell syntax ==\n'
for file in "$SCRIPT_DIR"/*.sh "$OVERRIDE_DIR/findRedundantDomain.py"; do
    case "$file" in
        *.sh) sh -n "$file" ;;
    esac
done
printf 'shell syntax OK\n'

printf '== python syntax ==\n'
for file in "$SCRIPT_DIR"/*.py "$OVERRIDE_DIR/findRedundantDomain.py"; do
    cp "$file" "$TMP/$(basename "$file")"
done
python3 -m py_compile "$TMP"/*.py
printf 'python syntax OK\n'

printf '== custom source config parser ==\n'
python3 "$SCRIPT_DIR/read-custom-sources.py" "$OVERRIDE_DIR/custom-sources.env" > "$TMP/sources.tsv"
[ "$(wc -l < "$TMP/sources.tsv" | tr -d '[:space:]')" -ge 6 ]
printf 'config parser OK\n'

printf '== domain validator fixtures ==\n'
python3 "$SCRIPT_DIR/validate_list.py" --mode domain --min 5 --max 10 --unique \
    "$FIXTURES/valid-domains.txt" >/dev/null
while IFS= read -r line || [ -n "$line" ]; do
    printf '%s\n' "$line" > "$TMP/one.txt"
    if python3 "$SCRIPT_DIR/validate_list.py" --mode domain "$TMP/one.txt" >/dev/null 2>&1; then
        printf 'FAIL: accepted invalid domain: %s\n' "$line" >&2
        exit 1
    fi
done < "$FIXTURES/invalid-domains.txt"
printf 'negative domain fixtures OK\n'

printf '== rule validator fixtures ==\n'
python3 "$SCRIPT_DIR/validate_list.py" --mode rule --min 4 --max 10 --unique \
    "$FIXTURES/valid-rules.txt" >/dev/null
while IFS= read -r line || [ -n "$line" ]; do
    printf '%s\n' "$line" > "$TMP/one.txt"
    if python3 "$SCRIPT_DIR/validate_list.py" --mode rule "$TMP/one.txt" >/dev/null 2>&1; then
        printf 'FAIL: accepted invalid rule: %s\n' "$line" >&2
        exit 1
    fi
done < "$FIXTURES/invalid-rules.txt"
printf 'negative rule fixtures OK\n'

printf '== list normalizer ==\n'
mkdir -p "$TMP/data"
printf 'b.com\nA.com\nb.com\na.com\n' > "$TMP/data/list"
python3 "$SCRIPT_DIR/normalize-lists.py" "$TMP/data" list >/dev/null
printf 'A.com\nb.com\n' > "$TMP/expected-list"
cmp "$TMP/expected-list" "$TMP/data/list"
cp "$TMP/data/list" "$TMP/first-normalized"
python3 "$SCRIPT_DIR/normalize-lists.py" "$TMP/data" list >/dev/null
cmp "$TMP/first-normalized" "$TMP/data/list"
printf 'list normalizer OK\n'

printf '== publish validator (positive + negative) ==\n'
mkdir -p "$TMP/publish"
python3 - "$TMP/publish" <<'PY'
import hashlib
import sys
import zipfile
from pathlib import Path

root = Path(sys.argv[1])
texts = [
    "proxy-list.txt", "direct-list.txt", "reject-list.txt", "china-list.txt",
    "apple-cn.txt", "google-cn.txt", "gfw.txt", "greatfire.txt",
    "win-spy.txt", "win-update.txt", "win-extra.txt", "netforge-ads.txt",
    "netforge-antiad.txt", "netforge-adrules.txt", "netforge-neodev.txt",
    "nf-direct-exception.txt", "nf-proxy-exception.txt",
]
for name in texts:
    (root / name).write_text("".join(f"d{i}.example.com\n" for i in range(1200)), encoding="ascii")
for name in ("geoip.dat", "geosite.dat"):
    (root / name).write_bytes(b"\x0a" + b"x" * 100000)
for source, output in (
    ("geoip.dat", "geoip.dat.sha256sum"),
    ("geosite.dat", "geosite.dat.sha256sum"),
    ("netforge-ads.txt", "netforge-ads.txt.sha256sum"),
):
    digest = hashlib.sha256((root / source).read_bytes()).hexdigest()
    (root / output).write_text(f"{digest}  {source}\n", encoding="ascii")
with zipfile.ZipFile(root / "rules.zip", "w") as archive:
    for name in ("proxy-list.txt", "direct-list.txt", "reject-list.txt", "geoip.dat", "geosite.dat"):
        archive.write(root / name, name)
PY
python3 "$SCRIPT_DIR/validate_publish.py" "$TMP/publish" >/dev/null
printf 'wrong-checksum  ' > "$TMP/publish/geoip.dat.sha256sum"
if python3 "$SCRIPT_DIR/validate_publish.py" "$TMP/publish" >/dev/null 2>&1; then
    printf 'FAIL: publish validator accepted a bad checksum\n' >&2
    exit 1
fi
printf 'publish validator OK\n'

printf '== redundant-domain finder ==\n'
printf 'foo.com\nbar.foo.com\nother.net\n' > "$TMP/domains.txt"
python3 "$OVERRIDE_DIR/findRedundantDomain.py" "$TMP/domains.txt" "$TMP/removed.txt"
[ "$(cat "$TMP/removed.txt")" = "bar.foo.com" ] || {
    printf 'FAIL: unexpected redundant set: %s\n' "$(cat "$TMP/removed.txt")" >&2
    exit 1
}
cp "$TMP/removed.txt" "$TMP/removed-first.txt"
python3 "$OVERRIDE_DIR/findRedundantDomain.py" "$TMP/domains.txt" "$TMP/removed.txt"
cmp "$TMP/removed-first.txt" "$TMP/removed.txt"
printf 'redundant-domain finder OK\n'

if command -v ruby >/dev/null 2>&1 && [ -f "$REPO_DIR/.github/workflows/run.yml" ]; then
    printf '== workflow YAML parse ==\n'
    ruby -e 'require "yaml"; YAML.parse_file(ARGV[0])' "$REPO_DIR/.github/workflows/run.yml"
    printf 'workflow YAML OK\n'
fi

printf 'ALL CHECKS PASSED\n'
