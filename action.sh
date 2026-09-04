#!/system/bin/sh
MODDIR=${0%/*}
"$MODDIR/tailscale/scripts/tailscale-service" toggle
