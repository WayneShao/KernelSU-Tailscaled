#!/system/bin/sh
# Sourced by common.sh; directory values are data, never shell configuration.
# Android mksh and BusyBox ash support local and inode comparison with -ef.
# shellcheck disable=SC3043,SC3013

read_taildrop_directory() {
  # awk owns $0; this is intentionally not a shell expansion.
  # shellcheck disable=SC2016
  LC_ALL=C awk_command '
    NR != 1 || /[[:cntrl:]]/ || /\302[\200-\237]/ { invalid=1 }
    { directory=$0 }
    END { if (NR != 1 || invalid) exit 1; print directory }
  '
}

valid_taildrop_directory() {
  local directory="$1" rest user volume
  printf '%s\n' "$directory" | read_taildrop_directory >/dev/null || return 1
  case "$directory/" in *//* | */./* | */../*) return 1 ;; esac
  case "$directory" in
    /sdcard/*) [ -n "${directory#/sdcard/}" ] ;;
    /storage/emulated/*/*)
      rest=${directory#/storage/emulated/}; user=${rest%%/*}
      case "$user" in '' | *[!0-9]*) return 1 ;; esac ;;
    /storage/self/primary/*) [ -n "${directory#/storage/self/primary/}" ] ;;
    /storage/*/*)
      rest=${directory#/storage/}; volume=${rest%%/*}
      case "$volume" in '' | emulated | self | *[!A-Za-z0-9_-]*) return 1 ;; esac ;;
    *) return 1 ;;
  esac
}

taildrop_storage_root() {
  local directory="$1" rest user volume
  case "$directory" in
    /sdcard/*) TAILDROP_ROOT=/sdcard; TAILDROP_RELATIVE=${directory#/sdcard/} ;;
    /storage/emulated/*/*)
      rest=${directory#/storage/emulated/}; user=${rest%%/*}
      TAILDROP_ROOT="/storage/emulated/$user"; TAILDROP_RELATIVE=${rest#*/} ;;
    /storage/self/primary/*)
      TAILDROP_ROOT=/storage/self/primary; TAILDROP_RELATIVE=${directory#/storage/self/primary/} ;;
    /storage/*/*)
      rest=${directory#/storage/}; volume=${rest%%/*}
      TAILDROP_ROOT="/storage/$volume"; TAILDROP_RELATIVE=${rest#*/} ;;
    *) return 1 ;;
  esac
}

taildrop_root_mounted() {
  local root="$1" mount rest user='' volume='' scope
  case "$root" in
    /storage/emulated/*)
      user=${root#/storage/emulated/}; mount=/storage/emulated ;;
    /storage/*)
      volume=${root#/storage/}; mount=$root ;;
    /mnt/runtime/*/emulated/*)
      rest=${root#/mnt/runtime/}; scope=${rest%%/*}; rest=${rest#*/}
      case "$scope" in default | read | write | full) ;; *) return 1 ;; esac
      user=${rest#emulated/}; mount="/mnt/runtime/$scope/emulated" ;;
    /mnt/runtime/*/*)
      rest=${root#/mnt/runtime/}; scope=${rest%%/*}; volume=${rest#*/}
      case "$scope" in default | read | write | full) ;; *) return 1 ;; esac
      mount=$root ;;
    /mnt/user/*/emulated/*)
      rest=${root#/mnt/user/}; scope=${rest%%/*}; user=${rest#*/emulated/}
      case "$scope" in '' | *[!0-9]*) return 1 ;; esac
      mount="/mnt/user/$scope/emulated" ;;
    /mnt/media_rw/*) volume=${root#/mnt/media_rw/}; mount=$root ;;
    *) return 1 ;;
  esac
  if [ -n "$user" ]; then
    case "$user" in *[!0-9]*) return 1 ;; esac
  elif [ -n "$volume" ]; then
    case "$volume" in emulated | self | *[!A-Za-z0-9_-]*) return 1 ;; esac
  else return 1
  fi
  # Only an actual shared-storage mount qualifies, never / or /storage itself.
  # These allowlisted mount roots cannot contain mountinfo escape characters.
  # awk owns $5; this is intentionally not a shell expansion.
  # shellcheck disable=SC2016
  awk_command -v root="$root" -v mount="$mount" '
    $5 == mount || $5 == root { found=1 }
    END { exit !found }
  ' /proc/self/mountinfo
}

taildrop_enter_directory() {
  local directory="$1" create="${2:-check}" canonical part rest probe
  TAILDROP_ERROR=
  valid_taildrop_directory "$directory" || {
    TAILDROP_ERROR='Choose a folder below /sdcard or an Android shared-storage volume; control characters, empty segments and traversal are not allowed'
    return 1
  }
  taildrop_storage_root "$directory" || return 1
  # Enter an existing storage root before checking its mount. Never mkdir a
  # missing mount root, including while credential-encrypted storage is locked.
  if ! CDPATH='' cd -- "$TAILDROP_ROOT" 2>/dev/null; then
    TAILDROP_ERROR='Shared storage is unavailable; unlock the device or mount the selected volume'
    return 1
  fi
  canonical=$(pwd -P) || return 1
  if ! taildrop_root_mounted "$canonical"; then
    TAILDROP_ERROR='The selected root is not mounted Android shared storage'
    return 1
  fi
  TAILDROP_CANONICAL_ROOT=$canonical
  rest=$TAILDROP_RELATIVE
  while [ -n "$rest" ]; do
    part=${rest%%/*}
    case "$rest" in */*) rest=${rest#*/} ;; *) rest= ;; esac
    if [ -L "$part" ]; then
      TAILDROP_ERROR='Destination folders must not contain symbolic links'
      return 1
    fi
    if [ ! -d "$part" ]; then
      if [ "$create" != create ] || ! mkdir -- "$part" 2>/dev/null; then
        TAILDROP_ERROR='The destination is not a writable folder; check storage access and free space'
        return 1
      fi
    fi
    if ! CDPATH='' cd -- "$part" 2>/dev/null; then
      TAILDROP_ERROR='The destination folder cannot be opened'
      return 1
    fi
    canonical=$(pwd -P) || return 1
    case "$canonical" in "$TAILDROP_CANONICAL_ROOT"/*) ;;
      *) TAILDROP_ERROR='The destination resolves outside the selected shared-storage root'; return 1 ;;
    esac
  done
  if [ ! -w . ]; then
    TAILDROP_ERROR='The destination folder is not writable'
    return 1
  fi
  if [ "$create" = create ]; then
    probe=$(mktemp './.taildrop-write.XXXXXX' 2>/dev/null) || {
      TAILDROP_ERROR='The destination folder is not writable; check free space and storage access'
      return 1
    }
    rm -f "$probe" || { TAILDROP_ERROR='Could not remove the destination write probe'; return 1; }
  fi
  TAILDROP_CANONICAL=$canonical
}

taildrop_running() {
  owned_alive "$TAILDROP_PID" "$TAILSCALE_BIN" --conflict=rename || return 1
  local pid
  pid=$(read_pid "$TAILDROP_PID") || return 1
  pid_matches "$pid" "$TAILSCALE_BIN" "--socket=$SOCKET_FILE"
}

taildrop_health() {
  [ -z "${TAILDROP_CONFIG_ERROR:-}" ] && taildrop_running || return 1
  local pid
  pid=$(read_pid "$TAILDROP_PID") || return 1
  # A pinned cwd cannot be redirected. An unmount, replacement or path change
  # breaks this identity check; full storage validation belongs to startup.
  [ "/proc/$pid/cwd" -ef "$TAILDROP_DIR" ] && [ -w "$TAILDROP_DIR" ]
}
