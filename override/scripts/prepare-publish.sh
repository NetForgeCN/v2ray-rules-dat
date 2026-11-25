#!/bin/sh
# Stage, validate, and atomically publish release artifacts.
# Usage: prepare-publish.sh [WORKSPACE_DIR]   (default: current directory)
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/lib.sh"

ROOT=${1:-.}
cd "$ROOT"

STAGE=$(mktemp -d "$ROOT/.publish-staging.XXXXXX") || nf_die "mktemp failed"
trap 'rm -rf "$STAGE"' EXIT HUP INT TERM

# Every file comes from this single build. Never merge with an older publish/.
install -m 0644 sources/geoip.dat "$STAGE/geoip.dat"
install -m 0644 sources/geoip.dat.sha256sum "$STAGE/geoip.dat.sha256sum"
install -m 0644 custom/publish/geosite.dat "$STAGE/geosite.dat"

for name in proxy-list direct-list reject-list china-list apple-cn google-cn \
            gfw greatfire win-spy win-update win-extra netforge-ads; do
    [ -s "$name.txt" ] || nf_die "missing or empty $name.txt"
    install -m 0644 "$name.txt" "$STAGE/$name.txt"
done
for name in netforge-antiad netforge-adrules netforge-neodev \
            nf-direct-exception nf-proxy-exception; do
    [ -s "community/data/$name" ] || nf_die "missing or empty community/data/$name"
    install -m 0644 "community/data/$name" "$STAGE/$name.txt"
done

# Deterministic timestamps and archive flags make two builds of the same
# inputs byte-identical (no owner/uid, no directory entries, fixed mtime).
find "$STAGE" -type f -exec touch -t 200001010000 {} + || nf_die "touch failed"
export SOURCE_DATE_EPOCH=946684800
(
    cd "$STAGE"
    zip -q -X -D rules.zip \
        proxy-list.txt direct-list.txt reject-list.txt geoip.dat geosite.dat \
        || nf_die "zip failed"
)

python3 - "$STAGE" <<'PY'
import hashlib
import sys
from pathlib import Path

stage = Path(sys.argv[1])
for source, output in (
    ("geosite.dat", "geosite.dat.sha256sum"),
    ("netforge-ads.txt", "netforge-ads.txt.sha256sum"),
):
    digest = hashlib.sha256((stage / source).read_bytes()).hexdigest()
    (stage / output).write_text(f"{digest}  {source}\n", encoding="ascii")
PY

python3 "$SCRIPT_DIR/validate_publish.py" "$STAGE" || nf_die "publish validation failed"

# Atomic swap: consumers see either the previous complete set or the new one.
rm -rf "$ROOT/publish" || nf_die "cannot remove old publish directory"
mv "$STAGE" "$ROOT/publish" || nf_die "cannot move staged artifacts to publish/"
trap - EXIT HUP INT TERM
printf 'staged %s files into publish/\n' "$(find "$ROOT/publish" -type f | wc -l | tr -d '[:space:]')"
