#!/system/bin/sh
# Android mksh, BusyBox ash, and the test shell support function-local variables.
# shellcheck disable=SC3043

SCRIPT_DIR=$(CDPATH='' cd -- "${SCRIPT_DIR:-${0%/*}}" 2>/dev/null && pwd -P)
BUNDLE_DIR=${BUNDLE_DIR:-${SCRIPT_DIR%/tailscale/scripts}}
MODDIR=${MODDIR:-/data/adb/modules/kernelsu-tailscaled}
TS_DIR=${TS_DIR:-/data/adb/kernelsu-tailscaled}
BIN_DIR="$BUNDLE_DIR/bin"
CONFIG_DIR="$TS_DIR/config"
LOG_DIR="$TS_DIR/logs"
RUN_DIR="$TS_DIR/run"
STATE_FILE="$TS_DIR/tailscaled.state"
SOCKET_FILE="$RUN_DIR/tailscaled.sock"
TAILSCALE_BIN="$BIN_DIR/tailscale"
TAILSCALED_BIN="$BIN_DIR/tailscaled"
TUNNEL_BIN="$BIN_DIR/hev-socks5-tunnel"
SCRIPT_DIR="$BUNDLE_DIR/tailscale/scripts"
SUPERVISOR_SCRIPT="$SCRIPT_DIR/tailscale-supervisor"
DAEMON_SCRIPT="$SCRIPT_DIR/tailscale-daemon"
WEB_SCRIPT="$SCRIPT_DIR/tailscale-web"
TUNNEL_SCRIPT="$SCRIPT_DIR/tailscale-tunnel"
SUPERVISOR_PID="$RUN_DIR/supervisor.pid"
DAEMON_PID="$RUN_DIR/tailscaled.pid"
WEB_PID="$RUN_DIR/web.pid"
TUNNEL_PID="$RUN_DIR/tunnel.pid"
KST_SHELL=${KST_SHELL:-/system/bin/sh}
KST_BUSYBOX=${KST_BUSYBOX:-/data/adb/ksu/bin/busybox}
KST_LOCK_TIMEOUT=${KST_LOCK_TIMEOUT:-15}
KST_CLI_TIMEOUT=${KST_CLI_TIMEOUT:-3}
KST_START_TIMEOUT=${KST_START_TIMEOUT:-15}
KST_STOP_TIMEOUT=${KST_STOP_TIMEOUT:-3}
KST_STAGED_DIR=${KST_STAGED_DIR:-/data/adb/modules_update/kernelsu-tailscaled}
export BUNDLE_DIR MODDIR TS_DIR KST_SHELL KST_BUSYBOX
umask 077

MODE=native
TUN_NAME=tailscale0
TAILSCALE_PORT=41641
WEB_LISTEN=127.0.0.1:8088
SOCKS_LISTEN=127.0.0.1:1055
CONTROL_PROXY=
DEVICE_HOSTNAME=
SUPERVISOR_INTERVAL=5
RESTART_BACKOFF_MAX=60

ensure_dirs() {
  mkdir -p "$TS_DIR" "$RUN_DIR" "$LOG_DIR" "$CONFIG_DIR" || return 1
  chmod 0700 "$TS_DIR" "$RUN_DIR" "$LOG_DIR" "$CONFIG_DIR"
}

flock_command() {
  # Android mksh closes exec-created descriptors unless each external call keeps them.
  if [ -x "$KST_BUSYBOX" ]; then
    case "$2" in 8) "$KST_BUSYBOX" flock "$@" 8>&8 ;; 9) "$KST_BUSYBOX" flock "$@" 9>&9 ;; *) return 2 ;; esac
  else
    case "$2" in 8) flock "$@" 8>&8 ;; 9) flock "$@" 9>&9 ;; *) return 2 ;; esac
  fi
}

awk_command() {
  if [ -x "$KST_BUSYBOX" ]; then "$KST_BUSYBOX" awk "$@"; else command awk "$@"; fi
}

