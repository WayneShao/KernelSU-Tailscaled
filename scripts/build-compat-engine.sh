#!/usr/bin/env bash
# Rebuild patched binaries from a pinned upstream archive; no host installation.
set -euo pipefail
[[ $# == 2 ]] || { echo "usage: GO=/path/to/go $0 SOURCE_TARBALL OUTPUT_DIRECTORY"; exit 2; }
root=$(cd "$(dirname "$0")/.." && pwd)
archive=$(realpath "$1")
mkdir -p "$2"
output=$(realpath "$2")
[[ $output != "$root/files" ]] || { echo 'Build to a staging directory, not files/'; exit 2; }
go=${GO:-go}
[[ $("$go" version) == 'go version go1.27.3 '* ]] || { echo 'Go 1.27.3 required'; exit 2; }
[[ $(sha256sum "$archive" | cut -d ' ' -f 1) == 862f12b3177d5e961f2a86cf82fb1ff3551786afcaf95f2dc9a8318889f98732 ]] || { echo 'Source checksum mismatch'; exit 2; }
work=$(mktemp -d "$output/build.XXXXXX")
tar -xzf "$archive" -C "$work"
cd "$work/tailscale-1.104.4"
patch --batch --fuzz=0 -p1 < "$root/engine/compat/android-legacy.patch"
flags='-s -w -buildid= -X tailscale.com/version.shortStamp=1.104.4-kst1 -X tailscale.com/version.longStamp=1.104.4-kst1 -X tailscale.com/version.gitCommitStamp=27047635f237d1f3e0b08c0f487674757f30d2f7'
for arch in arm arm64; do
  for name in tailscale tailscaled; do
    CGO_ENABLED=0 GOOS=linux GOARCH="$arch" GOARM=7 "$go" build -trimpath -buildvcs=false -ldflags="$flags" -o "$output/$name-$arch" "./cmd/$name"
  done
done
cp LICENSE "$output/Tailscale-LICENSE.txt"
printf 'v1.104.4\n' > "$output/VERSION.txt"
printf 'Built compatibility engine in %s\n' "$output"
