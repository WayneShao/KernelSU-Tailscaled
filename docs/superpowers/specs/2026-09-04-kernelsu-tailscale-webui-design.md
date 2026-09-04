# KernelSU-first Tailscale Module Design

Date: 2026-09-04
Status: Approved direction, pending implementation plan
Base repository: `ryukora/Magisk-Tailscaled`
Feature branch: `feature/kernelsu-webui`

## 1. Objective

Create a maintainable, drop-in replacement for the existing
`magisk-tailscaled` module that combines:

- the current official Tailscale binaries and release automation from the
  ryukora fork;
- the simpler native-TUN runtime and state migration behavior from
  anasfanani v2;
- a KernelSU WebUI that presents local device and service status, then opens
  Tailscale's official local web interface for login and advanced settings;
- reliable process supervision that does not report stale PID files as a
  healthy service.

The first release is KernelSU and KernelSU Next focused. Magisk keeps the
background service and CLI behavior. Runtime validation is required on the
owner's two KernelSU phones (`PKX110` and `nezha`); Magisk compatibility is
validated statically in the first release.

## 2. Confirmed Baseline

- Both phones currently run `magisk-tailscaled` v2.0.0.1 with Tailscale
  1.90.6.
- Both phones have a working root-started `tailscaled` process using the
  default native TUN mode, despite stale README text describing only
  userspace networking.
- Current state is stored at `/data/adb/tailscale/tailscaled.state`.
- The `nezha` device does not expose the module wrappers through
  `/system/bin` even after reboot. Internal services and WebUI actions must
  therefore use absolute paths and must not depend on Magic Mount or a
  KernelSU metamodule.
- The ryukora fork's Tailscale 1.102.3 arm64 `tailscale` and `tailscaled`
  files match the official static package byte for byte by SHA-256.
- Neither upstream module contains a KernelSU `webroot`.

### Implementation feasibility gates

Before restructuring the module, prove the three uncertain platform boundaries
with disposable runtime tests:

1. run the official Tailscale 1.102.3 arm64 daemon in native TUN mode on each
   phone, one at a time, and verify that its local API socket, `tailscale0`,
   route installation, and network rebinding work on Android;
2. run the packaged `tailscale web` against the module's explicit socket and
   verify localhost access while the backend is both `NeedsLogin` and
   `Running`;
3. install a minimal KernelSU `webroot` probe that uses the official JavaScript
   bridge and navigates the manager WebView to `http://127.0.0.1:8088/`.

A failed gate changes the implementation plan before broad refactoring. Native
TUN failure selects the explicit userspace compatibility path for that device.
WebView navigation failure selects a launcher-mediated external browser open,
not an iframe or a second implementation of the Tailscale panel.

## 3. Scope

### In scope

- Arm and arm64 module packages containing official static Tailscale
  binaries.
- Native TUN as the default data plane.
- Explicit userspace-networking plus hev-socks5-tunnel compatibility mode.
- KernelSU WebUI status dashboard and fixed maintenance actions.
- Tailscale official web interface on localhost.
- Upgrade migration from both known state layouts.
- Boot startup, crash recovery, disable handling, and deterministic logs.
- Automated binary provenance checks and reproducible module ZIP creation.

### Out of scope for the first release

- Reimplementing Tailscale login, account, route, DNS, exit-node, ACL, or
  peer-management forms.
- Exposing the device web interface to LAN, the tailnet, or the public
  internet.
- Automatic fallback from native TUN after transient network failures.
- Full runtime validation on Magisk or APatch.
- Changing or stopping ZeroTier as part of module installation.
- Advertising subnet routes automatically.

## 4. User Interface

KernelSU discovers `webroot/index.html`. The page is a compact local dashboard
with no remote assets and no arbitrary command input.

The dashboard displays:

- hostname and Tailscale backend state;
- Tailscale IPv4 address;
- accept-routes, accept-DNS, and exit-node summaries;
- health of `tailscaled`, the selected data plane, and the local web server;
- installed module and Tailscale versions.

The dashboard provides these fixed actions:

- refresh status;
- copy the Tailscale IP;
- restart the module runtime;
- open recent logs;
- open the full Tailscale panel.

The dashboard reports Tailscale preferences but does not enforce or rewrite
them. Migration-specific settings such as `accept-routes=false` and
`accept-dns=false` are applied explicitly by the deployment procedure after a
device logs in. Existing users upgrading the public module keep their current
preferences.

