#!/system/bin/sh
SKIPUNZIP=1

if [ "$BOOTMODE" != true ]; then
  abort "Install from Magisk or KernelSU Manager, not recovery"
fi

case "$ARCH" in
  arm | arm64) F_ARCH="$ARCH" ;;
  *) abort "Unsupported architecture: $ARCH" ;;
esac

TS_DIR="/data/adb/tailscale"
TS_BIN="$TS_DIR/bin"
TS_CONFIG="$TS_DIR/config"
TS_LOGS="$TS_DIR/logs"
TS_RUN="$TS_DIR/run"
STATE_FILE="$TS_DIR/tailscaled.state"
LEGACY_STATE="$TS_DIR/tmp/tailscaled.state"

ui_print "- Installing Tailscale for $F_ARCH"
unzip -oq "$ZIPFILE" -x 'META-INF/*' 'files/*' -d "$MODPATH" || abort "Module extraction failed"
mkdir -p "$TS_BIN" "$TS_CONFIG" "$TS_LOGS" "$TS_RUN" || abort "Runtime directory creation failed"

if [ ! -f "$STATE_FILE" ] && [ -f "$LEGACY_STATE" ]; then
  mv "$LEGACY_STATE" "$STATE_FILE" || abort "Legacy state migration failed"
fi
if [ -f "$STATE_FILE" ]; then
  chmod 0600 "$STATE_FILE"
fi

if [ ! -f "$TS_CONFIG/module.conf" ]; then
  cp "$MODPATH/tailscale/config/module.conf" "$TS_CONFIG/module.conf" || abort "Default configuration install failed"
  chmod 0600 "$TS_CONFIG/module.conf"
fi

unzip -p "$ZIPFILE" "files/tailscale-$F_ARCH" > "$TS_BIN/tailscale.new" || abort "Missing tailscale binary"
unzip -p "$ZIPFILE" "files/tailscaled-$F_ARCH" > "$TS_BIN/tailscaled.new" || abort "Missing tailscaled binary"
chmod 0755 "$TS_BIN/tailscale.new" "$TS_BIN/tailscaled.new"
"$TS_BIN/tailscale.new" version >/dev/null 2>&1 || abort "Invalid tailscale binary"
"$TS_BIN/tailscaled.new" --version >/dev/null 2>&1 || abort "Invalid tailscaled binary"
mv -f "$TS_BIN/tailscale.new" "$TS_BIN/tailscale"
mv -f "$TS_BIN/tailscaled.new" "$TS_BIN/tailscaled"

if unzip -l "$ZIPFILE" "files/hev-socks5-tunnel-linux-$F_ARCH" 2>/dev/null | grep -q "hev-socks5-tunnel-linux-$F_ARCH"; then
  unzip -p "$ZIPFILE" "files/hev-socks5-tunnel-linux-$F_ARCH" > "$TS_BIN/hev-socks5-tunnel.new" || abort "Tunnel binary extraction failed"
  chmod 0755 "$TS_BIN/hev-socks5-tunnel.new"
  mv -f "$TS_BIN/hev-socks5-tunnel.new" "$TS_BIN/hev-socks5-tunnel"
fi

rm -rf "$TS_DIR/scripts"
rm -f "$TS_DIR/settings.ini" "$TS_DIR/settings.sh"

set_perm_recursive "$MODPATH/tailscale/scripts" 0 0 0755 0755
set_perm_recursive "$MODPATH/tailscale/config" 0 0 0755 0644
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
set_perm_recursive "$TS_BIN" 0 0 0755 0755
set_perm_recursive "$TS_CONFIG" 0 0 0700 0600
set_perm_recursive "$TS_LOGS" 0 0 0700 0600
set_perm_recursive "$TS_RUN" 0 0 0700 0600

ui_print "- Existing Tailscale state and preferences were preserved"
ui_print "- Reboot, then open Details to sign in"
