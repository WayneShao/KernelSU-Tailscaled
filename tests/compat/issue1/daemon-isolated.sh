#!/usr/bin/env bash
set -euo pipefail
if [[ ${1:-} != --inside ]]; then
 [[ $# == 5 ]] || { echo "usage: $0 DAEMON CLI TESTCONTROL SECCOMP OUTPUT_DIR"; exit 2; }
 exec unshare --user --map-root-user --net --mount "$0" --inside "$(realpath "$1")" "$(realpath "$2")" "$(realpath "$3")" "$(realpath "$4")" "$(realpath "$5")"
fi
daemon=$2; cli=$3; control=$4; reject=$5; output=$6
work=$(mktemp -d "$output/daemon-case.XXXXXX")
echo "DAEMON_EVIDENCE=$work"
holder=; control_pid=; dns_pid=; daemon_pid=; up_pid=
cleanup(){
 for pid in "$up_pid" "$daemon_pid" "$dns_pid" "$control_pid" "$holder"; do [[ -z $pid ]] || kill "$pid" 2>/dev/null || :; done
}
trap cleanup EXIT
mount --make-rprivate /
: > "$work/resolv.conf"; mount --bind "$work/resolv.conf" /etc/resolv.conf
: > "$work/tun"; mount --bind /dev/net/tun "$work/tun"
ip link set lo up
unshare --net sleep 180 & holder=$!
for _ in {1..50}; do [[ $(readlink /proc/"$holder"/ns/net) != $(readlink /proc/self/ns/net) ]] && break; sleep .02; done
ip link add wan0 type veth peer name peer0
ip link set peer0 netns "$holder"
ip addr add 192.0.2.1/24 dev wan0; ip link set wan0 up
nsenter -t "$holder" -n ip addr add 192.0.2.2/24 dev peer0
nsenter -t "$holder" -n ip link set peer0 up
nsenter -t "$holder" -n ip link set lo up
ip route add default via 192.0.2.2 dev wan0 table 100
ip rule add pref 10000 lookup 100
ip rule add pref 5210 fwmark 0x80000/0xff0000 lookup main
ip rule add pref 5230 fwmark 0x80000/0xff0000 lookup default
ip rule add pref 5250 fwmark 0x80000/0xff0000 unreachable
unset ALL_PROXY all_proxy HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
mount -t tmpfs tmpfs /dev
mkdir -p /dev/socket /dev/__properties__ /dev/net
: > /dev/null; : > /dev/net/tun; mount --bind "$work/tun" /dev/net/tun
python3 "$(dirname "$0")/dnsproxyd.py" > "$work/dns.log" 2>&1 & dns_pid=$!
nsenter -t "$holder" -n "$control" > "$work/control.log" 2>&1 & control_pid=$!
for _ in {1..100}; do [[ -S /dev/socket/dnsproxyd ]] && curl -fsS --max-time 1 http://192.0.2.2:18081/health >/dev/null && break; sleep .05; done
export TS_FORCE_LINUX_BIND_TO_DEVICE=true TS_NO_LOGS_NO_SUPPORT=true
"$reject" "$daemon" --state="$work/tailscaled.state" --socket="$work/tailscaled.sock" --tun=tailscale0 --port=0 > "$work/daemon.log" 2>&1 & daemon_pid=$!
for _ in {1..100}; do [[ -S "$work/tailscaled.sock" ]] && break; kill -0 "$daemon_pid"; sleep .05; done
timeout 25 "$cli" --socket="$work/tailscaled.sock" up --login-server=http://kst-issue1.invalid:18081 --netfilter-mode=off --accept-dns=false --timeout=20s > "$work/up.log" 2>&1 & up_pid=$!
auth=
for _ in {1..200}; do
 auth=$(grep -o 'http://kst-issue1.invalid:18081/auth/[a-f0-9]*' "$work/up.log" | head -1 || :)
 [[ -n $auth ]] && break
 kill -0 "$up_pid" 2>/dev/null || break
 sleep .05
done
if [[ -z $auth ]]; then echo 'FAIL: no fresh-login auth URL'; cat "$work/up.log"; tail -12 "$work/daemon.log"; exit 1; fi
curl -fsS --max-time 3 --resolve kst-issue1.invalid:18081:192.0.2.2 "$auth"
wait "$up_pid"; up_pid=
"$cli" --socket="$work/tailscaled.sock" status --json > "$work/status.json"
python3 - "$work/status.json" <<'PY'
import json,sys
s=json.load(open(sys.argv[1]));assert s['BackendState']=='Running',s['BackendState'];assert s['TailscaleIPs'];print('PASS: fresh native daemon authorized against isolated control, BackendState=Running')
PY
ip link show tailscale0
