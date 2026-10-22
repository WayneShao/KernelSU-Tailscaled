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

engine_select() {
  local selected root version base
  ENGINE_DIR=$BUNDLE_DIR
  [ -e "$TS_DIR/engine-current" ] || [ -L "$TS_DIR/engine-current" ] || return 0
  [ -L "$TS_DIR/engine-current" ] && [ ! -L "$TS_DIR/engines" ] || return 1
  selected=$(readlink -f "$TS_DIR/engine-current") || return 1
  root=$(cd "$TS_DIR/engines" && pwd -P) || return 1
  [ "${selected%/*}" = "$root" ] && [ -d "$selected/bin" ] || return 1
  version=$(cat "$selected/engine-version") || return 1
  base=$(cat "$BUNDLE_DIR/engine-version") || return 1
  engine_valid_version "${version#v}" || return 1
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