The full-panel action navigates the WebView to
`http://127.0.0.1:8088/`. It does not use an iframe. Tailscale owns login,
check-mode authentication, and all advanced setting changes.

If localhost:8088 is unavailable, the dashboard reports the failed component,
offers a web-component restart, waits for the listener, and then retries the
navigation.

The dashboard bundles the Apache-2.0 `kernelsu` JavaScript bridge. Calls to
`exec` invoke only fixed module scripts and enumerated action arguments.
User-controlled strings are never interpolated into shell commands.

Maintainable WebUI source lives in `webroot-src/`; reproducible production
assets are committed under `webroot/` so module installation and use do not
require Node.js or internet access.

## 5. Repository And Packaging

Development continues from the ryukora Git history on
`feature/kernelsu-webui`. The module ID remains `magisk-tailscaled` so the
package is an in-place upgrade.

The repository retains upstream attribution and BSD-3-Clause notices. The
KernelSU bridge's Apache-2.0 notice is included with the built WebUI.

The package is self-contained and does not download executables during module
installation. Release automation:

1. reads the stable Tailscale version from the official package site;
2. downloads official arm and arm64 archives and published checksum files;
3. verifies archive checksums before extraction;
4. records binary SHA-256 values in a release manifest;
5. builds full and architecture-specific module ZIP files;
6. validates ZIP structure, shell line endings, executable modes, and version
   metadata before creating a release.

## 6. Persistent Layout

The canonical runtime layout is:

```text
/data/adb/tailscale/
  bin/
    tailscale
    tailscaled
    hev-socks5-tunnel
  config/
    module.conf
  logs/
    supervisor.log
    tailscaled.log
    web.log
    tunnel.log
  run/
    supervisor.pid
    tailscaled.pid
    tailscaled.sock
    web.pid
    tunnel.pid
  tailscaled.state
```

Upgrade rules:

- Never overwrite an existing canonical `tailscaled.state`.
- If the canonical file is absent and
  `/data/adb/tailscale/tmp/tailscaled.state` exists, move it atomically to the
  canonical location and set mode 0600.
- Preserve `module.conf` and logs during upgrades.
- Stage new binaries before stopping the old runtime, validate them, then
  replace executable files atomically.
- Remove stale sockets and PID files only after proving their referenced
  processes do not exist or do not match the expected executable.
- A normal uninstall stops all owned processes and removes runtime state. An
  upgrade is not treated as an uninstall.

## 7. Runtime Components

### `service.sh`

Waits for Android boot completion and launches the supervisor through an
absolute module path. It remains compatible with KernelSU's and Magisk's
late-start service execution.

### Supervisor

The supervisor owns component ordering and recovery:

1. validate configuration and runtime directories;
2. start `tailscaled`;
3. wait for a responsive local API socket;
4. start the selected data-plane helper only when userspace mode is selected;
5. start the local Tailscale web process;
6. monitor child identity, socket response, and listener health;
7. restart only the failed component where dependencies permit;
8. apply bounded retry delays and log every state transition;
9. stop all owned components when the module is disabled.

Health is not inferred from a PID file alone. A healthy component requires:

- a live PID;
- a matching `/proc/<pid>/cmdline` executable and arguments;
- its expected socket or listener where applicable;
- a successful CLI status probe for `tailscaled`.

The manager script exposes `start`, `stop`, `restart`, `status`, `status-json`,
`logs`, and `web-restart`. Commands are idempotent.

### Tailscaled

Default invocation uses native TUN and explicit paths:

```text
tailscaled --tun=tailscale0 \
  --state=/data/adb/tailscale/tailscaled.state \
  --socket=/data/adb/tailscale/run/tailscaled.sock \
  --port=41641
```

The final argument spelling is validated against the packaged Tailscale
version before release. Native mode does not start hev-socks5-tunnel.

Compatibility mode uses `--tun=userspace-networking`, a local SOCKS listener,
and hev-socks5-tunnel. Switching mode is explicit in `module.conf` and requires
a runtime restart. The supervisor does not silently change modes.

### Official web process

After the daemon socket responds, start:

```text
tailscale --socket=/data/adb/tailscale/run/tailscaled.sock \
  web --listen=127.0.0.1:8088
```

