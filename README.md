[![bioluks - KernelSU-Tailscaled](https://img.shields.io/static/v1?label=bioluks&message=KernelSU-Tailscaled&color=blue&logo=github)](https://github.com/bioluks/KernelSU-Tailscaled)
[![Build, Verify, and Release](https://github.com/bioluks/KernelSU-Tailscaled/actions/workflows/release.yml/badge.svg?branch=all-features-merged)](https://github.com/bioluks/KernelSU-Tailscaled/actions/workflows/release.yml)
[![Total downloads](https://img.shields.io/github/downloads/bioluks/KernelSU-Tailscaled/total)](https://github.com/bioluks/KernelSU-Tailscaled/releases)
[![Latest stable release](https://img.shields.io/github/v/release/bioluks/KernelSU-Tailscaled?color=blue)](https://github.com/bioluks/KernelSU-Tailscaled/releases/latest)
[![Open issues](https://img.shields.io/github/issues/bioluks/KernelSU-Tailscaled)](https://github.com/bioluks/KernelSU-Tailscaled/issues)

# KernelSU-Tailscaled

Run the official Tailscale daemon on rooted Android without occupying Android's
VPN slot. KernelSU-first module with a local WebUI, serialized lifecycle control,
diagnostic health checks, explicit legacy migration, and verified runtime updates.

This is **bioluks's fork**, maintained on **all-features-merged**. Version **2.1.1**
combines the English-default WebUI, Chinese language switch, Headscale sign-in,
idle supervisor CPU improvements and Taildrop receiving fixes. See the
[2.1.1 release notes](docs/releases/v2.1.1.md).

Download the [latest published stable release](https://github.com/bioluks/KernelSU-Tailscaled/releases/latest).
The legacy Magisk-Tailscaled v1 release and update channel are retired. Only the
`kernelsu-tailscaled` module line is maintained. Official store review is separate.
This fork continues [WayneShao/KernelSU-Tailscaled](https://github.com/WayneShao/KernelSU-Tailscaled),
based on `ryukora/Magisk-Tailscaled`; it is not an official Tailscale or KernelSU
product. The daemon remains the official Tailscale 1.104.2 binary; this project
maintains the Android module integration. No device-specific kernel is included.

## Identity And Compatibility

| Item | Value |
| --- | --- |
| Module ID | `kernelsu-tailscaled` |
| Source | [bioluks/KernelSU-Tailscaled](https://github.com/bioluks/KernelSU-Tailscaled) |
| Persistent data | `/data/adb/kernelsu-tailscaled` |
| Legacy ID | `magisk-tailscaled` |
| Legacy data | `/data/adb/tailscale`, read only by explicit migration |
| Architectures | ARM and ARM64 |
| Primary manager | KernelSU with WebUI support |

The combined ARM64 build has been exercised on a OnePlus 9 Pro (LE2123).
Earlier upstream testing also targeted OnePlus PKX110 and Xiaomi nezha. Host
tests and package validation do not establish broad Android, Magisk, APatch,
or userspace-tunnel compatibility. See the release notes and `docs/verification`
for actual results and remaining limits.

## Install And Activate

1. Obtain a ZIP from the [current release](https://github.com/bioluks/KernelSU-Tailscaled/releases/latest).
   The universal ZIP includes both architectures; an ARM64-only ZIP is also built.
2. Install the ZIP through KernelSU Manager, or `ksud module install ZIP`.
   The installer verifies the complete bundle, switches the owned runtime, and
   publishes the KernelSU WebUI and Action entrypoints. Existing v2 login and
   configuration are preserved. No post-install patch script is needed.
3. Installation starts the new runtime immediately unless an old login still
   requires explicit migration. No script requests or performs an Android reboot.
4. Open the module WebUI to sign in. Leave **Control server URL** blank for
   Tailscale, or enter your Headscale server URL. For an existing legacy identity,
   follow the migration below before signing in.

Hot installation switches scripts and binaries together and publishes the
complete manager view from that same ZIP. Reopen an already-open Details page
to load its new assets. Normal KernelSU module promotion remains compatible with
the selected runtime. **Apply staged runtime** is also available for a staged
candidate; routine ZIP installation does not need that extra step.

Existing `kernelsu-tailscaled` users can install this fork's ZIP over their current
module. The ID and persistent data directory are unchanged; do not uninstall or
delete state first. The fork ZIP switches subsequent module update checks to
this repository. Upstream installations do not automatically discover this fork;
the first switch is a manual ZIP install. This includes the private `2.1.1-dev.1`
combined build (`versionCode=20000019`); release 2.1.1 advances to 20000020.

## WebUI Language And Headscale

The module WebUI defaults to **English**, regardless of your device language.
Use **Language → 简体中文** in any page header to switch to Simplified Chinese.
The choice is remembered in that WebView; if storage is disabled, it lasts only
for the current session. Raw engine diagnostics and log messages are not translated.

The bundled official Tailscale engine supports Headscale. Under **Sign in /
Headscale**, enter your server's base URL, for example
`https://headscale.example.com`, and choose **Connect / sign in**. Confirm the
server, then open the returned sign-in link and complete registration using your
Headscale server's instructions. Refresh status afterward. If the server is slow
to return a link, use **Open full panel** to finish signing in.

Leave the field blank to return to the official Tailscale service. Changing
servers can disconnect the current network and requires registration on the
selected server; do this locally, not through a Tailscale-only remote session.
The module must be enabled and its daemon running. Migration must be completed
and explicitly enabled first. The URL is saved in Tailscale's persistent
preferences, retaining hostname, DNS, route and other settings across restarts.
HTTPS is recommended. HTTP is accepted for private/test servers but is unencrypted.
Credentials, query parameters and fragments are not accepted in server URLs.

The equivalent root command reads one URL line from standard input:

```sh
printf '%s\n' 'https://headscale.example.com' | \
  sh /data/adb/modules/kernelsu-tailscaled/control.sh login-server
```

Its JSON reply includes the selected `controlURL` and a registration `authURL`
(empty while pending). Treat the registration URL as sensitive; ordinary status
and log output continue to redact authentication URLs. No auth key is required
in the WebUI. See [Headscale client registration](https://headscale.net/stable/usage/connect/android/).

## Update The Tailscale Engine

Open **Tailscale engine update** in Details. Check for an official stable
version, download and verify it, then apply when ready. Downloading does not
interrupt the service; applying briefly restarts it while retaining your login
and settings. No Android reboot is requested.

Downloads use the official HTTPS server and its SHA-256 checksum. Failed
activation restores the previous engine and saved identity. Pending recovery
respects a later stop/disable. Updated engines persist across module installs
and boot; a newer bundled engine takes precedence. See the
[v2.0.5 release notes](docs/releases/v2.0.5.md) for validation and limits.

## Taildrop On Android

Taildrop works in native mode; switching to userspace networking is not required.
The module sets `--statedir=/data/adb/kernelsu-tailscaled` so the Linux daemon can
queue incoming files under `/data/adb/kernelsu-tailscaled/files/`, separately from
the existing login state. Queued files survive service restarts and module updates.
Unlike the Android app, this module does not automatically save them to Downloads.

Retrieve queued files from a root shell:

```sh
TS=/data/adb/kernelsu-tailscaled
"$TS/current/bin/tailscale" --socket="$TS/run/tailscaled.sock" \
  file get /sdcard/Download
```

To send from the phone, use the module's CLI and socket:

```sh
"$TS/current/bin/tailscale" --socket="$TS/run/tailscaled.sock" \
  file cp /sdcard/Download/example.txt <peer-name-or-tailnet-ip>:
```

If you use Headscale instead of the official Tailscale service, your server must
advertise the file-sharing capability. For general Taildrop setup and usage, see
the [official documentation](https://tailscale.com/docs/features/taildrop).

## Migrate An Existing Login

Existing `kernelsu-tailscaled` installations, including beta.5, install the current release
normally and keep their login state. No migration is needed within this module ID.

The old `magisk-tailscaled` ID is retired. Its `update.json` endpoint has been
removed; it does not offer an automatic cross-ID upgrade. The following is a
one-time procedure for retained legacy data, not a maintained v1 upgrade channel.

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

The supervisor checks owned processes every `SUPERVISOR_INTERVAL` seconds
(default: five), including while logged out so the daemon and login panel can
recover. It does not poll authentication, peer routes, or network health in this
loop; detailed diagnostics run when requested. Manager descriptions and pending
hot-install finalization refresh about once a minute, not every health pass.
Descriptions have no ticking clock and unchanged content is not rewritten.
IPv4 queries are time-bounded and skipped when the service is not running or
its socket is missing. Native mode does not mean kernel WireGuard: Tailscale
still handles encryption in its userspace daemon.

On-device idle profiling (Android mksh, five-second supervision, real logged-out
daemon and panel in isolated state/ports) measured supervisor plus child CPU
at 7.73 CPU-seconds per 60.43 seconds before, versus 0.42/60.64 and 0.40/60.38
after: about 95% less supervisor CPU. The daemon used userspace networking to
avoid changing the active TUN; the supervisor used the native process-check
branch. Both fixed samples left Manager metadata unchanged, and killing the
isolated panel exercised successful HTTP recovery while still logged out.
This is CPU evidence, not a screen-off battery-life or tunnel-mode benchmark.

```text
/data/adb/modules/kernelsu-tailscaled/control.sh
  {enable|disable|toggle|start|stop|restart|status|status-json|logs|
   web-restart|diagnostics|migration-status|migrate-legacy|apply-staged|login-server}
```

The WebUI invokes only a fixed command allowlist; `login-server` additionally
accepts one validated HTTP/HTTPS base URL on stdin. The full official panel binds
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

The default `all-features-merged` branch, `main` and feature branches build
artifacts without publishing. `v2.*-*` tags publish as prereleases; stable tags
additionally require `STABLE_RELEASE_APPROVED=true` and
the `source-release` environment. Enable repository release immutability before
tag publication, then set `SOURCE_IMMUTABILITY_CONFIRMED=true` after checking the
setting with an administrator account. `GITHUB_TOKEN` cannot read that admin-only
setting; an optional, narrowly scoped `SOURCE_RELEASE_READ_TOKEN` enables a live
preflight instead. This configuration acknowledgement does not replace the
post-publication check: the workflow fails unless the actual release is immutable
and all assets pass GitHub's release attestation verification.

Tag builds call `publish-source.yml`. Its manual entry can resume publication
using the original tag and build run ID without rebuilding packages or moving
the tag. It verifies the successful build's commit and all existing draft assets
before publishing; already published immutable assets are verified, not replaced.

Fork releases are distributed on this repository's GitHub Releases page. The
upstream store submission is historical and does not approve this fork; store
publication remains disabled unless separately reviewed and authorized.

Official store requirements are documented in
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
- [WayneShao/KernelSU-Tailscaled](https://github.com/WayneShao/KernelSU-Tailscaled):
  upstream module, lifecycle implementation and retained release tooling.
- [hev-socks5-tunnel](https://github.com/heiher/hev-socks5-tunnel): userspace helper.
- [ryukora/Magisk-Tailscaled](https://github.com/ryukora/Magisk-Tailscaled),
  ANASFANANI, and prior contributors: original module and retained history.

See [LICENSE](LICENSE), [NOTICE](NOTICE), and `webroot/licenses` for license texts.
