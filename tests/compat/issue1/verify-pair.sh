#!/usr/bin/env bash
# Run on Linux/WSL. GO must point to the upstream-required Go toolchain.
set -euo pipefail
[[ $# == 2 ]] || { echo "usage: GO=/path/to/go $0 UPSTREAM_TARBALL OUTPUT_PARENT"; exit 2; }
archive=$(realpath "$1"); output=$(realpath "$2")
fixtures=$(cd "$(dirname "$0")" && pwd)
[[ $(sha256sum "$archive" | cut -d ' ' -f 1) == 862f12b3177d5e961f2a86cf82fb1ff3551786afcaf95f2dc9a8318889f98732 ]] || { echo 'Unexpected source archive'; exit 2; }
work=$(mktemp -d "$output/issue1-pair.XXXXXX")
printf 'Evidence directory: %s\n' "$work"
# Extraction is only of the pinned upstream archive into a newly-created directory.
tar -xzf "$archive" -C "$work"
src="$work/tailscale-1.104.4"
cp "$fixtures/run-isolated.sh" "$fixtures/dnsproxyd.py" "$work/"
chmod +x "$work/run-isolated.sh"
gcc -Wall -Wextra -Werror -O2 "$fixtures/reject-strict.c" -o "$work/reject-strict"
mkdir -p "$src/cmd/kst-issue1"
cp "$fixtures/probe.go" "$src/cmd/kst-issue1/main.go"
cd "$src"
CGO_ENABLED=0 "${GO:-go}" build -o "$work/baseline" ./cmd/kst-issue1
set +e
"$work/run-isolated.sh" "$work/baseline" "$work/reject-strict" > "$work/baseline.log" 2>&1
baseline=$?
set -e
[[ $baseline == 1 ]] || { cat "$work/baseline.log"; echo 'Baseline did not fail as expected'; exit 1; }
grep -q 'bound-interface="lo"' "$work/baseline.log"
grep -q 'android-default-installed=true control-dial-installed=false' "$work/baseline.log"
grep -q 'RESULT normal=0 unsupported=1 android_dns=1 combined=1' "$work/baseline.log"
patch --batch --fuzz=0 -p1 < "$fixtures/../../../engine/compat/android-legacy.patch"
CGO_ENABLED=0 "${GO:-go}" build -o "$work/candidate" ./cmd/kst-issue1
"$work/run-isolated.sh" "$work/candidate" "$work/reject-strict" > "$work/candidate.log" 2>&1
"${GO:-go}" test ./net/netmon ./net/netns ./net/dnscache ./feature/androiddns > "$work/upstream-tests.log" 2>&1
printf 'PASS: upstream baseline fails; candidate passes actual Android adapter + routing matrix.\n'
tail -1 "$work/candidate.log"
cat "$work/upstream-tests.log"
