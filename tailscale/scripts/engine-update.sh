#!/system/bin/sh
# Sourced by the controller under its exclusive lock.
# shellcheck disable=SC3043

engine_fetch() {
  command -v curl >/dev/null 2>&1 || { echo 'Engine updates require curl with HTTPS certificate verification' >&2; return 1; }
  curl --fail --silent --show-error --proto '=https' --tlsv1.2 \
    --connect-timeout 10 --max-time "$3" --max-filesize "$4" \
    "https://pkgs.tailscale.com/stable/$1" --output "$2"
}

engine_status() {
  local current latest staged
  engine_select || return 1
  current=$(cat "$ENGINE_DIR/engine-version" 2>/dev/null); current=${current#v}
  latest=$(cat "$TS_DIR/engine-offer" 2>/dev/null)
  staged=$(cat "$TS_DIR/engine-ready/engine-version" 2>/dev/null)
  printf '{"current":"%s","latest":"%s","staged":"%s"}\n' \
    "$(json_escape "$current")" "$(json_escape "$latest")" "$(json_escape "$staged")"
}

engine_check() (
  local temporary version
  temporary=$(mktemp "$RUN_DIR/engine-meta.XXXXXX") || exit 1
  trap 'rm -f "$temporary"' EXIT
  engine_fetch '?mode=json' "$temporary" 20 524288 || exit 1
  version=$(json_read stable-version < "$temporary") || exit 1
  engine_valid_version "$version" || exit 1
  printf '%s\n' "$version" > "$TS_DIR/engine-offer.new" || exit 1
  mv -f "$TS_DIR/engine-offer.new" "$TS_DIR/engine-offer" || exit 1
  engine_status
)

engine_prepare() (
  local version arch work archive expected actual member listing binary reported target
  version=$(cat "$TS_DIR/engine-offer") || exit 1
  engine_valid_version "$version" || exit 1
  case "$(uname -m)" in aarch64|arm64) arch=arm64 ;; armv7*|armv8l|arm) arch=arm ;; *) echo 'Unsupported engine architecture' >&2; exit 1 ;; esac
  [ ! -L "$TS_DIR/engines" ] || exit 1
  mkdir -p "$TS_DIR/engines" || exit 1
  work=$(mktemp -d "$TS_DIR/engines/.download.XXXXXX") || exit 1
  trap 'rm -rf "$work"' EXIT
  archive="tailscale_${version}_${arch}.tgz"
  engine_fetch "$archive.sha256" "$work/checksum" 15 256 || exit 1
  expected=$(tr -d '\r\n' < "$work/checksum")
  [ "${#expected}" -eq 64 ] || exit 1
  case "$expected" in *[!0-9a-f]*) exit 1 ;; esac
  engine_fetch "$archive" "$work/archive" 60 104857600 || exit 1
  actual=$(sha256sum "$work/archive" | cut -d ' ' -f 1)
  [ "$actual" = "$expected" ] || { echo 'Official archive checksum mismatch' >&2; exit 1; }
  mkdir "$work/bin" || exit 1
  for binary in tailscale tailscaled; do
    member="tailscale_${version}_${arch}/$binary"
    listing=$(tar -tvzf "$work/archive" "$member") || exit 1
    [ "$(printf '%s\n' "$listing" | wc -l)" -eq 1 ] || exit 1
    case "$listing" in -*) ;; *) echo 'Archive member is not a regular file' >&2; exit 1 ;; esac
    (ulimit -f 131072; tar -xOzf "$work/archive" "$member" > "$work/bin/$binary") || exit 1
    chmod 0700 "$work/bin/$binary" || exit 1
    if [ "$binary" = tailscale ]; then
      reported=$(bounded 5 "$work/bin/$binary" version | head -n 1)
    else
      reported=$(bounded 5 "$work/bin/$binary" --version | head -n 1)
    fi
    [ "$reported" = "$version" ] || { echo 'Downloaded engine version mismatch' >&2; exit 1; }
  done
  printf '%s\n' "$version" > "$work/engine-version"
  (cd "$work" && sha256sum bin/tailscale bin/tailscaled engine-version > engine.sha256) || exit 1
  engine_verify "$work" || exit 1
  rm -f "$work/archive" "$work/checksum"
  target="$TS_DIR/engines/$version-$arch-$expected"
  if [ -e "$target" ]; then engine_verify "$target" || exit 1
  else mv "$work" "$target" || exit 1; fi
  kst_pointer engine-ready "$target" || exit 1
  engine_status
)

