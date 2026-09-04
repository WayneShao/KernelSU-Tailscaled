#!/system/bin/sh

SCRIPT_DIR=${0%/*}
MODDIR=${MODDIR:-${SCRIPT_DIR%/tailscale/scripts}}
TS_DIR=${TS_DIR:-/data/adb/tailscale}
BIN_DIR="$TS_DIR/bin"
CONFIG_DIR="$TS_DIR/config"
LOG_DIR="$TS_DIR/logs"
RUN_DIR="$TS_DIR/run"
STATE_FILE="$TS_DIR/tailscaled.state"
SOCKET_FILE="$RUN_DIR/tailscaled.sock"
TAILSCALE_BIN="$BIN_DIR/tailscale"
TAILSCALED_BIN="$BIN_DIR/tailscaled"
TUNNEL_BIN="$BIN_DIR/hev-socks5-tunnel"
SUPERVISOR_SCRIPT="$MODDIR/tailscale/scripts/tailscale-supervisor"
DAEMON_SCRIPT="$MODDIR/tailscale/scripts/tailscale-daemon"
WEB_SCRIPT="$MODDIR/tailscale/scripts/tailscale-web"
TUNNEL_SCRIPT="$MODDIR/tailscale/scripts/tailscale-tunnel"
SUPERVISOR_PID="$RUN_DIR/supervisor.pid"
DAEMON_PID="$RUN_DIR/tailscaled.pid"
WEB_PID="$RUN_DIR/web.pid"
TUNNEL_PID="$RUN_DIR/tunnel.pid"

MODE=native
TUN_NAME=tailscale0
TAILSCALE_PORT=41641
WEB_LISTEN=127.0.0.1:8088
SOCKS_LISTEN=127.0.0.1:1055
SUPERVISOR_INTERVAL=5
RESTART_BACKOFF_MAX=60

log() {
  level="$1"
  shift
  mkdir -p "$LOG_DIR"
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" >> "$LOG_DIR/supervisor.log"
}

load_config() {
  config="$CONFIG_DIR/module.conf"
  [ -f "$config" ] || config="$MODDIR/tailscale/config/module.conf"
  [ -f "$config" ] || return 1
  . "$config"
  case "$MODE" in
    native | userspace) ;;
    *) log ERROR "Invalid MODE: $MODE"; return 1 ;;
  esac
  case "$TUN_NAME" in
    '' | *[!a-zA-Z0-9_.-]*) log ERROR "Invalid TUN_NAME"; return 1 ;;
  esac
  case "$TAILSCALE_PORT:$SUPERVISOR_INTERVAL:$RESTART_BACKOFF_MAX" in
    *[!0-9:]*) log ERROR "Invalid numeric configuration"; return 1 ;;
  esac
  case "$WEB_LISTEN" in
    127.0.0.1:[0-9]*) ;;
    *) log ERROR "WEB_LISTEN must use IPv4 loopback"; return 1 ;;
  esac
  case "$SOCKS_LISTEN" in
    127.0.0.1:[0-9]*) ;;
    *) log ERROR "SOCKS_LISTEN must use IPv4 loopback"; return 1 ;;
  esac
}

read_pid() {
  pid_file="$1"
  [ -r "$pid_file" ] || return 1
  pid=$(sed -n '1p' "$pid_file" 2>/dev/null)
  case "$pid" in
    '' | *[!0-9]*) return 1 ;;
  esac
  printf '%s\n' "$pid"
}

pid_matches() {
  pid="$1"
  expected="$2"
  required_arg="${3:-}"
  case "$pid" in
    '' | *[!0-9]*) return 1 ;;
  esac
  [ -r "/proc/$pid/cmdline" ] || return 1
  cmdline=$(tr '\000' ' ' < "/proc/$pid/cmdline" 2>/dev/null) || return 1
  first=$(printf '%s' "$cmdline" | sed 's/ .*//')
  [ "$first" = "$expected" ] || [ "$(readlink "/proc/$pid/exe" 2>/dev/null)" = "$expected" ] || return 1
  if [ -n "$required_arg" ]; then
    case " $cmdline " in
      *" $required_arg "*) ;;
      *) return 1 ;;
    esac
  fi
}

write_pid() {
  pid_file="$1"
  pid="$2"
  printf '%s\n' "$pid" > "$pid_file.new"
  mv -f "$pid_file.new" "$pid_file"
}

stop_owned() {
  pid_file="$1"
  expected="$2"
  required_arg="${3:-}"
  pid=$(read_pid "$pid_file") || {
    rm -f "$pid_file"
    return 0
  }
  if ! pid_matches "$pid" "$expected" "$required_arg"; then
    log WARN "Removed stale PID file $pid_file"
    rm -f "$pid_file"
    return 0
  fi
  kill -TERM "$pid" 2>/dev/null || true
  count=0
  while pid_matches "$pid" "$expected" "$required_arg" && [ "$count" -lt 10 ]; do
    sleep 1
    count=$((count + 1))
  done
  if pid_matches "$pid" "$expected" "$required_arg"; then
    kill -KILL "$pid" 2>/dev/null || true
  fi
  rm -f "$pid_file"
}

socket_ready() {
  [ -S "$SOCKET_FILE" ] || return 1
  output=$("$TAILSCALE_BIN" --socket="$SOCKET_FILE" status --json 2>/dev/null || true)
  case "$output" in
    *'"BackendState"'*) return 0 ;;
    *) return 1 ;;
  esac
}

tcp_ready() {
  listen="$1"
  host=${listen%:*}
  port=${listen##*:}
  if [ -x /data/adb/ksu/bin/busybox ]; then
    /data/adb/ksu/bin/busybox nc -z -w 1 "$host" "$port" </dev/null >/dev/null 2>&1
  elif command -v busybox >/dev/null 2>&1; then
    busybox nc -z -w 1 "$host" "$port" </dev/null >/dev/null 2>&1
  else
    return 1
  fi
}

module_disabled() {
  [ -f "$MODDIR/disable" ]
}

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\t/\\t/g; s/\r/\\r/g; s/\n/\\n/g'
}

json_object_or_null() {
  value="$1"
  case "$value" in
    \{*\}) printf '%s' "$value" ;;
    *) printf 'null' ;;
  esac
}
