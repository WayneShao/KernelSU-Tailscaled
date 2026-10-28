// Integration probe against the actual upstream packages, not rewritten logic.
package main

import (
	"context"
	"fmt"
	"golang.org/x/sys/unix"
	"log"
	"net"
	"os"
	"syscall"
	_ "tailscale.com/feature/androiddns"
	"tailscale.com/net/dnscache"
	"tailscale.com/net/netmon"
	"tailscale.com/net/netns"
	"time"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "dns-android" {
		androidDNS()
		return
	}
	if len(os.Args) > 1 && os.Args[1] == "combined" {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		ip, _, _, err := dnscache.Get().LookupIP(ctx, "kst-issue1.invalid")
		fmt.Printf("combined-control-DNS=%v error=%v\n", ip, err)
		if err != nil {
			os.Exit(1)
		}
		os.Args[1] = net.JoinHostPort(ip.String(), "18080")
	}
	fd, err := unix.Socket(unix.AF_NETLINK, unix.SOCK_RAW, unix.NETLINK_ROUTE)
	if err != nil {
		log.Fatal(err)
	}
	fmt.Printf("strict-option=%v\n", unix.SetsockoptInt(fd, 270, 12, 1))
	unix.Close(fd)
	iface, err := netmon.DefaultRouteInterface()
	fmt.Printf("default-interface=%q error=%v\n", iface, err)
	if len(os.Args) < 2 {
		os.Exit(2)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	plain, plainErr := (&net.Dialer{}).DialContext(ctx, "tcp", os.Args[1])
	if plain != nil {
		plain.Close()
	}
	fmt.Printf("unbound-dial=%v\n", plainErr)
	ctx2, cancel2 := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel2()
	nd := &net.Dialer{}
	scoped := netns.FromDialer(log.Printf, netmon.NewStatic(), nd)
	originalControl := nd.Control
	nd.Control = func(network, address string, raw syscall.RawConn) error {
		e := originalControl(network, address, raw)
		raw.Control(func(fd uintptr) {
			bound, _ := unix.GetsockoptString(int(fd), unix.SOL_SOCKET, unix.SO_BINDTODEVICE)
			fmt.Printf("bound-interface=%q\n", bound)
		})
		return e
	}
	c, dialErr := scoped.DialContext(ctx2, "tcp", os.Args[1])
	if c != nil {
		c.Close()
	}
	fmt.Printf("netns-dial=%v\n", dialErr)
	if err != nil || dialErr != nil || plainErr != nil {
		os.Exit(1)
	}
}
func androidDNS() {
	fmt.Printf("android-default-installed=%v control-dial-installed=%v\n", net.DefaultResolver.Dial != nil, dnscache.Get().Forward.Dial != nil)
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	ips, err := net.DefaultResolver.LookupIP(ctx, "ip4", "kst-issue1.invalid")
	fmt.Printf("android-default=%v error=%v\n", ips, err)
	if err != nil {
		os.Exit(2)
	}
	ip, _, _, err := dnscache.Get().LookupIP(ctx, "kst-issue1.invalid")
	fmt.Printf("android-control-cache=%v error=%v\n", ip, err)
	if err != nil || ip.String() != "192.0.2.2" {
		os.Exit(1)
	}
}
