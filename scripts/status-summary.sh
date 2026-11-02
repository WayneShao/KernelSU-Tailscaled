#!/system/bin/sh
# shellcheck disable=SC2317

MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled}
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
KST_STAGED_DIR=${KST_STAGED_DIR:-/data/adb/modules_update/kernelsu-tailscaled}
KST_BUSYBOX=${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}
KST_CLI_TIMEOUT=${KST_CLI_TIMEOUT:-3}

summary_file() {
  file=$1
  [ -f "$file" ] || return 0
  description=$2
  unchanged=0
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      description=*)
        [ "${line#description=}" = "$description" ] || { unchanged=0; break; }
        unchanged=1 ;;
    esac
  done < "$file"
  [ "$unchanged" = 1 ] && return 0
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

BUNDLE_DIR=${BUNDLE_DIR:-$TS_DIR/current}
ENGINE_DIR=$BUNDLE_DIR
if [ -f "$BUNDLE_DIR/tailscale/scripts/engine-lib.sh" ]; then
  . "$BUNDLE_DIR/tailscale/scripts/engine-lib.sh"
  engine_select || exit 1
fi
version=$(sed -n '1p' "$ENGINE_DIR/engine-version" 2>/dev/null)
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
cli="$ENGINE_DIR/bin/tailscale"
if [ -S "$TS_DIR/run/tailscaled.sock" ] && [ -x "$cli" ]; then
  case "$lifecycle" in
    running|degraded)
      candidate=$(
        if [ -x "$KST_BUSYBOX" ]; then
          "$KST_BUSYBOX" timeout -s KILL "$KST_CLI_TIMEOUT" "$cli" --socket="$TS_DIR/run/tailscaled.sock" ip -4
        else
          timeout -s KILL "$KST_CLI_TIMEOUT" "$cli" --socket="$TS_DIR/run/tailscaled.sock" ip -4
        fi 2>/dev/null | head -n 1
      )
      case "$candidate" in [0-9]*.[0-9]*.[0-9]*.[0-9]*) ip=$candidate ;; esac ;;
  esac
fi
ui='UI unavailable'
[ -S "$TS_DIR/run/tailscaled.sock" ] && ui='UI ready'
pending=''
if [ -f "$KST_STAGED_DIR/module.prop" ]; then
  staged=$(sed -n 's/^version=//p' "$KST_STAGED_DIR/module.prop" 2>/dev/null | head -n 1)
  [ -n "$staged" ] && pending=" | update pending reboot: $staged"
fi
summary="[$state] Tailscale($(sanitize "$version")) | $(sanitize "$ip") | $ui$pending"
summary_file "$MODDIR/module.prop" "$summary"
