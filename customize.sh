#!/system/bin/sh
SKIPUNZIP=1

if [ "$BOOTMODE" != true ]; then
  abort "Install from Magisk or KernelSU Manager, not recovery"
fi

case "$ARCH" in
  arm | arm64) F_ARCH="$ARCH" ;;
  *) abort "Unsupported architecture: $ARCH" ;;
esac

ui_print "- Installing KernelSU-Tailscaled for $F_ARCH"
unzip -oq "$ZIPFILE" -x 'META-INF/*' 'files/*' -d "$MODPATH" || abort "Module extraction failed"
mkdir -p "$MODPATH/bin" || abort "Candidate directory creation failed"
unzip -p "$ZIPFILE" "files/tailscale-$F_ARCH" > "$MODPATH/bin/tailscale" || abort "Missing tailscale binary"
unzip -p "$ZIPFILE" "files/tailscaled-$F_ARCH" > "$MODPATH/bin/tailscaled" || abort "Missing tailscaled binary"
unzip -p "$ZIPFILE" "files/bundle-$F_ARCH.sha256" > "$MODPATH/bundle.sha256" || abort "Missing bundle manifest"
unzip -p "$ZIPFILE" files/VERSION.txt > "$MODPATH/engine-version" || abort "Missing engine version"

if unzip -l "$ZIPFILE" "files/hev-socks5-tunnel-linux-$F_ARCH" 2>/dev/null | grep -q "hev-socks5-tunnel-linux-$F_ARCH"; then
  unzip -p "$ZIPFILE" "files/hev-socks5-tunnel-linux-$F_ARCH" > "$MODPATH/bin/hev-socks5-tunnel" || abort "Tunnel binary extraction failed"
fi

. "$MODPATH/scripts/bundle-lib.sh"
kst_verify_bundle "$MODPATH" || abort "Candidate integrity verification failed"
set_perm_recursive "$MODPATH/bin" 0 0 0755 0755
set_perm_recursive "$MODPATH/scripts" 0 0 0755 0755
set_perm_recursive "$MODPATH/tailscale/scripts" 0 0 0755 0755
set_perm_recursive "$MODPATH/tailscale/config" 0 0 0755 0644
set_perm "$MODPATH/control.sh" 0 0 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/action.sh" 0 0 0755
set_perm "$MODPATH/uninstall.sh" 0 0 0755
timeout 10 "$MODPATH/bin/tailscale" version >/dev/null 2>&1 || abort "Invalid tailscale binary"
timeout 10 "$MODPATH/bin/tailscaled" --version >/dev/null 2>&1 || abort "Invalid tailscaled binary"
ui_print "- Candidate verified; completing runtime and manager installation"
sh "$MODPATH/scripts/install-runtime.sh" "$MODPATH" || abort "Runtime installation failed"
ui_print "- KernelSU WebUI and Action are ready without reboot"
