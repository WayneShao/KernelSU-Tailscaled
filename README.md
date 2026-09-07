# KernelSU-Tailscaled

Run the official Tailscale daemon on rooted Android without occupying Android's
VPN slot. KernelSU-first module with a local WebUI, serialized lifecycle control,
diagnostic health checks, explicit legacy migration, and verified runtime updates.

**2.0.0-beta.5 is a prerelease, not a stable release or an approved store listing.**
This is an independent continuation of `ryukora/Magisk-Tailscaled`, not an official
Tailscale or KernelSU product. The daemon remains the official Tailscale 1.102.3
binary; this project maintains the Android module integration.

## Identity And Compatibility

| Item | Value |
| --- | --- |
| Module ID | `kernelsu-tailscaled` |
| Source | [WayneShao/KernelSU-Tailscaled](https://github.com/WayneShao/KernelSU-Tailscaled) |
| Persistent data | `/data/adb/kernelsu-tailscaled` |
| Legacy ID | `magisk-tailscaled` |
| Legacy data | `/data/adb/tailscale`, read only by explicit migration |
| Architectures | ARM and ARM64 |
| Primary manager | KernelSU with WebUI support |

ARM64 testing targets are the maintainer's OnePlus PKX110 and Xiaomi nezha.
Host tests and package validation do not establish broad Android, Magisk,
APatch, or userspace-tunnel compatibility. See the candidate verification record
under `docs/verification` for actual results and remaining limits.

## Install And Activate

1. Obtain a verified ZIP from [source builds/releases](https://github.com/WayneShao/KernelSU-Tailscaled/actions).
   The universal ZIP includes both architectures; an ARM64-only ZIP is also built.
2. Install the ZIP through KernelSU Manager, or `ksud module install ZIP`.
   The installer verifies the complete bundle, switches the owned runtime, and
   publishes the KernelSU WebUI and Action entrypoints. Existing v2 login and
   configuration are preserved. No post-install patch script is needed.
3. Installation starts the new runtime immediately unless an old login still
   requires explicit migration. No script requests or performs an Android reboot.
4. For a fresh identity, open the official local panel
   to sign in. For an existing legacy identity, follow the migration below.

Hot installation switches scripts and binaries together and publishes the
complete manager view from that same ZIP. Reopen an already-open Details page
to load its new assets. Normal KernelSU module promotion remains compatible with
the selected runtime. **Apply staged runtime** is also available for a staged
candidate; routine ZIP installation does not need that extra step.

## Migrate An Existing Login

The changed ID intentionally prevents an implicit upgrade over an old module.
The old `update.json` remains on the existing v1 release; v2 uses a separate feed.

1. Stop the legacy Tailscale service explicitly, then disable the legacy module.
   Do not uninstall it with a legacy uninstall script that deletes its identity.
2. Invoke **Migrate legacy identity** in the new module or run its control entry
   with `migrate-legacy`. The module verifies that old/new daemons and watchers are
   stopped before proceeding.
3. Migration copies the identity and validated configuration; it never moves,
   deletes, replaces, or logs the legacy state. Existing destination identity or
   unrelated configuration is preserved and causes the operation to stop.
4. Enable the new module explicitly. Migration itself leaves it stopped, even
   across a subsequent boot. Existing hostname, DNS, route and exit preferences
   are retained. No duplicate identity should run in the old module concurrently.

An interrupted migration keeps a hash-checked journal. Repeating migration
resumes only matching transaction-owned data; changed destination content is
preserved for inspection. `migration-status` distinguishes incomplete migration,
awaiting enable, existing destination, and absent legacy state.

## Runtime And Configuration

Persistent identity, configuration and logs are separate from manager files.
Complete checked generations live under `releases/`; `current` selects the active
generation and `previous` records the prior one. Activation rejects engine
downgrades. Failed activation can automatically restore a prior generation only
when its engine version is identical; arbitrary state-format rollback is not
promised. Generations are retained for diagnosis, not automatically pruned.

`config/module.conf` is parsed as data, never sourced as shell code:

```ini
MODE=native
TUN_NAME=tailscale0
TAILSCALE_PORT=41641
WEB_LISTEN=127.0.0.1:8088
SOCKS_LISTEN=127.0.0.1:1055
CONTROL_PROXY=
DEVICE_HOSTNAME=
SUPERVISOR_INTERVAL=5
RESTART_BACKOFF_MAX=60
```

Native mode is explicit. Userspace mode requires the bundled helper and is never
silently selected after an interface failure. An optional loopback HTTP/SOCKS5
`CONTROL_PROXY` affects control-plane requests, not direct WireGuard traffic.
No script edits another module's firewall, proxy, DNS, or ZeroTier configuration.

Fresh identities initialize a hostname from the Android device name, falling
back to product/model, and begin with DNS/subnet acceptance and exit routing off.
Existing identities retain their preferences. The dashboard prefers the
control-plane DNS name so admin-console renaming appears correctly.

The status contract reports lifecycle, owned processes, real native interface
and applicable routes, upstream health warnings, preferences, and active/staged
versions separately. An API timeout or missing interface is not reported healthy.
These local checks do not prove end-to-end peer reachability.
If process identity checks disagree while the recorded process is still alive,
the controller retains its record and socket and blocks replacement. It does
not treat an inconclusive ownership check as proof that the process exited.

```text
/data/adb/modules/kernelsu-tailscaled/control.sh
  {enable|disable|toggle|start|stop|restart|status|status-json|logs|
   web-restart|diagnostics|migration-status|migrate-legacy|apply-staged}
```

The WebUI invokes only a fixed command allowlist. The full official panel binds
to IPv4 loopback. Log output is size-bounded and redacts keys, login URLs and proxy
credentials. Treat any diagnostics as potentially containing device/network names.
Uninstall stops owned processes but preserves v2 data. To intentionally discard a
login, stop/uninstall the module first, then manually remove its isolated data
directory. Legacy data is a separate ownership domain and is never purged by v2.

## Development And Distribution

```bash
python3 -m unittest discover -s tests -v
cd webroot-src
npm ci
npm run typecheck
npm test
npm run build
cd ..
sh scripts/build-release.sh --use-existing-binaries --output dist
```

Run process/lifecycle behavior tests on Linux or WSL; Windows-only unit tests skip
those tests. Packages normalize LF, ordering, timestamps and executable modes.
Binary payload manifests and architecture-specific installed-bundle manifests are
verified independently. CI rebuilds all ZIPs twice and compares their bytes.

Feature branches build artifacts without publishing. `v2.*-*` tags publish as
prereleases; stable tags additionally require `STABLE_RELEASE_APPROVED=true` and
the `source-release` environment. Enable repository release immutability before
tag publication, then set `SOURCE_IMMUTABILITY_CONFIRMED=true` after checking the
setting with an administrator account. `GITHUB_TOKEN` cannot read that admin-only
setting; an optional, narrowly scoped `SOURCE_RELEASE_READ_TOKEN` enables a live
preflight instead. This configuration acknowledgement does not replace the
post-publication check: the workflow fails unless the actual release is immutable
and all assets pass GitHub's release attestation verification.

The official store submission and distribution requirements are documented in
[the research record](docs/research/2026-09-07-kernelsu-store-requirements.md).
Submission requires manual review and is not performed by the build workflow.
After approval, configure the store repository's default-branch metadata,
immutable releases, a protected `kernelsu-store` environment, and a separately
scoped `KERNELSU_STORE_TOKEN` with destination contents write and administration
read permissions. Set `STORE_PUBLICATION_ENABLED=true` only after those steps.
The manual store workflow accepts a previously verified immutable stable source
release and publishes **one universal ZIP**, never an architecture-specific
default download. It never replaces existing assets or tags.

## Credits And License

- [Tailscale](https://github.com/tailscale/tailscale): official daemon and CLI.
- [KernelSU](https://github.com/tiann/KernelSU): root manager and WebUI bridge.
- [hev-socks5-tunnel](https://github.com/heiher/hev-socks5-tunnel): userspace helper.
- [ryukora/Magisk-Tailscaled](https://github.com/ryukora/Magisk-Tailscaled),
  ANASFANANI, and prior contributors: original module and retained history.

See [LICENSE](LICENSE), [NOTICE](NOTICE), and `webroot/licenses` for license texts.