with_control_lock() (
  exec 8>&-
  ensure_dirs || exit 1
  local expected actual deadline
  expected=$(stat -Lc '%d:%i' "$RUN_DIR/control.lock" 2>/dev/null)
  actual=$(stat -Lc '%d:%i' /proc/self/fd/9 2>/dev/null 9>&9)
  if [ "${KST_LOCK_HELD:-}" = 1 ] && [ -n "$expected" ] && [ "$actual" = "$expected" ]; then
    "$@" 9>&9
    exit $?
  fi
  unset KST_LOCK_HELD
  exec 9>"$RUN_DIR/control.lock" || exit 1
  deadline=$(($(date +%s) + KST_LOCK_TIMEOUT))
  until flock_command -n 9; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo 'Runtime control lock timed out' >&2
      exit 75
    fi
    sleep 0.1
  done
  KST_LOCK_HELD=1
  export KST_LOCK_HELD
  "$@" 9>&9
)

bounded() (
  local seconds="$1"
  shift
  exec 9>&- 8>&-
  unset KST_LOCK_HELD
  if [ -x "$KST_BUSYBOX" ]; then exec "$KST_BUSYBOX" timeout -s KILL "$seconds" "$@"; fi
  exec timeout -s KILL "$seconds" "$@"
)

valid_number() {
  case "$1" in '' | *[!0-9]* | 0[0-9]*) return 1 ;; esac
  [ "${#1}" -le 6 ] && [ "$1" -ge "$2" ] && [ "$1" -le "$3" ]
}

valid_loopback() {
  case "$1" in 127.0.0.1:*) valid_number "${1##*:}" 1 65535 ;; *) return 1 ;; esac
}

load_config() {
  local config="$CONFIG_DIR/module.conf" line key value
  CONFIG_ERROR=
  [ -f "$config" ] || config="$BUNDLE_DIR/tailscale/config/module.conf"
  [ -f "$config" ] || { CONFIG_ERROR='Configuration file is missing'; return 1; }
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in '' | \#*) continue ;; *=*) ;; *) CONFIG_ERROR='Malformed configuration line'; return 1 ;; esac
    key=${line%%=*}
    value=${line#*=}
    case "$key" in
      MODE) case "$value" in native | userspace) MODE=$value ;; *) CONFIG_ERROR='Invalid MODE'; return 1 ;; esac ;;
      TUN_NAME) case "$value" in '' | *[!a-zA-Z0-9_.-]*) CONFIG_ERROR='Invalid TUN_NAME'; return 1 ;; esac
        [ "${#value}" -le 15 ] || { CONFIG_ERROR='TUN_NAME exceeds interface limit'; return 1; }; TUN_NAME=$value ;;
      TAILSCALE_PORT) valid_number "$value" 1 65535 || { CONFIG_ERROR='Invalid TAILSCALE_PORT'; return 1; }; TAILSCALE_PORT=$value ;;
      WEB_LISTEN) valid_loopback "$value" || { CONFIG_ERROR='Invalid loopback WEB_LISTEN'; return 1; }; WEB_LISTEN=$value ;;
      SOCKS_LISTEN) valid_loopback "$value" || { CONFIG_ERROR='Invalid loopback SOCKS_LISTEN'; return 1; }; SOCKS_LISTEN=$value ;;
      CONTROL_PROXY)
        case "$value" in '') ;; http://127.0.0.1:* | socks5://127.0.0.1:*)
          valid_loopback "${value#*://}" || { CONFIG_ERROR='Invalid loopback CONTROL_PROXY'; return 1; } ;;
          *) CONFIG_ERROR='Invalid loopback CONTROL_PROXY'; return 1 ;; esac
        CONTROL_PROXY=$value ;;
      DEVICE_HOSTNAME) case "$value" in *[!a-zA-Z0-9_.\ -]*) CONFIG_ERROR='Invalid DEVICE_HOSTNAME'; return 1 ;; esac
        [ "${#value}" -le 63 ] || { CONFIG_ERROR='DEVICE_HOSTNAME exceeds DNS label limit'; return 1; }; DEVICE_HOSTNAME=$value ;;
      SUPERVISOR_INTERVAL) valid_number "$value" 1 300 || { CONFIG_ERROR='Invalid SUPERVISOR_INTERVAL'; return 1; }; SUPERVISOR_INTERVAL=$value ;;
      RESTART_BACKOFF_MAX) valid_number "$value" 1 300 || { CONFIG_ERROR='Invalid RESTART_BACKOFF_MAX'; return 1; }; RESTART_BACKOFF_MAX=$value ;;
      *) CONFIG_ERROR='Unknown configuration key'; return 1 ;;
    esac
  done < "$config"
  return 0
}

