> Historical candidate record. Current acceptance and results:
> [v2.0.5 validation](2026-10-22-release-2.0.5.md).

# Android native socket routing fix — local beta.4

Not published. Maintainer acceptance is required before any release or tag.

## Mechanism

The official Linux engine sets SO_MARK to 0x80000 by default. On the affected
Android routing configuration, rule 5210 looks up main, rule 5230 looks up default,
then rule 5250 rejects traffic. Android stores its real default in interface
tables instead, so adding a main-table default would duplicate network state.

Upstream already implements `TS_FORCE_LINUX_BIND_TO_DEVICE=true`, selecting
SO_BINDTODEVICE and `netmon.DefaultRouteInterface()` instead of SO_MARK:

- https://github.com/tailscale/tailscale/blob/v1.104.2/net/netns/netns_linux.go
- https://github.com/tailscale/tailscale/blob/v1.104.2/net/netmon/interfaces_linux.go

The module exports that option when loading native-mode configuration on Android.
It keeps the official engine binaries and does not copy routes, pin Wi-Fi interface
names, modify hosts, or patch an immutable runtime after installation.

## Tests and device evidence

- Full WSL suite: 122 tests passed without skips. Android daemon environment and
  absence of marked-route dependency are covered, with ordinary Linux behavior
  preserved. Regression failed before implementation, passed after implementation.
- OnePlus netcheck with the upstream option false: UDP false, no public IPv4.
- Same command with the option true: UDP true, public IPv4 mapping and DERP RTTs.
- Isolated fresh daemon: separate socket, `--state=mem:`, userspace TUN to avoid
  altering the live daemon's routes, no proxy environment. Registration returned
  an authentication URL. The temporary process/state were cleaned up. This proves
  pre-login DNS/TLS/control connectivity, not completed browser authorization.
- Installed ARM64 ZIP hash:
  `1a7ba62903cb235683427d5db790631c8445bbf3ccf9e842d23189cc672dd5ac`.
- Installed native daemon reports udp=true and STUN public endpoints. Public
  direct pings: OpenWrt 11 ms, Tencent node 14 ms.
- Existing OnePlus identity-state SHA-256 preserved.

## Remaining acceptance

beta.4 is hot-installed after beta.3's reboot verification, so beta.3's boot test
does not count as a beta.4 reboot test. The original reporter ROM, ARM32 runtime,
Wi-Fi/cellular handover, and complete new-account browser authorization remain
unverified. No new publication is authorized until the maintainer confirms the
specific tested version.
