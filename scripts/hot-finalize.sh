#!/system/bin/sh

MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled}
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
KST_STAGED_DIR=${KST_STAGED_DIR:-/data/adb/modules_update/kernelsu-tailscaled}
BUNDLE_DIR=${BUNDLE_DIR:-$TS_DIR/current}

[ -f "$MODDIR/update" ] && [ ! -L "$MODDIR/update" ] || exit 0
[ -d "$KST_STAGED_DIR" ] && [ ! -L "$KST_STAGED_DIR" ] || exit 0
[ -f "$BUNDLE_DIR/bundle.sha256" ] && [ -f "$KST_STAGED_DIR/bundle.sha256" ] || exit 0
cmp -s "$BUNDLE_DIR/bundle.sha256" "$KST_STAGED_DIR/bundle.sha256" || exit 0

prop() { sed -n "s/^$2=//p" "$1/module.prop" 2>/dev/null | head -n 1; }
code=$(prop "$BUNDLE_DIR" versionCode)
[ -n "$code" ] && [ "$code" = "$(prop "$KST_STAGED_DIR" versionCode)" ] && \
  [ "$code" = "$(prop "$MODDIR" versionCode)" ] || exit 0

for name in control.sh action.sh service.sh uninstall.sh; do
  [ -f "$MODDIR/$name" ] && cmp -s "$BUNDLE_DIR/$name" "$MODDIR/$name" || exit 0
done
manager_view_valid=1
while read -r digest relative; do
  case "$relative" in
    webroot/*)
      [ -f "$MODDIR/$relative" ] || { manager_view_valid=0; break; }
      [ "$(sha256sum "$MODDIR/$relative" | cut -d ' ' -f 1)" = "$digest" ] || { manager_view_valid=0; break; }
      ;;
  esac
done < "$BUNDLE_DIR/bundle.sha256"
[ "$manager_view_valid" = 1 ] || exit 0

[ "$(sed -n '1p' "$TS_DIR/run/wanted" 2>/dev/null)" = 1 ] || exit 0
[ "$(sed -n '1p' "$TS_DIR/run/lifecycle" 2>/dev/null)" = running ] || exit 0
[ -S "$TS_DIR/run/tailscaled.sock" ] || exit 0
"$BUNDLE_DIR/bin/tailscale" --socket="$TS_DIR/run/tailscaled.sock" ip -4 >/dev/null 2>&1 || exit 0

rm -f "$MODDIR/update" || exit 0
rm -rf "$KST_STAGED_DIR"