redact() { awk_command -f "$SCRIPT_DIR/log-filter.awk"; }

log() {
  local level="$1"
  shift
  mkdir -p "$LOG_DIR"
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$level" "$*" |
    awk_command -v destination="$LOG_DIR/supervisor.log" -f "$SCRIPT_DIR/log-filter.awk"
}

read_pid() {
  local pid
  [ -r "$1" ] || return 1
  pid=$(sed -n '1p' "$1")
  case "$pid" in '' | *[!0-9]*) return 1 ;; esac
  [ "$pid" -gt 1 ] || return 1
  printf '%s\n' "$pid"
}

process_starttime() {
  # comm may contain spaces or parentheses; starttime is field 20 after it.
  # shellcheck disable=SC2016
  sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | awk_command '$1 != "Z" {print $20}'
}

pid_matches() {
  local pid="$1" expected="$2" required_arg="${3:-}" start="${4:-}" executable="${5:-}"
  case "$pid" in '' | *[!0-9]*) return 1 ;; esac
  [ -r "/proc/$pid/cmdline" ] || return 1
  [ -n "$(process_starttime "$pid")" ] || return 1
  if [ -n "$start" ]; then [ "$(process_starttime "$pid")" = "$start" ] || return 1; fi
  if [ -n "$executable" ]; then [ "$(readlink "/proc/$pid/exe")" = "$executable" ] || return 1; fi
  tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fqx -- "$expected" || {
    [ "$(readlink "/proc/$pid/exe" 2>/dev/null)" = "$(readlink -f "$expected")" ] || return 1
  }
  if [ -n "$required_arg" ]; then tr '\000' '\n' < "/proc/$pid/cmdline" | grep -Fqx -- "$required_arg" || return 1; fi
}

write_pid() {
  local pid_file="$1" pid="$2" expected="$3" required_arg="${4:-}" start executable count=0
  while ! pid_matches "$pid" "$expected" "$required_arg"; do
    [ "$count" -lt 20 ] || return 1
    sleep 0.05
    count=$((count + 1))
  done
  start=$(process_starttime "$pid")
  executable=$(readlink "/proc/$pid/exe")
  [ -n "$start" ] && [ -n "$executable" ] || return 1
  printf '%s\n' "$pid" "$start" "$executable" "$expected" "$required_arg" > "$pid_file.new"
  mv -f "$pid_file.new" "$pid_file"
}

owned_alive() {
  local file="$1" expected="$2" required="${3:-}" pid start executable identity recorded_arg
  pid=$(read_pid "$file") || return 1
  start=$(sed -n '2p' "$file")
  executable=$(sed -n '3p' "$file")
  identity=$(sed -n '4p' "$file")
  recorded_arg=$(sed -n '5p' "$file")
  case "$start" in '' | *[!0-9]*) return 1 ;; esac
  [ -n "$executable" ] && [ "$identity" = "$expected" ] && [ "$recorded_arg" = "$required" ] || return 1
  pid_matches "$pid" "$expected" "$required" "$start" "$executable"
}

record_process_gone() {
  local file="$1" pid recorded snapshot state current
  [ -e "$file" ] || return 0
  pid=$(read_pid "$file") || return 1
  [ -d "/proc/$pid" ] || return 0
  recorded=$(sed -n '2p' "$file")
  # A failed identity check is not proof of exit. Retain ambiguous live records.
  # shellcheck disable=SC2016
  snapshot=$(sed 's/^.*) //' "/proc/$pid/stat" 2>/dev/null | awk_command '{print $1, $20}')
  state=${snapshot%% *}
  current=${snapshot#* }
  case "$state" in Z | X) return 0 ;; esac
  case "$recorded" in '' | *[!0-9]*) return 1 ;; esac
  case "$current" in '' | *[!0-9]*) return 1 ;; esac
  [ "$current" != "$recorded" ]
}

