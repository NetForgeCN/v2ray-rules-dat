#!/bin/sh
# Download every upstream input exactly once, with strict TLS, bounded size,
# content checks and digest verification where the upstream provides one.
# Usage: fetch-sources.sh [WORKSPACE_DIR]   (default: current directory)
set -eu
umask 077

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$SCRIPT_DIR/lib.sh"

ROOT=${1:-.}
SRC="$ROOT/sources"
mkdir -p "$SRC"

# Canonical upstream inputs. Environment overrides are allowed for testing and
# for incident response, but nf_fetch enforces HTTPS for all of them.
CHINA_DOMAINS_URL=${CHINA_DOMAINS_URL:-https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf}
GOOGLE_DOMAINS_URL=${GOOGLE_DOMAINS_URL:-https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/google.china.conf}
APPLE_DOMAINS_URL=${APPLE_DOMAINS_URL:-https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/apple.china.conf}
EASYLISTCHINA_EASYLIST_REJECT_URL=${EASYLISTCHINA_EASYLIST_REJECT_URL:-https://easylist-downloads.adblockplus.org/easylistchina+easylist.txt}
ADGUARD_DNS_REJECT_URL=${ADGUARD_DNS_REJECT_URL:-https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt}
PETERLOWE_REJECT_URL=${PETERLOWE_REJECT_URL:-https://pgl.yoyo.org/adservers/serverlist.php?hostformat=hosts&showintro=1&mimetype=plaintext}
DANPOLLOCK_REJECT_URL=${DANPOLLOCK_REJECT_URL:-https://someonewhocares.org/hosts/hosts}
CUSTOM_DIRECT=${CUSTOM_DIRECT:-https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/release/cn.txt}
CUSTOM_PROXY=${CUSTOM_PROXY:-https://raw.githubusercontent.com/Loyalsoldier/domain-list-custom/release/geolocation-!cn.txt}
WIN_SPY=${WIN_SPY:-https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/spy.txt}
WIN_UPDATE=${WIN_UPDATE:-https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/update.txt}
WIN_EXTRA=${WIN_EXTRA:-https://raw.githubusercontent.com/crazy-max/WindowsSpyBlocker/master/data/hosts/extra.txt}
GEOIP_URL=${GEOIP_URL:-https://github.com/Loyalsoldier/geoip/raw/release/geoip.dat}
GEOIP_SUM_URL=${GEOIP_SUM_URL:-https://github.com/Loyalsoldier/geoip/raw/release/geoip.dat.sha256sum}

# Read the pinned custom sources without sourcing shell code from a data file.
CONFIG="$SCRIPT_DIR/../custom-sources.env"
ANTIAD_URL=
ANTIAD_SHA256=
ADRULES_URL=
ADRULES_SHA256=
NEODEV_URL=
NEODEV_SHA256=
while IFS="$(printf '\t')" read -r nf_key nf_value; do
    case "$nf_key" in
        ANTIAD_URL) ANTIAD_URL=$nf_value ;;
        ANTIAD_SHA256) ANTIAD_SHA256=$nf_value ;;
        ADRULES_URL) ADRULES_URL=$nf_value ;;
        ADRULES_SHA256) ADRULES_SHA256=$nf_value ;;
        NEODEV_URL) NEODEV_URL=$nf_value ;;
        NEODEV_SHA256) NEODEV_SHA256=$nf_value ;;
        *) nf_die "unexpected key from custom-sources parser: $nf_key" ;;
    esac
done <<EOF
$(python3 "$SCRIPT_DIR/read-custom-sources.py" "$CONFIG" || nf_die "cannot parse $CONFIG")
EOF
[ -n "$ANTIAD_URL" ] && [ -n "$ANTIAD_SHA256" ] || nf_die "missing anti-AD pin in $CONFIG"
[ -n "$ADRULES_URL" ] && [ -n "$ADRULES_SHA256" ] || nf_die "missing AdRules pin in $CONFIG"
[ -n "$NEODEV_URL" ] && [ -n "$NEODEV_SHA256" ] || nf_die "missing neodev pin in $CONFIG"
unset nf_key nf_value

# Fetch once. The rest of the build reads only from $SRC, so a moving upstream
# branch cannot mix old and new inputs within one build.
nf_fetch "$CHINA_DOMAINS_URL" "$SRC/china.conf"
nf_fetch "$GOOGLE_DOMAINS_URL" "$SRC/google.conf"
nf_fetch "$APPLE_DOMAINS_URL" "$SRC/apple.conf"
nf_fetch "$EASYLISTCHINA_EASYLIST_REJECT_URL" "$SRC/easylist.txt"
nf_fetch "$ADGUARD_DNS_REJECT_URL" "$SRC/adguard.txt"
nf_fetch "$PETERLOWE_REJECT_URL" "$SRC/peterlowe.txt"
nf_fetch "$DANPOLLOCK_REJECT_URL" "$SRC/danpollock.txt"
nf_fetch "$CUSTOM_DIRECT" "$SRC/custom-cn.txt"
nf_fetch "$CUSTOM_PROXY" "$SRC/custom-proxy.txt"
nf_fetch "$WIN_SPY" "$SRC/win-spy.txt"
nf_fetch "$WIN_UPDATE" "$SRC/win-update.txt"
nf_fetch "$WIN_EXTRA" "$SRC/win-extra.txt"
nf_fetch "$ANTIAD_URL" "$SRC/antiad.txt" "$ANTIAD_SHA256"
nf_fetch "$ADRULES_URL" "$SRC/adrules.txt" "$ADRULES_SHA256"
nf_fetch "$NEODEV_URL" "$SRC/neodev.txt" "$NEODEV_SHA256"

# geoip.dat is the only binary input and its publisher ships a checksum.
nf_fetch "$GEOIP_SUM_URL" "$SRC/geoip.dat.sha256sum"
GEOIP_EXPECTED=$(nf_read_sha256sum "$SRC/geoip.dat.sha256sum" geoip.dat) \
    || nf_die "invalid geoip.dat checksum file"
nf_fetch "$GEOIP_URL" "$SRC/geoip.dat" "$GEOIP_EXPECTED"
nf_verify_artifact "$SRC/geoip.dat" "$SRC/geoip.dat.sha256sum" geoip.dat

# Record digests of every input for the release body and for incident response.
python3 - "$SRC" <<'PY'
import hashlib
import os
import sys
from pathlib import Path

src = Path(sys.argv[1])
rows = []
for path in sorted(src.iterdir()):
    if path.name == "SHA256SUMS" or not path.is_file():
        continue
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    rows.append(f"{digest}  {path.name}\n")
(src / "SHA256SUMS").write_text("".join(rows), encoding="ascii")
print(f"recorded {len(rows)} source digests")
PY

wc -c "$SRC"/* | tail -1
