#!/system/bin/sh

kst_engine_order() {
  kst_awk -v old="$(cat "$1/engine-version")" -v new="$(cat "$2/engine-version")" 'BEGIN {
    sub(/^v/, "", old); sub(/^v/, "", new)
    if (old !~ /^[0-9]+\.[0-9]+\.[0-9]+$/ || new !~ /^[0-9]+\.[0-9]+\.[0-9]+$/) exit 2
    split(old, a, "."); split(new, b, ".")
    for (i=1;i<=3;i++) { if (b[i]+0 < a[i]+0) exit 1; if (b[i]+0 > a[i]+0) exit 0 }
    exit 0
  }'
}

kst_activate() (
  candidate=$1
  wanted=$2
  old=$(kst_current) || exit 1
  new=$(kst_generation "$candidate") || exit 1
  [ "$new" != "$old" ] || exit 0
  if [ -n "$old" ]; then
    old_code=$(kst_prop "$old" versionCode)
    new_code=$(kst_prop "$new" versionCode)
    [ "$new_code" -gt "$old_code" ] || { kst_error version-not-increasing; exit 1; }
    kst_engine_order "$old" "$new" || { kst_error engine-downgrade-or-invalid-version; exit 1; }
    kst_runtime "$old" stop || { kst_error current-stop-failed; exit 1; }
    kst_pointer previous "$old" || exit 1
  fi
  kst_pointer current "$new" || exit 1
  if [ "$wanted" = 1 ] && ! kst_runtime "$new" start; then
    printf '%s\n' candidate-start-failed > "$TS_DIR/run/activation-failure"
    kst_runtime "$new" stop || { kst_error candidate-stop-failed; exit 1; }
    printf 'failed\n' > "$TS_DIR/run/lifecycle"
    printf '1\n' > "$TS_DIR/run/wanted"
    if [ -n "$old" ] && cmp -s "$old/engine-version" "$new/engine-version"; then
      if kst_pointer current "$old"; then
        kst_runtime "$old" start || printf '%s\n' rollback-start-failed > "$TS_DIR/run/activation-failure"
      fi
    fi
    kst_error candidate-start-failed
    exit 1
  fi
  rm -f "$TS_DIR/run/activation-failure"
)

kst_prepare_initial() {
  existing=$(kst_current) || return 1
  [ -n "$existing" ] || kst_activate "$BUNDLE_DIR" 0
}

kst_prepare_manager() {
  existing=$(kst_current) || return 1
  if [ -z "$existing" ]; then
    kst_activate "$MODDIR" 1
    return $?
  fi
  if [ ! -f "$MODDIR/bundle.sha256" ]; then
    kst_verify_bundle "$existing" || return 1
    kst_runtime "$existing" start
    return $?
  fi
  kst_verify_bundle "$MODDIR" || return 1
  manager_code=$(kst_prop "$MODDIR" versionCode)
  active_code=$(kst_prop "$existing" versionCode)
  if [ "$manager_code" -gt "$active_code" ]; then
    kst_activate "$MODDIR" 1
  elif [ "$manager_code" -eq "$active_code" ]; then
    cmp -s "$MODDIR/bundle.sha256" "$existing/bundle.sha256" || { kst_error equal-version-different-bundle; return 1; }
    kst_runtime "$existing" start
  else
    kst_runtime "$existing" start
  fi
}

kst_apply_staged() {
  [ -d "$KST_STAGED_DIR" ] || { kst_error no-staged-update; return 1; }
  kst_require_identity_choice || return 1
  wanted=0
  [ "$(cat "$TS_DIR/run/wanted" 2>/dev/null)" != 1 ] || wanted=1
  [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || wanted=0
  kst_activate "$KST_STAGED_DIR" "$wanted"
}