engine_finish_transaction() {
  local completed="$TS_DIR/.engine-completed.$$"
  [ ! -e "$completed" ] || return 1
  mv "$TS_DIR/engine-transaction" "$completed" || return 1
  # A partial cleanup of this inert directory is never interpreted as rollback.
  rm -rf "$completed"
}

engine_recover() {
  local journal="$TS_DIR/engine-transaction" old wanted
  [ -d "$journal" ] || return 0
  old=$(cat "$journal/previous") || return 1
  [ -n "$old" ] || return 1
  wanted=$(cat "$journal/wanted") || return 1
  case "$wanted" in 0|1) ;; *) return 1 ;; esac
  if [ -f "$journal/snapshot-ready" ] && [ -f "$journal/state-existed" ]; then
    [ -f "$journal/tailscaled.state" ] || return 1
  fi
  # Retain the journal if an owned process cannot be stopped safely.
  kst_runtime "$BUNDLE_DIR" stop >/dev/null || return 1
  if [ "$old" = bundled ]; then rm -f "$TS_DIR/engine-current"
  else kst_pointer engine-current "$old" || return 1; fi
  if [ -f "$journal/snapshot-ready" ]; then
    if [ -f "$journal/state-existed" ]; then
      cp -p "$journal/tailscaled.state" "$STATE_FILE.restore" && mv -f "$STATE_FILE.restore" "$STATE_FILE" || return 1
    else rm -f "$STATE_FILE"; fi
  fi
  if [ "$wanted" = 1 ] && [ ! -f "$journal/no-restart" ] && ! module_disabled; then
    kst_runtime "$BUNDLE_DIR" start >/dev/null || return 1
  fi
  engine_finish_transaction
}

engine_apply() (
  local target root version old wanted=0 backend journal="$TS_DIR/engine-transaction" before
  engine_recover || exit 1
  [ -L "$TS_DIR/engine-ready" ] && [ ! -L "$TS_DIR/engines" ] || exit 1
  target=$(readlink -f "$TS_DIR/engine-ready") || exit 1
  root=$(cd "$TS_DIR/engines" && pwd -P) || exit 1
  [ "${target%/*}" = "$root" ] || exit 1
  engine_verify "$target" || exit 1
  engine_select || exit 1
  version=$(cat "$target/engine-version")
  engine_at_least "$version" "$(cat "$ENGINE_DIR/engine-version")" || { echo 'Engine downgrade rejected' >&2; exit 1; }
  backend=$(cli_json backend status --json 2>/dev/null) || backend=
  [ "$(cat "$RUN_DIR/wanted" 2>/dev/null)" != 1 ] || wanted=1
  module_disabled && wanted=0
  before=$(mktemp -d "$TS_DIR/.engine-transaction.XXXXXX") || exit 1
  trap 'rm -rf "$before"' EXIT
  old=$(readlink -f "$TS_DIR/engine-current" 2>/dev/null)
  [ -L "$TS_DIR/engine-current" ] || old=bundled
  printf '%s\n' "$old" > "$before/previous" || exit 1
  printf '%s\n' "$wanted" > "$before/wanted" || exit 1
  mv "$before" "$journal" || exit 1
  trap 'engine_recover' EXIT
  kst_runtime "$BUNDLE_DIR" stop >/dev/null || exit 1
  if [ -f "$STATE_FILE" ]; then
    cp -p "$STATE_FILE" "$journal/tailscaled.state" || exit 1
    touch "$journal/state-existed" || exit 1
  fi
  touch "$journal/snapshot-ready" || exit 1
  kst_pointer engine-current "$target" || exit 1
  if [ "$wanted" = 1 ]; then
    kst_runtime "$BUNDLE_DIR" start >/dev/null || exit 1
    if [ "$backend" = Running ]; then
      local deadline state
      deadline=$(($(date +%s) + 20))
      while :; do
        state=$(bounded 3 "$target/bin/tailscale" --socket="$SOCKET_FILE" status --json 2>/dev/null | json_read backend)
        [ "$state" != Running ] || break
        [ "$(date +%s)" -lt "$deadline" ] || { echo 'New engine did not regain the logged-in state; rolling back' >&2; exit 1; }
        sleep 1
      done
    fi
  fi
  engine_finish_transaction || exit 1
  trap - EXIT
  rm -f "$TS_DIR/engine-ready"
  engine_status
)
