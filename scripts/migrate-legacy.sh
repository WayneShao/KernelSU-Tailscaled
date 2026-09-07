#!/system/bin/sh

kst_legacy_state() {
  if [ -f "$KST_LEGACY_DIR/tailscaled.state" ]; then
    printf '%s\n' "$KST_LEGACY_DIR/tailscaled.state"
  elif [ -f "$KST_LEGACY_DIR/tmp/tailscaled.state" ]; then
    printf '%s\n' "$KST_LEGACY_DIR/tmp/tailscaled.state"
  fi
}

kst_process_uses_root() (
  root=$1
  scope=${2:-legacy}
  for proc in /proc/[0-9]*; do
    [ -r "$proc/cmdline" ] || continue
    executable=$(readlink "$proc/exe" 2>/dev/null)
    case "$executable" in "$root/"*) exit 0 ;; esac
    if tr '\000' '\n' < "$proc/cmdline" 2>/dev/null | (
      while IFS= read -r argument; do
        if [ "$scope" = legacy ]; then
          case "$argument" in "$root"|"$root/"*) exit 0 ;; esac
        fi
        case "$argument" in "$root/"*)
          case "${argument##*/}" in
            tailscale|tailscaled|tailscale-supervisor|tailscale-daemon|tailscale-web|tailscale-tunnel|hev-socks5-tunnel) exit 0 ;;
          esac ;;
        esac
      done
      exit 1
    ); then exit 0; fi
  done
  exit 1
)

kst_migration_status() {
  if [ -e "$TS_DIR/migration.pending" ]; then
    printf '%s\n' '{"state":"migration-incomplete"}'
  elif [ -f "$TS_DIR/migration-awaiting-enable" ]; then
    printf '%s\n' '{"state":"awaiting-enable"}'
  elif [ -e "$TS_DIR/tailscaled.state" ]; then
    printf '%s\n' '{"state":"destination-exists"}'
  elif [ -n "$(kst_legacy_state)" ]; then
    printf '%s\n' '{"state":"migration-required"}'
  else
    printf '%s\n' '{"state":"no-legacy-identity"}'
  fi
}

kst_finish_migration() (
  pending="$TS_DIR/migration.pending"
  [ -d "$pending" ] && [ ! -L "$pending" ] || exit 1
  [ -z "$(find "$pending" -type l -print)" ] || exit 1
  kst_awk 'NF != 2 || length($1) != 64 || $1 ~ /[^0-9a-f]/ || $2 !~ /^(tailscaled.state|module.conf|migration-origin|migration-awaiting-enable)$/ { exit 1 }
    seen[$2]++ { exit 1 }
    END { if (!seen["tailscaled.state"] || !seen["migration-origin"] || !seen["migration-awaiting-enable"]) exit 1 }
  ' "$pending/journal.sha256" || { kst_error invalid-migration-journal; exit 1; }
  (cd "$pending" && sha256sum -c journal.sha256 >/dev/null 2>&1) || { kst_error migration-journal-changed; exit 1; }
  for marker in migration-origin migration-awaiting-enable; do
    [ ! -L "$TS_DIR/$marker" ] || exit 1
    if [ -e "$TS_DIR/$marker" ]; then
      cmp -s "$pending/$marker" "$TS_DIR/$marker" || { kst_error migration-marker-changed; exit 1; }
    else
      ln "$pending/$marker" "$TS_DIR/$marker" || exit 1
    fi
  done
  if [ -f "$pending/module.conf" ]; then
    [ ! -L "$TS_DIR/config/module.conf" ] || exit 1
    if [ -e "$TS_DIR/config/module.conf" ]; then
      cmp -s "$pending/module.conf" "$TS_DIR/config/module.conf" || { kst_error migration-config-changed; exit 1; }
    else
      cp "$pending/module.conf" "$pending/config.publish" || exit 1
      ln "$pending/config.publish" "$TS_DIR/config/module.conf" || exit 1
      rm -f "$pending/config.publish"
    fi
  fi
  # Persist preference and explicit-enable gates before making the identity visible.
  sync
  [ ! -L "$TS_DIR/tailscaled.state" ] || exit 1
  if [ -e "$TS_DIR/tailscaled.state" ]; then
    cmp -s "$pending/tailscaled.state" "$TS_DIR/tailscaled.state" || { kst_error migration-identity-changed; exit 1; }
  else
    ln "$pending/tailscaled.state" "$TS_DIR/tailscaled.state" || exit 1
  fi
  sync
  completed="$TS_DIR/.migration-complete.$$"
  [ ! -e "$completed" ] && [ ! -L "$completed" ] || exit 1
  mv "$pending" "$completed" || exit 1
  sync
  rm -rf "$completed" || true
  printf '%s\n' 'Legacy identity copied; legacy files preserved; runtime awaits explicit enable.'
)