stop_owned() {
  local file="$1" expected="$2" required="${3:-}" pid deadline count=0
  if owned_alive "$file" "$expected" "$required"; then
    pid=$(read_pid "$file")
    kill -TERM "$pid" 2>/dev/null || true
    deadline=$(($(date +%s) + KST_STOP_TIMEOUT))
    while owned_alive "$file" "$expected" "$required" && [ "$(date +%s)" -lt "$deadline" ]; do sleep 0.1; done
    if owned_alive "$file" "$expected" "$required"; then
      kill -KILL "$pid" 2>/dev/null || true
      while owned_alive "$file" "$expected" "$required" && [ "$count" -lt 10 ]; do
        sleep 0.05
        count=$((count + 1))
      done
      if owned_alive "$file" "$expected" "$required"; then
        log ERROR 'Owned process survived bounded stop; ownership record retained'
        return 1
      fi
    fi
  fi
  if ! record_process_gone "$file"; then
    log ERROR "Process identity unresolved; retained ${file##*/} and blocked replacement"
    return 1
  fi
  rm -f "$file"
}

launch_logged() {
  local name="$1" record="$2" identity="$3" required="$4" fifo logger child
  shift 4
  fifo="$RUN_DIR/$name.fifo"
  stop_owned "$record" "$identity" "$required" || return 1
  stop_owned "$RUN_DIR/$name-log.pid" "$SCRIPT_DIR/log-filter.awk" || return 1
  rm -f "$fifo"
  mkfifo -m 0600 "$fifo" || return 1
  (exec 9>&- 8>&-; unset KST_LOCK_HELD
    if [ -x "$KST_BUSYBOX" ]; then
      exec "$KST_BUSYBOX" awk -v destination="$LOG_DIR/$name.log" -f "$SCRIPT_DIR/log-filter.awk" < "$fifo"
    fi
    exec awk -v destination="$LOG_DIR/$name.log" -f "$SCRIPT_DIR/log-filter.awk" < "$fifo"
  ) </dev/null >/dev/null 2>&1 &
  logger=$!
  (exec 9>&- 8>&-; unset KST_LOCK_HELD; trap '' HUP; exec "$@" > "$fifo" 2>&1) </dev/null >/dev/null 2>&1 &
  child=$!
  write_pid "$RUN_DIR/$name-log.pid" "$logger" "$SCRIPT_DIR/log-filter.awk" || true
  write_pid "$record" "$child" "$identity" "$required"
}

stop_logger() {
  stop_owned "$RUN_DIR/$1-log.pid" "$SCRIPT_DIR/log-filter.awk" || return 1
  rm -f "$RUN_DIR/$1.fifo"
}

json_read() { awk_command -v action="$1" -f "$SCRIPT_DIR/json.awk"; }

json_escape() {
  # shellcheck disable=SC2016
  printf '%s' "$1" | awk_command 'BEGIN {ORS=""} {if (NR>1) printf "\\n"; gsub(/\\/,"\\\\"); gsub(/"/,"\\\""); gsub(/\t/,"\\t"); gsub(/\r/,"\\r"); printf "%s",$0}'
}

cli_json() (
  local action="$1" file
  shift
  ensure_dirs || exit 1
  file=$(mktemp "$RUN_DIR/query.XXXXXX") || exit 1
  trap 'rm -f "$file"' EXIT HUP INT TERM
  # Raw replies have a disk cap and timeout. Raw prefs never leave this scope.
  (ulimit -f 1024; bounded "$KST_CLI_TIMEOUT" "$TAILSCALE_BIN" --socket="$SOCKET_FILE" "$@" > "$file" 2>/dev/null) || exit 1
  [ "$(wc -c < "$file")" -le 524288 ] || exit 1
  json_read "$action" < "$file"
)

socket_ready() { [ -S "$SOCKET_FILE" ] && cli_json backend status --json >/dev/null 2>&1; }

tcp_ready() {
  local host="${1%:*}" port="${1##*:}"
  if [ -x "$KST_BUSYBOX" ]; then
    bounded 1 "$KST_BUSYBOX" nc -z -w 1 "$host" "$port" </dev/null >/dev/null 2>&1
  else
    bounded 1 nc -z -w 1 "$host" "$port" </dev/null >/dev/null 2>&1
  fi
}

