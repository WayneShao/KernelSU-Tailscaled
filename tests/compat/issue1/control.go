// Local-only test control plane; never authenticates real accounts.
package main

import (
	"log"
	"net"
	"net/http"
	"net/http/httptest"
	"strings"
	"tailscale.com/derp/derpserver"
	"tailscale.com/net/stun"
	"tailscale.com/tailcfg"
	"tailscale.com/tstest/integration/testcontrol"
	"tailscale.com/types/key"
)

func main() {
	udp, err := net.ListenUDP("udp4", &net.UDPAddr{IP: net.ParseIP("192.0.2.2"), Port: 13478})
	if err != nil {
		log.Fatal(err)
	}
	go func() {
		buf := make([]byte, 2048)
		for {
			n, a, e := udp.ReadFromUDPAddrPort(buf)
			if e != nil {
				return
			}
			id, e := stun.ParseBindingRequest(buf[:n])
			if e == nil {
				udp.WriteToUDPAddrPort(stun.Response(id, a), a)
			}
		}
	}()
	d := derpserver.New(key.NewNode(), log.Printf)
	hs := httptest.NewUnstartedServer(derpserver.Handler(d))
	hs.Listener.Close()
	hs.Listener, err = net.Listen("tcp", "192.0.2.2:18082")
	if err != nil {
		log.Fatal(err)
	}
	hs.StartTLS()
	defer hs.Close()
	dm := &tailcfg.DERPMap{Regions: map[tailcfg.DERPRegionID]*tailcfg.DERPRegion{1: {RegionID: 1, RegionCode: "fixture", Nodes: []*tailcfg.DERPNode{{Name: "fixture", RegionID: 1, HostName: "192.0.2.2", IPv4: "192.0.2.2", IPv6: "none", DERPPort: 18082, STUNPort: 13478, STUNTestIP: "192.0.2.2", InsecureForTests: true}}}}}
	s := &testcontrol.Server{ExplicitBaseURL: "http://kst-issue1.invalid:18081", RequireAuth: true, DERPMap: dm}
	handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/health" {
			w.WriteHeader(200)
			return
		}
		if strings.HasPrefix(r.URL.Path, "/auth/") {
			if s.CompleteAuth(r.URL.Path) {
				w.WriteHeader(200)
			} else {
				http.Error(w, "invalid test auth", 400)
			}
			return
		}
		s.ServeHTTP(w, r)
	})
	log.Fatal(http.ListenAndServe("192.0.2.2:18081", handler))
}
