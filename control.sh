#!/system/bin/sh

ENTRY_DIR=$(cd "${0%/*}" && pwd -P) || exit 1
case "$ENTRY_DIR" in
  /data/adb/modules_update/kernelsu-tailscaled) MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled} ;;
  *) MODDIR=${MODDIR:-$ENTRY_DIR} ;;
esac
MODDIR=$(cd "$MODDIR" && pwd -P) || exit 1
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
BUNDLE_DIR=$ENTRY_DIR
# Boot alone reconciles the manager's newly activated ZIP with the selected runtime.
if { [ "${1:-}" != boot ] || [ ! -f "$ENTRY_DIR/update" ]; } && \
  { [ -e "$TS_DIR/current" ] || [ -L "$TS_DIR/current" ]; }; then
  [ -L "$TS_DIR/current" ] || exit 1
  BUNDLE_DIR=$(readlink -f "$TS_DIR/current") || exit 1
  releases=$(cd "$TS_DIR/releases" && pwd -P) || exit 1
  [ "${BUNDLE_DIR%/*}" = "$releases" ] && [ -d "$BUNDLE_DIR" ] || exit 1
fi
export MODDIR TS_DIR BUNDLE_DIR
exec sh "$BUNDLE_DIR/scripts/runtime-control.sh" "$@"
