#!/system/bin/sh
# shellcheck disable=SC2317

MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled}
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
KST_STAGED_DIR=${KST_STAGED_DIR:-/data/adb/modules_update/kernelsu-tailscaled}
SUMMARY_BASE=${SUMMARY_BASE:-Tailscale service with KernelSU WebUI}

summary_file() {
  file=$1
  [ -f "$file" ] || return 0
  description=$2
  temporary="$file.tmp.$$"
  awk -v description="$description" '
    /^description=/ { print "description=" description; found=1; next }
    { print }
    END { if (!found) print "description=" description }
  ' "$file" > "$temporary" || { rm -f "$temporary"; return 0; }
  chmod 0644 "$temporary" 2>/dev/null || true
  mv -f "$temporary" "$file" 2>/dev/null || rm -f "$temporary"
}

sanitize() {
  printf '%s' "$1" | tr '\r\n|' '   ' | cut -c 1-48
}

version=$(sed -n '1p' "$TS_DIR/current/engine-version" 2>/dev/null)
lifecycle=$(sed -n '1p' "$TS_DIR/run/lifecycle" 2>/dev/null)
[ -n "$lifecycle" ] || lifecycle=unknown
case "$lifecycle" in
  running) state='service is running' ;;
  stopped|disabled) state='service is stopped' ;;
  degraded) state='service degraded' ;;
  failed) state='service failed' ;;
  *) state="service $lifecycle" ;;
esac
ip='not ready'
cli="$TS_DIR/current/bin/tailscale"
if [ -x "$cli" ]; then
  candidate=$($cli --socket="$TS_DIR/run/tailscaled.sock" ip -4 2>/dev/null | head -n 1)
  case "$candidate" in [0-9]*.[0-9]*.[0-9]*.[0-9]*) ip=$candidate ;; esac
fi
ui='UI unavailable'
[ -S "$TS_DIR/run/tailscaled.sock" ] && ui='UI ready'
pending=''
if [ -f "$KST_STAGED_DIR/module.prop" ]; then
  staged=$(sed -n 's/^version=//p' "$KST_STAGED_DIR/module.prop" 2>/dev/null | head -n 1)
  [ -n "$staged" ] && pending=" | update pending reboot: $staged"
fi
summary="[$(date '+%H:%M') | $state] Tailscale($(sanitize "$version")) | $(sanitize "$ip") | $ui$pending"
summary_file "$MODDIR/module.prop" "$summary"