The listener remains localhost-only. The supervisor verifies both the process
identity and TCP listener. A web crash does not restart the data plane.

## 8. Failure Handling

- Stale PID: delete it after PID and cmdline validation, then start once.
- Stale socket: remove it only when no matching daemon owns it.
- Daemon crash: stop dependent web and userspace helper, restart daemon with
  bounded backoff, then restore dependencies.
- Web crash or port collision: keep Tailscale connected, expose the error in
  the dashboard, and restart only the web component after the port is free.
- Native TUN startup failure: report the failure and provide instructions to
  select compatibility mode; do not switch automatically.
- Logged-out backend: show `NeedsLogin` as a valid daemon state and keep the
  official web interface available.
- Network transition: keep processes running while Tailscale rebinds; do not
  classify temporary coordination loss as a daemon failure.
- Module disable: terminate only PIDs whose command lines match module-owned
  executables, then remove module-created routes and runtime files.

## 9. Security

- Bind the official web interface to 127.0.0.1 only.
- Do not store auth keys, login URLs, private node keys, or control-plane
  responses in module configuration or WebUI storage.
- Preserve Tailscale's own check-mode authentication for settings changes.
- Bundle all WebUI assets; make no CDN requests.
- Escape all CLI output before rendering.
- Keep the WebUI shell interface to an enumerated command allowlist.
- Never accept a raw shell command, file path, host, or argument from a form.
- Release workflows verify official archive checksums and record extracted
  binary hashes.

## 10. Verification

### Static and package verification

- Run shell syntax checks and ShellCheck where supported.
- Run WebUI formatting, type checks, unit tests, and a production build.
- Test status JSON parsing against Running, NeedsLogin, Stopped, stale-PID,
  missing-socket, and web-port-collision fixtures.
- Verify module ZIP paths, LF endings, modes, metadata, notices, architecture
  selection, and recorded SHA-256 values.
- Render the WebUI at representative phone and desktop widths and verify that
  controls do not overlap or shift.

### Device verification

Install and validate on one phone at a time while ZeroTier remains online.
For each of `PKX110` and `nezha`:

1. capture current module, process, state-file hash, ZeroTier identity, routes,
   and ADB reachability;
2. install the new ZIP as an in-place module update;
3. reboot and confirm the canonical state path was reused and the Tailscale
   machine/node identity is continuous; the file hash may legitimately change
   when a newer daemon updates its state;
4. confirm exactly one supervisor, daemon, selected tunnel helper, and web
   process;
5. confirm native `tailscale0`, Tailscale IP, backend state, disabled route and
   DNS acceptance, and localhost:8088;
6. open the KernelSU WebUI and official panel on the physical device;
7. authenticate through the official panel without enabling subnet routes;
8. explicitly set `accept-routes=false` and `accept-dns=false` for the migration,
   then verify Tailscale-layer ping and actual TCP access to known tailnet
   devices;
9. switch Wi-Fi to cellular and back, checking rebinding and recovery;
10. kill web, daemon, and supervisor children separately and verify bounded
    recovery without duplicates;
11. disable and re-enable the module and verify complete teardown/startup;
12. reboot again and repeat process, socket, route, WebUI, and connectivity
    checks.

ZeroTier remains enabled until both phones are online in Tailscale and the
larger migration inventory and reachability gate is satisfied. Before parallel
traffic tests, ZeroTier on each phone must ignore `tailscale*` interfaces to
avoid recursive overlay transport.

### Compatibility statement

The first release may state:

- runtime verified: KernelSU/KernelSU Next on PKX110 and nezha;
- package and script compatibility retained but not device-tested: Magisk;
- not verified: APatch and other Android devices.

## 11. Acceptance Criteria

- Installing over the current module preserves the Tailscale identity state.
- Both test phones boot with one healthy native-TUN Tailscale runtime.
- KernelSU shows the hybrid dashboard and all fixed actions work.
- The official Tailscale panel opens from the dashboard on localhost only.
- Login can be completed from the official panel.
- The deployment procedure can set route and DNS acceptance off after login,
  and the module preserves those preferences across restart and reboot.
- The dashboard never reports healthy from a stale PID file.
- Killing any one owned process produces bounded recovery without duplicates.
- Wi-Fi and cellular transitions do not require manual service restarts.
- Packaged Tailscale binaries match verified official artifacts.
- Existing ZeroTier connectivity remains intact throughout module validation.
