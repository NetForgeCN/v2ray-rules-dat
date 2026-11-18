# NetForgeCN v2ray-rules-dat

Self-maintained `geosite.dat` / `geoip.dat` for V2Ray-family routers. Built from the Loyalsoldier full rule set plus additional ad/privacy domain lists, published as GitHub release assets with `sha256sum` files.

## Rule Sets

The baseline is `Loyalsoldier/v2ray-rules-dat` (tags: `cn`, `china-list`, `geolocation-!cn`, `category-ads-all`, `apple-cn`, `google-cn`, `gfw`, `greatfire`, `win-*` and the rest). Four extra tags are compiled in:

| tag | source | format in source |
|---|---|---|
| `netforge-antiad` | privacy-protection-tools/anti-AD `anti-ad-domains.txt` | plain domain |
| `netforge-adrules` | Cats-Team/AdRules `mosdns_adrules.txt` | `domain:` prefix |
| `netforge-neodev` | neodevpro/neodevhost `domain` | plain domain |
| `netforge-ads` | union of the three above | plain domain |

All four extra tags are merged into `category-ads-all`, so a single `geosite:category-ads-all` rule covers them. China acceleration domains are provided by the upstream `china-list` and `cn` tags.

## Download (stable paths)

- geosite.dat: `https://github.com/NetForgeCN/v2ray-rules-dat/releases/latest/download/geosite.dat`
- geosite.dat (CDN): `https://cdn.jsdelivr.net/gh/NetForgeCN/v2ray-rules-dat@release/geosite.dat`
- geoip.dat: `https://github.com/NetForgeCN/v2ray-rules-dat/releases/latest/download/geoip.dat`
- geoip.dat (CDN): `https://cdn.jsdelivr.net/gh/NetForgeCN/v2ray-rules-dat@release/geoip.dat`
- extra tag plaintext: `https://raw.githubusercontent.com/NetForgeCN/v2ray-rules-dat/release/netforge-ads.txt`

Each asset has a matching `.sha256sum`. A downstream OpenWrt package can consume these URLs directly; [NetForgeCN/Loyalsoldier](https://github.com/NetForgeCN/Loyalsoldier) is the packaging layer that turns them into `v2ray-geoip` / `v2ray-geosite` packages.

## Update Policy

The upstream project builds daily at 22:00 UTC (06:00 Beijing). This repository checks every 30 minutes and builds when the latest upstream release is at least **2 hours old** and has not been built yet. Each release body records `upstream: <tag>` for idempotency.

Manual rebuild: Actions → **Build NetForgeCN rules dat files** → Run workflow.

## Customization

- `override/custom-sources.env` — URLs of extra ad lists.
- `override/direct.txt`, `override/proxy.txt`, `override/reject.txt` — domains to add.
- `override/*-need-to-remove.txt` — domains to remove.

## License

GPL-3.0, see [LICENSE](LICENSE).

Upstream data comes from Loyalsoldier/v2ray-rules-dat, v2fly/domain-list-community, felixonmars/dnsmasq-china-list, anti-AD, Cats-Team/AdRules and neodevpro/neodevhost. Respect each upstream license and attribution when redistributing the generated files.
