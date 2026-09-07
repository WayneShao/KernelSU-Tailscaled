#!/system/bin/sh

kst_error() { printf '%s\n' "KernelSU-Tailscaled: $1" >&2; }

kst_awk() {
  if [ -x "${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}" ]; then
    "${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}" awk "$@"
  else command awk "$@"; fi
}

kst_private_root() {
  case "$TS_DIR" in /*) ;; *) kst_error invalid-state-root; return 1 ;; esac
  [ ! -L "$TS_DIR" ] || { kst_error symlink-state-root; return 1; }
  umask 077
  mkdir -p "$TS_DIR" || return 1
  for entry in run releases config logs; do
    [ ! -L "$TS_DIR/$entry" ] || { kst_error symlink-state-directory; return 1; }
    mkdir -p "$TS_DIR/$entry" || return 1
    chmod 0700 "$TS_DIR/$entry" || return 1
  done
  chmod 0700 "$TS_DIR"
}

kst_prop() { sed -n "s/^$2=//p" "$1/module.prop"; }

kst_verify_bundle() (
  root=$1
  [ -d "$root" ] && [ ! -L "$root" ] && [ -f "$root/bundle.sha256" ] || exit 1
  [ -z "$(find "$root" -type l -print)" ] || { kst_error symlink-bundle; exit 1; }
  kst_awk '
    length($1) != 64 || $1 ~ /[^0-9a-f]/ || NF != 2 { exit 1 }
    $0 != $1 "  " $2 { exit 1 }
    $2 !~ /^[A-Za-z0-9_-][A-Za-z0-9_.\/-]*$/ || $2 ~ /(^|\/)\.\.?($|\/)|\/\/|\/$/ { exit 1 }
    $2 == "bundle.sha256" || $2 == "disable" || $2 == "remove" || $2 == "update" { exit 1 }
    seen[$2]++ { exit 1 }
    END { if (NR == 0) exit 1 }
  ' "$root/bundle.sha256" || { kst_error invalid-bundle-manifest; exit 1; }
  for required in module.prop engine-version control.sh bin/tailscale bin/tailscaled \
    scripts/bundle-lib.sh scripts/runtime-control.sh scripts/activate-runtime.sh scripts/migrate-legacy.sh \
    tailscale/scripts/common.sh tailscale/scripts/tailscale-service; do
    grep -q "  $required\$" "$root/bundle.sha256" || { kst_error incomplete-bundle; exit 1; }
  done
  [ "$(kst_prop "$root" id)" = kernelsu-tailscaled ] || { kst_error wrong-module-id; exit 1; }
  code=$(kst_prop "$root" versionCode)
  case "$code" in ''|*[!0-9]*|0*) kst_error invalid-version-code; exit 1 ;; esac
  [ "${#code}" -le 10 ] && [ "$code" -le 2147483647 ] || exit 1
  (cd "$root" && sha256sum -c bundle.sha256 >/dev/null 2>&1) || { kst_error bundle-hash-mismatch; exit 1; }
  find "$root" -type f | while IFS= read -r file; do
    relative=${file#"$root/"}
    case "$relative" in bundle.sha256|customize.sh|disable|remove|update) continue ;; esac
    grep -Fqx "$(sha256sum "$file" | cut -d ' ' -f 1)  $relative" "$root/bundle.sha256" || exit 1
  done || { kst_error undeclared-bundle-file; exit 1; }
)

kst_current() (
  [ -e "$TS_DIR/current" ] || [ -L "$TS_DIR/current" ] || exit 0
  [ -L "$TS_DIR/current" ] || { kst_error invalid-current-pointer; exit 1; }
  resolved=$(readlink -f "$TS_DIR/current") || exit 1
  releases=$(cd "$TS_DIR/releases" && pwd -P) || exit 1
  if [ "${resolved%/*}" != "$releases" ] || [ ! -d "$resolved" ]; then
    kst_error invalid-current-target
    exit 1
  fi
  printf '%s\n' "$resolved"
)

kst_generation() (
  source=$1
  kst_verify_bundle "$source" || exit 1
  digest=$(sha256sum "$source/bundle.sha256" | cut -d ' ' -f 1)
  target="$TS_DIR/releases/$(kst_prop "$source" versionCode)-$digest"
  if [ -e "$target" ]; then
    kst_verify_bundle "$target" || exit 1
    printf '%s\n' "$target"
    exit 0
  fi
  temporary=$(mktemp -d "$TS_DIR/releases/.prepare.XXXXXX") || exit 1
  trap 'rm -rf "$temporary"' EXIT HUP INT TERM
  while read -r digest relative; do
    case "$relative" in */*) mkdir -p "$temporary/${relative%/*}" || exit 1 ;; esac
    cp "$source/$relative" "$temporary/$relative" || exit 1
  done < "$source/bundle.sha256"
  cp "$source/bundle.sha256" "$temporary/bundle.sha256" || exit 1
  find "$temporary" -type d -exec chmod 0700 {} \; || exit 1
  find "$temporary" -type f -exec chmod 0600 {} \; || exit 1
  find "$temporary/bin" "$temporary/tailscale/scripts" "$temporary/scripts" -type f -exec chmod 0700 {} \; || exit 1
  kst_verify_bundle "$temporary" || exit 1
  mv "$temporary" "$target" || exit 1
  trap - EXIT HUP INT TERM
  printf '%s\n' "$target"
)

kst_pointer() {
  ln -s "$2" "$TS_DIR/.$1.$$" || return 1
  if [ -x "${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}" ]; then
    "${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}" mv -fT "$TS_DIR/.$1.$$" "$TS_DIR/$1"
  else
    mv -fT "$TS_DIR/.$1.$$" "$TS_DIR/$1"
  fi
}

kst_runtime() { BUNDLE_DIR="$1" sh "$1/tailscale/scripts/tailscale-service" "$2" 9>&9; }

kst_require_identity_choice() {
  [ ! -e "$TS_DIR/migration.pending" ] || { kst_error migration-incomplete; return 1; }
  if [ ! -e "$TS_DIR/tailscaled.state" ] && \
    { [ -e "$KST_LEGACY_DIR/tailscaled.state" ] || [ -e "$KST_LEGACY_DIR/tmp/tailscaled.state" ]; }; then
    kst_error migration-required
    return 1
  fi
}
