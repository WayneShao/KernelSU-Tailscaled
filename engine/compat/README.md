# Android legacy login compatibility engine

This beta distributes a **modified**, not official, Tailscale engine:
`1.104.4-kst1`. Numeric state/update ordering remains `1.104.4`.
See `source.json` for the pinned upstream commit, source checksum and Go version.
The upstream BSD license is shipped at `tailscale/Tailscale-LICENSE.txt`.

## Changes

- Retry route-netlink initialization without strict checking only when the
  kernel returns ENOPROTOOPT/EOPNOTSUPP. Do not bypass permission failures.
- Feed the already-selected Android dnsproxyd resolver to dnscache's forwarder,
  which the control client copies; do not change resolvers on non-Android hosts.
- Return an explicit outbound-interface discovery error instead of silently
  binding control sockets to loopback. Never fall back to unbound sockets.

## Rebuild

On Linux/WSL, obtain the source archive listed in `source.json` and Go 1.27.3.
Use a staging output directory, then inspect outputs before updating `files/`:

```sh
GO=/path/to/go scripts/build-compat-engine.sh tailscale-v1.104.4.tar.gz ./engine-output
```

The script verifies source SHA256 and toolchain version, applies the patch
without fuzzy matching, builds CGO-disabled Linux ARMv7/ARM64 binaries, stamps
the modified version, and emits the upstream license. Dependencies are verified
using upstream go.sum and Go's checksum database (do not set GOSUMDB=off).

## Beta update policy

`tailscale/engine-policy` pins this beta to its bundled compatibility engine.
An external official engine of the same/older numeric version is retained on
disk but not selected. A newer external engine is rejected before stopping the
current service rather than silently downgraded. Official engine check remains
read-only; download/apply is disabled until a module release changes the policy.
Install the ZIP normally through the module manager; no manual pointer edits.
Stable update feeds remain on v2.0.5.

## Reproduction

`tests/compat/issue1/verify-pair.sh` builds the pristine and patched upstream code
and checks both negative and positive results. Requires x86_64 Linux, gcc,
Python, iproute2, util-linux, user/network/mount namespaces, and the pinned Go.

```sh
GO=/path/to/go tests/compat/issue1/verify-pair.sh tailscale-v1.104.4.tar.gz ./evidence
```

This uses real upstream code, a private Android dnsproxyd wire-protocol fixture,
empty resolver configuration, a policy-table-only default route, and a seccomp
filter that rejects the strict-check socket option. It also tests supported
strict checking, EPERM, EOPNOTSUPP, changed interface, no route and recovery.
Host network routes and DNS are untouched.

For full native-daemon validation, build upstream cmd/tailscale and
cmd/tailscaled from the patched tree, copy `tests/compat/issue1/control.go` into
a temporary `cmd/kst-control/main.go` there and build it. Run
`daemon-isolated.sh DAEMON CLI TESTCONTROL SECCOMP OUTPUT_DIRECTORY` alongside
`dnsproxyd.py`. It asserts a new auth URL, completes local test authorization,
and checks BackendState=Running plus the native TUN. It uses a private mock
control/DERP/STUN server, not a production account.

These reproduce failure mechanisms; they do not emulate the reporter's entire
Android ROM, SELinux policy, vendor kernel or SukiSU implementation. ARM builds
are cross-compiled, not proof of ARM hardware acceptance. Real-device beta
feedback remains required before stable promotion.
