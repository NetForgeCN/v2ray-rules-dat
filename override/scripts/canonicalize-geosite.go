// canonicalize-geosite rewrites a geosite.dat with a stable protobuf encoding.
//
// The pinned upstream builder iterates Go maps when assembling GeoSiteList and
// when flattening included lists, so two builds from identical inputs can
// differ only in entry/domain/attribute order. V2Ray treats those collections
// as unordered sets; sorting them preserves meaning while making the artifact
// byte-for-byte reproducible.
//
// Run it from the domain-list-custom module directory so its go.mod supplies
// the routercommon and protobuf dependencies:
//
//	go run ../selfrepo/override/scripts/canonicalize-geosite.go ./publish/geosite.dat
package main

import (
	"fmt"
	"os"
	"sort"
	"strings"

	router "github.com/v2fly/v2ray-core/v5/app/router/routercommon"
	"google.golang.org/protobuf/encoding/prototext"
	"google.golang.org/protobuf/proto"
)

func attrKey(attr *router.Domain_Attribute) string {
	if attr == nil {
		return ""
	}
	return prototext.Format(attr)
}

func domainKey(domain *router.Domain) string {
	if domain == nil {
		return ""
	}
	attrs := make([]string, 0, len(domain.GetAttribute()))
	for _, attr := range domain.GetAttribute() {
		attrs = append(attrs, attrKey(attr))
	}
	sort.Strings(attrs)
	return fmt.Sprintf("%d\x00%s\x00%s", domain.GetType(), domain.GetValue(), strings.Join(attrs, "\x00"))
}

func siteKey(site *router.GeoSite) string {
	if site == nil {
		return ""
	}
	return fmt.Sprintf("%s\x00%s\x00%x\x00%s",
		site.GetCountryCode(), site.GetCode(), site.GetResourceHash(), site.GetFilePath())
}

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: canonicalize-geosite <geosite.dat>")
		os.Exit(2)
	}
	path := os.Args[1]

	raw, err := os.ReadFile(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read %s: %v\n", path, err)
		os.Exit(1)
	}
	list := new(router.GeoSiteList)
	if err := proto.Unmarshal(raw, list); err != nil {
		fmt.Fprintf(os.Stderr, "unmarshal %s: %v\n", path, err)
		os.Exit(1)
	}

	for _, site := range list.GetEntry() {
		for _, domain := range site.GetDomain() {
			attrs := domain.GetAttribute()
			sort.SliceStable(attrs, func(i, j int) bool {
				return attrKey(attrs[i]) < attrKey(attrs[j])
			})
		}
		sort.SliceStable(site.Domain, func(i, j int) bool {
			return domainKey(site.Domain[i]) < domainKey(site.Domain[j])
		})
	}
	sort.SliceStable(list.Entry, func(i, j int) bool {
		return siteKey(list.Entry[i]) < siteKey(list.Entry[j])
	})

	out, err := proto.MarshalOptions{Deterministic: true}.Marshal(list)
	if err != nil {
		fmt.Fprintf(os.Stderr, "marshal %s: %v\n", path, err)
		os.Exit(1)
	}
	tmp := path + ".canonical.tmp"
	if err := os.WriteFile(tmp, out, 0644); err != nil {
		fmt.Fprintf(os.Stderr, "write %s: %v\n", tmp, err)
		os.Exit(1)
	}
	if err := os.Rename(tmp, path); err != nil {
		fmt.Fprintf(os.Stderr, "replace %s: %v\n", path, err)
		os.Remove(tmp)
		os.Exit(1)
	}
	fmt.Printf("canonicalized %s: %d entries\n", path, len(list.GetEntry()))
}