kst_migrate_legacy() (
  source=$(kst_legacy_state)
  [ -n "$source" ] || { kst_error no-legacy-identity; exit 1; }
  if [ -L "$KST_LEGACY_DIR" ] || [ -L "${source%/*}" ] || [ -L "$source" ]; then
    kst_error symlink-legacy-state
    exit 1
  fi
  [ ! -e "$KST_LEGACY_MODULE" ] || [ -f "$KST_LEGACY_MODULE/disable" ] || [ -f "$KST_LEGACY_MODULE/remove" ] || { kst_error legacy-module-must-be-disabled; exit 1; }
  if kst_process_uses_root "$KST_LEGACY_DIR" || kst_process_uses_root "$KST_LEGACY_MODULE" || kst_process_uses_root "$TS_DIR/releases" components; then
    kst_error migration-requires-stopped-runtimes
    exit 1
  fi
  if [ -e "$TS_DIR/migration.pending" ] || [ -L "$TS_DIR/migration.pending" ]; then
    kst_finish_migration
    exit $?
  fi
  if [ -e "$TS_DIR/tailscaled.state" ] || [ -L "$TS_DIR/tailscaled.state" ]; then
    kst_error destination-identity-exists
    exit 1
  fi
  temporary=$(mktemp -d "$TS_DIR/.migration.XXXXXX") || exit 1
  trap 'rm -rf "$temporary"' EXIT HUP INT TERM
  if [ -e "$KST_LEGACY_DIR/config/module.conf" ]; then
    [ ! -L "$KST_LEGACY_DIR/config" ] && [ ! -L "$KST_LEGACY_DIR/config/module.conf" ] || exit 1
    if [ -e "$TS_DIR/config/module.conf" ] || [ -L "$TS_DIR/config/module.conf" ]; then
      kst_error destination-config-exists
      exit 1
    fi
    cp "$KST_LEGACY_DIR/config/module.conf" "$temporary/module.conf" || exit 1
    (CONFIG_DIR=$temporary; load_config) || { kst_error invalid-legacy-config; exit 1; }
  fi
  cp "$source" "$temporary/tailscaled.state" || exit 1
  chmod 0600 "$temporary/tailscaled.state" || exit 1
  cmp -s "$source" "$temporary/tailscaled.state" || exit 1
  printf '%s\n' legacy-copy-preserve-prefs > "$temporary/migration-origin"
  : > "$temporary/migration-awaiting-enable"
  (cd "$temporary" && sha256sum tailscaled.state migration-origin migration-awaiting-enable > journal.sha256) || exit 1
  [ ! -f "$temporary/module.conf" ] || (cd "$temporary" && sha256sum module.conf >> journal.sha256) || exit 1
  find "$temporary" -type f -exec chmod 0600 {} \; || exit 1
  mv "$temporary" "$TS_DIR/migration.pending" || exit 1
  trap - EXIT HUP INT TERM
  sync
  kst_finish_migration
)
