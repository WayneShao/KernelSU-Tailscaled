#!/usr/bin/env bash
set -euo pipefail
# No host route/DNS writes: all setup happens in fresh user/net/mount namespaces.
if [[ ${1:-} != --inside ]]; then
  [[ $# == 2 ]] || { echo "usage: $0 PROBE SECCOMP_LAUNCHER"; exit 2; }
  exec unshare --user --map-root-user --net --mount "$0" --inside "$(realpath "$1")" "$(realpath "$2")"
fi
probe=$2; reject=$3
work=$(mktemp -d)
server=; holder=; dns_server=
cleanup() { [[ -z $dns_server ]] || kill "$dns_server" 2>/dev/null || :; [[ -z $server ]] || kill "$server" 2>/dev/null || :; [[ -z $holder ]] || kill "$holder" 2>/dev/null || :; rm -f "$work/resolv.conf"; rmdir "$work"; }
trap cleanup EXIT
mount --make-rprivate /
# Empty DNS config triggers Go's loopback DNS behavior only inside this namespace.
: > "$work/resolv.conf"
mount --bind "$work/resolv.conf" /etc/resolv.conf
ip link set lo up
unshare --net sleep 300 & holder=$!
for _ in {1..50}; do
 [[ $(readlink /proc/"$holder"/ns/net) != $(readlink /proc/self/ns/net) ]] && break
 sleep .02
done
ip link add wan0 type veth peer name peer0
ip link set peer0 netns "$holder"
ip addr add 192.0.2.1/24 dev wan0
ip link set wan0 up
nsenter -t "$holder" -n ip addr add 192.0.2.2/24 dev peer0
nsenter -t "$holder" -n ip link set peer0 up
nsenter -t "$holder" -n ip link set lo up
nsenter -t "$holder" -n python3 -m http.server 18080 --bind 192.0.2.2 >/dev/null 2>&1 & server=$!
ip route add default via 192.0.2.2 dev wan0 table 100
ip rule add pref 10000 lookup 100
ip rule add pref 5210 fwmark 0x80000/0xff0000 lookup main
ip rule add pref 5230 fwmark 0x80000/0xff0000 lookup default
ip rule add pref 5250 fwmark 0x80000/0xff0000 unreachable
unset ALL_PROXY all_proxy HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
export TS_FORCE_LINUX_BIND_TO_DEVICE=true
for _ in {1..50}; do curl --silent --max-time 1 http://192.0.2.2:18080/ >/dev/null && break; sleep .02; done
echo '=== routes ==='; ip route show table main; ip rule; cat /proc/net/route
set +e
echo '=== supported strict option control ==='; "$probe" 192.0.2.2:18080; normal=$?
echo '=== strict option ENOPROTOOPT ==='; "$reject" "$probe" 192.0.2.2:18080; unsupported=$?
# Activate the actual upstream Android detection and dnsproxyd adapter.
mount -t tmpfs tmpfs /dev
mkdir -p /dev/socket /dev/__properties__
touch /dev/null
python3 "$(dirname "$0")/dnsproxyd.py" & dns_server=$!
for _ in {1..50}; do [[ -S /dev/socket/dnsproxyd ]] && break; sleep .02; done
echo '=== actual androiddns initialization ==='; "$probe" dns-android; android_dns=$?
echo '=== combined real adapter + unsupported strict option ==='; "$reject" "$probe" combined; combined=$?
printf 'RESULT android_dns=%s combined=%s\n' "$android_dns" "$combined"
echo '=== EOPNOTSUPP fallback ==='; KST_NETLINK_ERRNO=95 "$reject" "$probe" 192.0.2.2:18080; notsupported=$?
echo '=== permission failure must remain explicit ==='
permission_output=$(KST_NETLINK_ERRNO=1 "$reject" "$probe" 192.0.2.2:18080 2>&1); permission=$?
printf '%s\n' "$permission_output"
# Selecting a different physical name must not require a hardcoded wlan name.
ip link set wan0 name cellular0
echo '=== changed outbound interface ==='; "$reject" "$probe" 192.0.2.2:18080; changed=$?
ip route del default table 100
echo '=== absent default route must remain explicit ==='
offline_output=$("$probe" 192.0.2.2:18080 2>&1); offline=$?
printf '%s\n' "$offline_output"
ip route add default via 192.0.2.2 dev cellular0 table 100
echo '=== restored route ==='; "$reject" "$probe" combined; recovered=$?
printf 'RESULT normal=%s unsupported=%s android_dns=%s combined=%s notsupported=%s permission=%s changed=%s offline=%s recovered=%s\n' "$normal" "$unsupported" "$android_dns" "$combined" "$notsupported" "$permission" "$changed" "$offline" "$recovered"
[[ $normal == 0 && $unsupported == 0 && $android_dns == 0 && $combined == 0 && $notsupported == 0 && $permission == 1 && $changed == 0 && $offline == 1 && $recovered == 0 ]] &&
[[ $permission_output == *"finding outbound interface"* && $permission_output != *'bound-interface="lo"'* ]] &&
[[ $offline_output == *"finding outbound interface"* && $offline_output != *'bound-interface="lo"'* ]]
