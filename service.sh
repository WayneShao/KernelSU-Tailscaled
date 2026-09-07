#!/system/bin/sh
MODDIR=${0%/*}

[ -f "$MODDIR/disable" ] && exit 0
while [ "$(getprop sys.boot_completed)" != "1" ]; do
  sleep 1
done
sleep 3
[ -f "$MODDIR/disable" ] && exit 0
sh "$MODDIR/control.sh" boot
