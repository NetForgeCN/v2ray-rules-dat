# NetForgeCN v2ray-rules-dat

Self-maintained `geosite.dat` / `geoip.dat`, built from upstream Loyalsoldier full set **plus** the ad/privacy lists that upstream does not include.

## What is different from upstream

Base = `Loyalsoldier/v2ray-rules-dat` (all tags: `cn`, `china-list`, `geolocation-!cn`, `category-ads-all`, `apple-cn`, `google-cn`, `gfw`, `greatfire`, `win-*` ...).

Extra domains are injected into `category-ads-all` and exposed as independent tags:

| tag | source | format in source |
|---|---|---|
| `netforge-antiad` | privacy-protection-tools/anti-AD `anti-ad-domains.txt` | plain domain |
| `netforge-adrules` | Cats-Team/AdRules `mosdns_adrules.txt` | `domain:` prefix |
| `netforge-neodev` | neodevpro/neodevhost `domain` | plain domain |
| `netforge-ads` | union of the three above | plain domain |

`accelerated-domains.china.conf` is NOT duplicated: upstream already compiles it into `china-list` and `cn`.

All four extra tags are merged into `category-ads-all`, so a single `geosite:category-ads-all` rule already covers them.

## Download (stable paths)

- geosite.dat: `https://github.com/NetForgeCN/v2ray-rules-dat/releases/latest/download/geosite.dat`
- geosite.dat (CDN): `https://cdn.jsdelivr.net/gh/NetForgeCN/v2ray-rules-dat@release/geosite.dat`
- geoip.dat: `https://github.com/NetForgeCN/v2ray-rules-dat/releases/latest/download/geoip.dat`
- geoip.dat (CDN): `https://cdn.jsdelivr.net/gh/NetForgeCN/v2ray-rules-dat@release/geoip.dat`
- extra tag plaintext: `https://raw.githubusercontent.com/NetForgeCN/v2ray-rules-dat/release/netforge-ads.txt`

Third-party makefile (e.g. in your firmware) only needs the owner changed from `Loyalsoldier` to `NetForgeCN`; the repo name and file names are identical.

## Update policy

Upstream builds daily at 22:00 UTC (06:00 Beijing). This repo checks every 30 minutes and only builds when the latest upstream release is at least **2 hours old** and has not been built yet. Each release body records `upstream: <tag>` for idempotency.

Manual rebuild: Actions → Build NetForgeCN rules dat files → Run workflow.

## Customization

- `override/custom-sources.env` — URLs of extra ad lists.
- `override/direct.txt`, `override/proxy.txt`, `override/reject.txt` — domains to add.
- `override/*-need-to-remove.txt` — domains to remove.

## Credits / licensing

Upstream data from Loyalsoldier/v2ray-rules-dat, v2fly/domain-list-community, felixonmars/dnsmasq-china-list, anti-AD, Cats-Team/AdRules, neodevpro/neodevhost. Respect each upstream license and attribution when redistributing the generated files.
