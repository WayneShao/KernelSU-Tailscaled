#!/system/bin/sh
MODDIR=${0%/*}
sh "$MODDIR/control.sh" stop
# Identity and generations are retained for an explicit reinstall or manual purge.
