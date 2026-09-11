#!/system/bin/sh

MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled}
MODDIR=$(cd "$MODDIR" && pwd -P) || exit 1
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
KST_STAGED_DIR=${KST_STAGED_DIR:-/data/adb/modules_update/kernelsu-tailscaled}
KST_LEGACY_DIR=${KST_LEGACY_DIR:-/data/adb/tailscale}
KST_LEGACY_MODULE=${KST_LEGACY_MODULE:-/data/adb/modules/magisk-tailscaled}
export MODDIR TS_DIR KST_STAGED_DIR KST_LEGACY_DIR KST_LEGACY_MODULE

BUNDLE_DIR=${BUNDLE_DIR:-${0%/scripts/*}}
export BUNDLE_DIR
. "$BUNDLE_DIR/scripts/bundle-lib.sh"
kst_private_root || exit 1
. "$BUNDLE_DIR/tailscale/scripts/common.sh"
. "$BUNDLE_DIR/scripts/activate-runtime.sh"
. "$BUNDLE_DIR/scripts/migrate-legacy.sh"

kst_dispatch() {
  if [ "$1" != boot ]; then
    locked_current=$(kst_current) || return 1
    if [ -n "$locked_current" ] && [ "$locked_current" != "$BUNDLE_DIR" ]; then
      BUNDLE_DIR=$locked_current sh "$locked_current/scripts/runtime-control.sh" "$1" 9>&9
      return $?
    fi
  fi
  case "$1" in
    migration-status) kst_migration_status ;;
    migrate-legacy) kst_migrate_legacy ;;
    apply-staged) kst_apply_staged ;;
    boot)
      [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || return 0
      [ ! -f "$TS_DIR/migration-awaiting-enable" ] || return 0
      kst_require_identity_choice || return 1
      existing=$(kst_current) || return 1
      manager_version=$(sed -n 's/^versionCode=//p' "$BUNDLE_DIR/module.prop" 2>/dev/null | head -n 1)
      current_version=$(sed -n 's/^versionCode=//p' "$existing/module.prop" 2>/dev/null | head -n 1)
      manager_digest=$(sha256sum "$BUNDLE_DIR/bundle.sha256" 2>/dev/null | cut -d ' ' -f 1)
      current_digest=$(sha256sum "$existing/bundle.sha256" 2>/dev/null | cut -d ' ' -f 1)
      if [ -n "$existing" ] && [ -n "$manager_version" ] && [ "$manager_version" = "$current_version" ] && [ -n "$manager_digest" ] && [ "$manager_digest" = "$current_digest" ]; then
        # Boot starts the verified generation; the manager directory also has
        # UI and metadata files outside the immutable runtime manifest.
        kst_runtime "$existing" start
      else
        kst_prepare_manager
      fi
      ;;
    start|enable|restart|toggle)
      kst_require_identity_choice || return 1
      kst_prepare_initial || return 1
      rm -f "$TS_DIR/migration-awaiting-enable"
      kst_runtime "$(kst_current)" "$1"
      ;;
    stop|disable|status|status-json|logs|diagnostics|web-restart)
      selected=$(kst_current) || return 1
      [ -n "$selected" ] || selected=$BUNDLE_DIR
      kst_runtime "$selected" "$1"
      ;;
    *) kst_error unsupported-command; return 2 ;;
  esac
}

[ "$#" -eq 1 ] || { kst_error one-command-required; exit 2; }
with_control_lock kst_dispatch "$1"
result=$?
sh "$BUNDLE_DIR/scripts/status-summary.sh" >/dev/null 2>&1 || true
exit "$result"
