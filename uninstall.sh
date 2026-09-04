#!/system/bin/sh
MODDIR=${0%/*}
"$MODDIR/tailscale/scripts/tailscale-service" stop >/dev/null 2>&1 || true
rm -rf /data/adb/tailscale
