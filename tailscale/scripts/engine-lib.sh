#!/system/bin/sh
# shellcheck disable=SC3043

engine_valid_version() {
  printf '%s\n' "$1" | grep -Eq '^[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}$'
}

engine_at_least() {
  local candidate="${1#v}" base="${2#v}"
  engine_valid_version "$candidate" && engine_valid_version "$base" || return 1
  awk -v candidate="$candidate" -v base="$base" 'BEGIN {
    split(candidate,a,"."); split(base,b,".")
    for(i=1;i<=3;i++) { if(a[i]+0>b[i]+0) exit 0; if(a[i]+0<b[i]+0) exit 1 }
    exit 0
  }'
}

# A compatibility beta must not silently replace its patched engine with an
# official override. Missing policy preserves stable-release behavior.
engine_policy() {
  ENGINE_POLICY=official
  if [ -e "$BUNDLE_DIR/tailscale/engine-policy" ] || [ -L "$BUNDLE_DIR/tailscale/engine-policy" ]; then
    [ ! -L "$BUNDLE_DIR/tailscale/engine-policy" ] || return 1
    ENGINE_POLICY=$(cat "$BUNDLE_DIR/tailscale/engine-policy") || return 1
  fi
  case "$ENGINE_POLICY" in official|bundled-compatibility) return 0 ;; esac
  echo 'Invalid engine policy' >&2
  return 1
}

engine_require_official_updates() {
  engine_policy || return 1
  [ "$ENGINE_POLICY" = official ] && return 0
  echo 'This compatibility beta pins its patched engine; official engine updates are disabled.' >&2
  return 1
}

engine_select() {
  local selected root version base
  engine_policy || return 1
  ENGINE_DIR=$BUNDLE_DIR
  [ -e "$TS_DIR/engine-current" ] || [ -L "$TS_DIR/engine-current" ] || return 0
  [ -L "$TS_DIR/engine-current" ] && [ ! -L "$TS_DIR/engines" ] || return 1
  selected=$(readlink -f "$TS_DIR/engine-current") || return 1
  root=$(cd "$TS_DIR/engines" && pwd -P) || return 1
  [ "${selected%/*}" = "$root" ] && [ -d "$selected/bin" ] || return 1
  version=$(cat "$selected/engine-version") || return 1
  base=$(cat "$BUNDLE_DIR/engine-version") || return 1
  engine_valid_version "${version#v}" || return 1
  if [ "$ENGINE_POLICY" = bundled-compatibility ]; then
    engine_at_least "$base" "$version" || {
      echo 'Installed engine is newer than the compatibility bundle; downgrade rejected.' >&2
      return 1
    }
    return 0
  fi
  if engine_at_least "$version" "$base"; then ENGINE_DIR=$selected; fi
}

engine_verify() (
  target=$1
  [ ! -L "$target" ] && [ -d "$target" ] || exit 1
  [ -z "$(find "$target" -type l -print)" ] || exit 1
  [ "$(wc -l < "$target/engine.sha256")" -eq 3 ] || exit 1
  awk 'NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ {exit 1}
    $2!="bin/tailscale" && $2!="bin/tailscaled" && $2!="engine-version" {exit 1}
    seen[$2]++ {exit 1}' "$target/engine.sha256" || exit 1
  cd "$target" || exit 1
  sha256sum -c engine.sha256 >/dev/null 2>&1
)