module_disabled() { [ -f "$MODDIR/disable" ] || [ -f "$MODDIR/remove" ]; }
daemon_running() { owned_alive "$DAEMON_PID" "$TAILSCALED_BIN" "--socket=$SOCKET_FILE"; }
supervisor_health() { owned_alive "$SUPERVISOR_PID" "$SUPERVISOR_SCRIPT"; }
web_running() { owned_alive "$WEB_PID" "$TAILSCALE_BIN" "--socket=$SOCKET_FILE"; }

set_lifecycle() {
  printf '%s\n' "$1" > "$RUN_DIR/lifecycle.new"
  mv -f "$RUN_DIR/lifecycle.new" "$RUN_DIR/lifecycle"
}

diagnostic() {
  [ -z "${DIAGNOSTICS:-}" ] || DIAGNOSTICS="$DIAGNOSTICS,"
  DIAGNOSTICS="$DIAGNOSTICS{\"code\":\"$1\",\"severity\":\"$2\",\"message\":\"$(json_escape "$3")\"}"
}

native_health() {
  local status="$1" backend addresses own_ips address peers peer route deadline
  DATA_PLANE=unknown
  backend=$(printf '%s' "$status" | json_read backend) || return 1
  case "$backend" in
    NeedsLogin | NeedsMachineAuth | NoState | Starting | Stopped)
      diagnostic login-required info "Backend state: $backend"; return 1 ;;
    Running) ;;
    *) diagnostic backend-unknown warning 'Backend state is not recognized'; return 1 ;;
  esac
  DATA_PLANE=stopped
  if ! bounded 1 ip link show dev "$TUN_NAME" >/dev/null 2>&1; then
    diagnostic native-interface-missing error 'Native Tailscale interface is missing'; return 1
  fi
  addresses=$(bounded 1 ip -o address show dev "$TUN_NAME" 2>/dev/null) || {
    DATA_PLANE=unknown; diagnostic native-address-query warning 'Native address query failed'; return 1;
  }
  own_ips=$(printf '%s' "$status" | json_read ips)
  [ -n "$own_ips" ] || { diagnostic native-address-missing error 'Backend has no assigned Tailscale address'; return 1; }
  for address in $own_ips; do
    case "$address" in *[!0-9a-fA-F:.]*) return 1 ;; esac
    # shellcheck disable=SC2016
    printf '%s\n' "$addresses" | awk_command -v expected="$address" '{for(i=1;i<=NF;i++) if(index($i,expected "/")==1) found=1} END {exit !found}' || {
      diagnostic native-address-missing error 'An assigned Tailscale address is missing from the native interface'; return 1;
    }
  done
  peers=$(printf '%s' "$status" | json_read peer-ips)
  deadline=$(($(date +%s) + KST_CLI_TIMEOUT))
  for peer in $peers; do
    case "$peer" in *[!0-9a-fA-F:.]* | '') continue ;; esac
    if [ "$(date +%s)" -ge "$deadline" ]; then
      DATA_PLANE=unknown; diagnostic native-route-timeout warning 'Peer route inspection exceeded its time budget'; return 1
    fi
    route=$(bounded 1 ip route get "$peer" 2>/dev/null) || route=
    # shellcheck disable=SC2016
    printf '%s\n' "$route" | awk_command -v dev="$TUN_NAME" '{for(i=1;i<NF;i++) if($i=="dev" && $(i+1)==dev) found=1} END {exit !found}' || {
      diagnostic native-route-missing error 'A peer route does not resolve to the native Tailscale interface'; return 1;
    }
  done
  DATA_PLANE=running
}

data_plane_health() {
  if [ "$MODE" = native ]; then native_health "$1"; return $?; fi
  DATA_PLANE=stopped
  if owned_alive "$TUNNEL_PID" "$TUNNEL_BIN" && bounded 1 ip link show dev "$TUN_NAME" >/dev/null 2>&1 && tcp_ready "$SOCKS_LISTEN"; then
    DATA_PLANE=running; return 0
  fi
  diagnostic userspace-not-ready warning 'Explicit userspace helper is not ready'
  return 1
}
