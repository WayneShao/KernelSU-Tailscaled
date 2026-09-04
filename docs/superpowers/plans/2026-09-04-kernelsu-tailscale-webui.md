# KernelSU-first Tailscale Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate an in-place `magisk-tailscaled` upgrade that runs official Tailscale binaries under a reliable native-TUN-first supervisor, exposes a compact KernelSU dashboard, and opens Tailscale's localhost-only official device web interface for login and advanced settings.

**Architecture:** Keep persistent state and runtime data under `/data/adb/tailscale`, while the installed module owns immutable service scripts and built WebUI assets under `$MODDIR`. A small manager script presents an idempotent command surface to boot hooks and KernelSU's JavaScript bridge; a separate supervisor owns `tailscaled`, the optional userspace tunnel, and `tailscale web`. Build scripts verify upstream checksums and package contents without modifying tracked source files.

**Tech Stack:** Android `/system/bin/sh`, BusyBox applets supplied by KernelSU/Magisk, official static Tailscale binaries, optional `hev-socks5-tunnel`, KernelSU `kernelsu` JavaScript bridge, TypeScript, Vite, Vitest, Python 3 `unittest`, ADB, GitHub Actions.

---

## File Map

### Module lifecycle and runtime

- `customize.sh`: detect architecture, migrate state, install immutable/runtime files atomically, and set permissions without writing global `service.d` hooks.
- `service.sh`: wait for Android boot and exec the module-owned manager by absolute path.
- `action.sh`: KernelSU/Magisk module Action/Run entry that toggles enabled state and runtime together.
- `uninstall.sh`: stop only module-owned processes, then remove `/data/adb/tailscale` on an actual uninstall.
- `tailscale/config/module.conf`: default configuration copied only when no persistent configuration exists.
- `tailscale/scripts/common.sh`: paths, logging, PID/cmdline validation, socket/listener probes, JSON escaping, and bounded wait helpers.
- `tailscale/scripts/tailscale-service`: public fixed command surface: `enable`, `disable`, `toggle`, `start`, `stop`, `restart`, `status`, `status-json`, `logs`, and `web-restart`.
- `tailscale/scripts/tailscale-supervisor`: component ordering, monitoring, bounded recovery, and module-disable handling.
- `tailscale/scripts/tailscale-daemon`: start/stop/health operations for native or userspace `tailscaled`.
- `tailscale/scripts/tailscale-web`: start/stop/health operations for `tailscale web --listen=127.0.0.1:8088`.
- `tailscale/scripts/tailscale-tunnel`: start/stop/health and route cleanup for the explicit userspace fallback only.
- `system/bin/tailscale`, `system/bin/tailscaled`, `system/bin/tailscaled.service`: optional interactive wrappers; runtime scripts never depend on these overlays.

### WebUI

- `webroot-src/package.json`, `webroot-src/package-lock.json`: pinned frontend toolchain and `kernelsu` bridge dependency.
- `webroot-src/index.html`: Vite entry document.
- `webroot-src/src/main.ts`: refresh/action orchestration and localhost panel navigation.
- `webroot-src/src/api.ts`: allowlisted KernelSU `exec` calls and output decoding.
- `webroot-src/src/model.ts`: strict parsing and normalization of `status-json` output.
- `webroot-src/src/render.ts`: escaped status/log rendering and stable component-state presentation.
- `webroot-src/src/styles.css`: compact responsive dashboard with no remote assets.
- `webroot-src/src/*.test.ts`: state parsing, command allowlist, escaping, and render tests.
- `webroot/index.html`, `webroot/assets/*`: committed reproducible production build consumed directly by KernelSU.
- `NOTICE`: upstream attribution and bundled bridge license notice.

### Verification and release

- `.gitattributes`: force LF for shell/config files and retain binary treatment for executables.
- `scripts/build-release.sh`: checksum-verified official binary fetch and deterministic full/architecture ZIP assembly.
- `scripts/verify-package.py`: ZIP path, metadata, LF, mode, architecture, manifest, and forbidden-file checks.
- `scripts/device-gate.ps1`: one-device-at-a-time feasibility/validation harness with explicit serial binding and evidence capture.
- `tests/test_package.py`: installer, metadata, release-manifest, wrapper, and ZIP contract tests.
- `tests/test_runtime_static.py`: shell safety and runtime ownership/static-invariant tests.
- `tests/fixtures/status/*.json`: Running, NeedsLogin, Stopped, degraded, and preference-state fixtures.
- `.github/workflows/test.yml`: frontend, Python, shell syntax, package, and reproducibility checks.
- `.github/workflows/update.yml`: checksum-verified version update that delegates packaging to `scripts/build-release.sh`.
- `README.md`, `CHANGELOG.txt`: KernelSU WebUI, native/fallback modes, migration, local panel, diagnostics, and first-release compatibility notes.

## Implementation Constraints

- Keep ZeroTier enabled on both test phones and on the wider network throughout this plan.
- Treat ZeroTier as read-only during module development and validation: do not create/edit its files, change routes or firewall rules, or restart/stop its service.
- Bind every ADB command to one current serial from `adb devices -l`; never use an unqualified `adb shell`.
- Test/install on `PKX110` first, then `nezha`; restore the prior Tailscale module runtime before moving to the second device if a gate fails.
- Never depend on `/system/bin/tailscale`; use `/data/adb/tailscale/bin/*` or `$MODDIR/*` absolute paths internally.
- Never overwrite an existing `/data/adb/tailscale/tailscaled.state`.
- Never display or persist a Tailscale login URL, auth key, node private state, or ZeroTier secret in test artifacts.
- Treat the module `disable` marker as the persistent enabled-state source of truth. The Action/Run button changes the marker and runtime together; plain `start`/`stop` commands do not change it.
- Do not apply `accept-routes=false` or `accept-dns=false` automatically for public upgrades. Apply them explicitly only during this migration's device validation after login.
- Do not advertise routes, use an exit node, stop ZeroTier, or change tailnet ACLs during module development.

### Task 1: Establish Test Harness and Repository Invariants

**Files:**
- Create: `.gitattributes`
- Create: `tests/test_runtime_static.py`
- Create: `tests/test_package.py`
- Create: `scripts/verify-package.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add failing line-ending and ownership tests**

Add Python tests that assert every tracked `*.sh`, `*.ini`, `*.conf`, `*.yaml`, and workflow file contains no CRLF; runtime scripts contain no `pidof`/`pkill`/`killall` process-wide termination; module lifecycle files contain no write to `/data/adb/service.d` or `/data/adb/ksu/service.d`; and runtime scripts contain no invocation through `/system/bin/tailscale*`.

- [ ] **Step 2: Run the focused tests and confirm current-source failures**

Run: `python -m unittest tests.test_runtime_static -v`

Expected: FAIL on the current global-service installation, broad process matching, legacy runtime paths, or CRLF files.

- [ ] **Step 3: Add package-verifier contract tests**

Construct temporary good/bad ZIP fixtures in `tests/test_package.py`. Assert rejection of traversal paths, CRLF shell files, missing `module.prop`, missing `webroot/index.html`, duplicate architecture payloads in architecture-specific packages, non-executable scripts, absent `manifest.sha256`, and mismatched hashes.

- [ ] **Step 4: Implement the minimal package verifier**

`scripts/verify-package.py` must accept `--zip PATH --arch {all,arm,arm64}`, parse `module.prop`, validate normalized paths before extraction, inspect ZIP external attributes, verify the manifest using `hashlib.sha256`, and print one deterministic `OK: <zip> (<arch>)` line on success.

- [ ] **Step 5: Run the Python suite**

Run: `python -m unittest discover -s tests -v`

Expected: package-verifier tests PASS; invariant tests remain red only for legacy files intentionally replaced by later tasks.

- [ ] **Step 6: Commit the harness**

```bash
git add .gitattributes .gitignore scripts/verify-package.py tests
git commit -m "test: define module runtime and package contracts"
```

### Task 2: Prove Device Feasibility Before Refactoring

**Files:**
- Create: `scripts/device-gate.ps1`
- Create: `docs/device-tests/README.md`
- Create locally but ignore: `.device-tests/<serial>/<timestamp>/*`

- [ ] **Step 1: Write the ADB gate harness in dry-run mode**

The script must require `-Serial`, validate that exact serial is currently `device`, use `adb -s <serial>` for every call, default to `-DryRun`, and reject simultaneous serials. Its remote staging root is `/data/local/tmp/magisk-tailscaled-gate`; its local evidence root is ignored. Redact `AuthURL`, `LoginURL`, `MachineKey`, `NodeKey`, and `PrivateKey` keys before saving output.

- [ ] **Step 2: Add non-destructive baseline capture**

Capture module version, exact relevant process cmdlines, canonical/legacy state-file existence and SHA-256, `tailscale0`, policy routes, read-only active ZeroTier status without secrets, current ADB transport, and the effective module directory. Abort if ZeroTier is not online or ADB is not reachable. Do not create or edit ZeroTier files and do not restart its service.

- [ ] **Step 3: Add controlled Tailscale 1.102.3 native-TUN gate**

For one selected phone, copy the verified arm64 `tailscale` and `tailscaled` to the staging root. Stop only the existing module-owned Tailscale process after cmdline validation, then run the staged daemon with a temporary state, socket, log, TUN name `tailscale-gate0`, and UDP port `41643`. Validate executable identity, responsive local API, created TUN device, installed table/rule state, and daemon survival across Wi-Fi/cellular rebinding. Stop it by the captured PID and restore the previous module runtime in a `finally` block.

- [ ] **Step 4: Add official web gate for logged-out state**

Start the staged CLI against the staged socket with `web --listen=127.0.0.1:8088`. Validate exact cmdline, listener ownership, and HTTP response from the device. Record only status code/title markers; discard response bodies that may contain login data.

- [ ] **Step 5: Add minimal KernelSU WebView probe**

Install a temporary module containing `webroot/index.html` with two fixed bridge actions: `echo probe-ok` and navigate to `http://127.0.0.1:8088/`. Verify bridge execution and navigation manually on the device, then remove the probe module. Do not use an iframe.

- [ ] **Step 6: Run gates on `PKX110`, then `nezha`**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\device-gate.ps1 -Serial 172.30.83.21:5555 -Run
powershell -ExecutionPolicy Bypass -File .\scripts\device-gate.ps1 -Serial 172.30.11.230:5555 -Run
```

Expected: each device ends with the untouched ZeroTier process still online, prior Tailscale runtime restored, no `tailscale-gate0`, no port 41643 listener, and a redacted evidence summary showing native TUN/local API/web success. If coexistence regresses, stop the temporary Tailscale runtime and change only the Tailscale-side design. If native TUN fails on one device, set that device's later deployment `mode=userspace` explicitly; do not add automatic fallback.

- [ ] **Step 7: Commit the reusable gate harness and redaction docs, not evidence**

```bash
git add scripts/device-gate.ps1 docs/device-tests/README.md .gitignore
git commit -m "test: add isolated Android feasibility gates"
```

### Task 3: Define Persistent Configuration and State Migration

**Files:**
- Create: `tailscale/config/module.conf`
- Create: `tailscale/scripts/common.sh`
- Modify: `customize.sh`
- Delete: `tailscale/settings.ini`
- Delete: `tailscale/scripts/start.sh`

- [ ] **Step 1: Extend failing tests for migration semantics**

Add fixture-driven assertions that the installer preserves canonical state/config/logs, moves `tmp/tailscaled.state` only when canonical state is absent, sets state mode 0600, stages binaries before replacement, quotes the wildcard correctly, does not delete unknown persistent files, and never writes a global service hook.

- [ ] **Step 2: Add immutable default configuration**

Use shell assignments only:

```sh
MODE=native
TUN_NAME=tailscale0
TAILSCALE_PORT=41641
WEB_LISTEN=127.0.0.1:8088
SOCKS_LISTEN=127.0.0.1:1055
SUPERVISOR_INTERVAL=5
RESTART_BACKOFF_MAX=60
```

Validate every setting against an allowlist/range before use. Reject unknown `MODE`; require loopback-only web/SOCKS addresses; require numeric ports and bounded intervals.

- [ ] **Step 3: Implement focused common helpers**

Provide `log`, `read_pid`, `pid_matches`, `owned_stop`, `socket_ready`, `tcp_ready`, `wait_until`, `json_escape`, `load_config`, and `module_disabled`. `pid_matches` must read `/proc/<pid>/cmdline`, compare the expected absolute executable and required fixed arguments, and never use basename-wide matching.

- [ ] **Step 4: Rewrite installation around atomic files**

Extract the selected architecture into `$TMPDIR`, validate each ELF is non-empty/executable and reports the expected Tailscale version where possible, copy scripts/config into the module, stage runtime binaries as `.new`, then `mv` them into place. Preserve the canonical state, persistent config, and logs. Remove only named obsolete scripts/PID/socket files after ownership validation.

- [ ] **Step 5: Run installer/static tests**

Run: `python -m unittest tests.test_runtime_static tests.test_package -v`

Expected: migration/global-service/path tests PASS; failures are limited to runtime files scheduled for subsequent replacement.

- [ ] **Step 6: Commit configuration and migration**

```bash
git add customize.sh tailscale/config tailscale/scripts/common.sh tailscale/settings.ini tailscale/scripts/start.sh tests
git commit -m "feat: preserve Tailscale state during module upgrades"
```

### Task 4: Implement Owned Component Controllers

**Files:**
- Create: `tailscale/scripts/tailscale-daemon`
- Create: `tailscale/scripts/tailscale-web`
- Create: `tailscale/scripts/tailscale-tunnel`
- Delete: `tailscale/scripts/tailscaled.service`
- Delete: `tailscale/scripts/tailscaled.tun`
- Delete: `tailscale/scripts/tailscaled.tun.up`
- Delete: `tailscale/scripts/tailscaled.tun.down`
- Delete: `tailscale/scripts/tailscaled.inotify`
- Rename/modify: `tailscale/scripts/tailscaled.tun.config.yaml` to `tailscale/config/hev-socks5-tunnel.yaml`

- [ ] **Step 1: Add failing controller contract tests**

Assert each controller accepts only `start|stop|health`, writes one PID file, uses the absolute binary, refuses to kill a mismatched PID, removes a stale PID only after cmdline mismatch is proven, and has idempotent start/stop behavior. Assert native mode never starts the tunnel helper.

- [ ] **Step 2: Implement `tailscale-daemon`**

For native mode, run:

```sh
"$BIN_DIR/tailscaled" \
  --tun="$TUN_NAME" \
  --state="$STATE_FILE" \
  --socket="$SOCKET_FILE" \
  --port="$TAILSCALE_PORT"
```

For userspace mode, replace only `--tun` with `--tun=userspace-networking`. Redirect stdout/stderr to `logs/tailscaled.log`, write `$!` atomically, and require both PID identity and `tailscale --socket=... status --json` to consider it healthy. Treat `NeedsLogin` as healthy.

- [ ] **Step 3: Implement `tailscale-web`**

Start only after daemon health succeeds:

```sh
"$BIN_DIR/tailscale" --socket="$SOCKET_FILE" web --listen="$WEB_LISTEN"
```

Health requires PID/cmdline ownership and a TCP listener on exactly `127.0.0.1:8088`. A collision produces a logged degraded state and must not restart the daemon.

- [ ] **Step 4: Implement explicit userspace tunnel controller**

Render the persisted loopback SOCKS endpoint into a runtime-only YAML file, start the architecture-selected `hev-socks5-tunnel`, and use named route/rule priorities owned by this module. `stop` removes only those named/numeric rules and routes. Native mode returns success without mutation.

- [ ] **Step 5: Run focused controller tests on Android shell fixtures**

Run static tests locally, then copy controllers plus fake binaries to `/data/local/tmp` on one phone and verify start/health/stop, stale PID refusal, and duplicate-start prevention without touching the production module.

- [ ] **Step 6: Commit controllers**

```bash
git add tailscale tests
git commit -m "feat: add owned Tailscale component controllers"
```

### Task 5: Implement Supervisor, Manager, and Lifecycle Hooks

**Files:**
- Create: `tailscale/scripts/tailscale-supervisor`
- Create: `tailscale/scripts/tailscale-service`
- Modify: `service.sh`
- Create: `action.sh`
- Modify: `uninstall.sh`
- Modify: `system/bin/tailscale`
- Modify: `system/bin/tailscaled`
- Replace: `system/bin/tailscaled.service`
- Delete: `system/bin/tailscaled.tun`

- [ ] **Step 1: Add failing supervisor/manager tests**

Cover component start order, daemon-dependent web startup, component-only web recovery, daemon crash dependency restart, capped backoff, module-disable teardown, Action/Run toggling, manager command allowlist, stable machine-readable JSON, bounded log output, and owned-PID-only uninstall behavior. Assert `disable` creates the module marker before stopping all owned components, `enable` removes it before starting the supervisor, repeated calls are idempotent, and `toggle` selects exactly one branch from current marker state.

- [ ] **Step 2: Implement supervisor state machine**

On startup validate config/directories, migrate stale runtime files, start daemon, wait up to 30 seconds for API health, start tunnel only in userspace mode, then start web. In the monitor loop, restart a failed web component alone; on daemon failure stop dependents, apply delays `1,2,4,8,16,32,60`, restart daemon, and restore dependencies. Reset backoff after 60 seconds healthy. When `$MODDIR/disable` appears, synchronously stop web, the optional tunnel, and daemon, remove owned runtime files, then exit.

- [ ] **Step 3: Implement the manager command surface**

Expose `enable`, `disable`, and `toggle` in addition to runtime-only `start`, `stop`, and `restart`. The state-changing commands must update the module `disable` marker and actual processes as one operation, rolling back the marker if startup fails. `status-json` must emit one JSON object containing `enabled`, `hostname`, `backendState`, `tailscaleIPv4`, `acceptRoutes`, `acceptDNS`, `exitNode`, `daemon`, `dataPlane`, `web`, `moduleVersion`, `tailscaleVersion`, and `message`. Derive preferences from `tailscale debug prefs` or supported JSON output; represent unavailable values as `null`, never by parsing localized prose. `logs` prints at most the latest 300 lines from named module logs.

- [ ] **Step 4: Replace lifecycle entry points**

`service.sh` waits for `sys.boot_completed=1`, verifies the module is not disabled, then uses `$MODDIR/tailscale/scripts/tailscale-service start`. `action.sh` calls `toggle`, prints whether the resulting state is enabled/running or disabled/stopped, and returns failure if marker/runtime synchronization fails. `uninstall.sh` resolves the installed module path, calls owned stop, then removes `/data/adb/tailscale`; it must not remove arbitrary service scripts or kill by basename.

- [ ] **Step 5: Keep optional interactive wrappers thin**

Wrappers resolve `/data/adb/tailscale/bin` directly. `tailscaled.service` delegates to the manager. They provide convenience only and are not referenced from boot, supervisor, WebUI, or installer logic.

- [ ] **Step 6: Run all runtime tests and an Android disposable-runtime smoke test**

Run: `python -m unittest discover -s tests -v`

Then stage the runtime tree under `/data/local/tmp`, inject a temporary root/state path, and verify exactly one supervisor/daemon/web process, JSON validity, web-only recovery, owned stop, and complete temporary cleanup.

- [ ] **Step 7: Commit runtime supervision**

```bash
git add service.sh action.sh uninstall.sh system tailscale tests
git commit -m "feat: supervise Tailscale runtime by process identity"
```

### Task 6: Build the KernelSU Dashboard

**Files:**
- Create: `webroot-src/package.json`
- Create: `webroot-src/package-lock.json`
- Create: `webroot-src/tsconfig.json`
- Create: `webroot-src/vite.config.ts`
- Create: `webroot-src/index.html`
- Create: `webroot-src/src/api.ts`
- Create: `webroot-src/src/model.ts`
- Create: `webroot-src/src/render.ts`
- Create: `webroot-src/src/main.ts`
- Create: `webroot-src/src/styles.css`
- Create: `webroot-src/src/api.test.ts`
- Create: `webroot-src/src/model.test.ts`
- Create: `webroot-src/src/render.test.ts`
- Create: `webroot/index.html`
- Create: `webroot/assets/*`
- Create: `NOTICE`

- [ ] **Step 1: Scaffold a deterministic frontend build**

Pin exact versions of TypeScript, Vite, Vitest, jsdom, and `kernelsu`. Configure Vite `base: './'`, a fixed `outDir: '../webroot'`, no source maps in production, and deterministic asset names. Add `typecheck`, `test`, and `build` scripts.

- [ ] **Step 2: Write failing model and security tests**

Test all status fixtures, invalid/trailing output rejection, HTML escaping, missing/null preferences, long hostnames, fixed action mapping, and rejection of any action/argument outside `status-json|enable|disable|restart|logs|web-restart`. Assert rendered HTML never uses `innerHTML` with untrusted output.

- [ ] **Step 3: Implement the fixed bridge API**

Map enumerated TypeScript actions to fully quoted fixed commands under `/data/adb/modules/magisk-tailscaled/tailscale/scripts/tailscale-service`. The allowlist includes `status-json`, `enable`, `disable`, `restart`, `logs`, and `web-restart`, but the dashboard presents enable/disable as one state-aware control. Use the `kernelsu` bridge `exec`; normalize stdout/stderr/exit code; expose no method accepting a raw command, path, host, or shell argument.

- [ ] **Step 4: Implement the compact A+B dashboard**

Render a quiet work-focused page showing enabled state, hostname, connection state, IPv4, route/DNS acceptance, exit node, module/engine versions, and daemon/data-plane/web health. Provide controls for enable/disable, refresh, copy IP, restart runtime, logs, and open panel. Use familiar symbols through bundled icon assets or CSS-safe text only; no remote fonts, gradients, decorative cards, or nested cards. The KernelSU module card's Action/Run button uses `action.sh` for the same enable/disable transition, while its Details/WebUI button enters this page.

- [ ] **Step 5: Implement official-panel navigation and recovery**

The panel action checks/restarts the web component, polls status with a hard timeout, then sets `window.location.href = 'http://127.0.0.1:8088/'`. It never embeds an iframe and never proxies panel content. Failure returns to the dashboard with the component error and retry action.

- [ ] **Step 6: Make layout stable at phone widths**

Use fixed-height status rows, `minmax(0,1fr)`, wrapping labels, no viewport-scaled fonts, and icon buttons with stable dimensions. Validate at 360x800, 412x915, 768x1024, and desktop widths; no status text or toolbar action may overlap.

- [ ] **Step 7: Run frontend verification and commit built assets**

Run:

```bash
cd webroot-src
npm ci
npm run typecheck
npm test -- --run
npm run build
cd ..
git diff --exit-code -- webroot || true
```

Re-run `npm run build` and require no second-build diff. Then commit source, lockfile, licenses, and built assets.

```bash
git add webroot-src webroot NOTICE
git commit -m "feat: add KernelSU Tailscale status dashboard"
```

### Task 7: Make Release Builds Verifiable and Reproducible

**Files:**
- Create: `scripts/build-release.sh`
- Create/generated: `files/manifest.sha256`
- Create: `.github/workflows/test.yml`
- Modify: `.github/workflows/update.yml`
- Modify: `module.prop`
- Modify: `update.json`
- Modify: `tests/test_package.py`

- [ ] **Step 1: Add failing release tests**

Test that both official archives are verified against the exact published checksum before extraction; binary hashes are recorded; full, arm, and arm64 ZIPs contain only intended payloads; source files are not modified to select architecture; and two builds from the same tree have identical sorted file lists and content hashes.

- [ ] **Step 2: Implement checksum-verified binary refresh**

Download official archives and their published checksum metadata over HTTPS with retry. Match the exact archive filename, validate `sha256sum -c` before extraction, reject symlinks/path traversal, run each extracted CLI with `version`, then atomically update `files/tailscale-*`, `files/tailscaled-*`, `files/VERSION.txt`, and `files/manifest.sha256`.

- [ ] **Step 3: Implement clean staging and ZIP assembly**

Build in temporary directories from an explicit include list. Normalize timestamps/order, preserve Unix mode bits, exclude `.git`, tests, source-only frontend files, docs, local evidence, and other-architecture binaries as appropriate. Never edit `customize.sh` during packaging.

- [ ] **Step 4: Add CI**

On pushes and pull requests, run Python tests, frontend `npm ci/typecheck/test/build`, verify committed `webroot` is current, run `sh -n` and ShellCheck where available, build all ZIP variants, and run `scripts/verify-package.py` against each. The update workflow uses the same script and creates a release only after all checks pass.

- [ ] **Step 5: Run local release verification**

Run:

```bash
python -m unittest discover -s tests -v
cd webroot-src && npm ci && npm run typecheck && npm test -- --run && npm run build && cd ..
bash scripts/build-release.sh --use-existing-binaries --output dist
python scripts/verify-package.py --zip dist/Magisk-Tailscaled-*.zip --arch all
```

Run architecture-specific verification separately for `arm` and `arm64`. Inspect ZIP listing and manifest hashes.

- [ ] **Step 6: Commit release engineering**

```bash
git add scripts files/manifest.sha256 .github module.prop update.json tests
git commit -m "ci: verify Tailscale binaries and module packages"
```

### Task 8: Install and Validate on `PKX110`

**Files:**
- Create locally but ignore: `.device-tests/172.30.83.21_5555/<timestamp>/*`
- Modify only after results: `docs/device-tests/README.md`

- [ ] **Step 1: Capture the hard pre-install gate**

Re-enumerate ADB, bind to `172.30.83.21:5555`, and prove ZeroTier online, current module/process identity, state path/hash, Android routes, and recovery command. ZeroTier is read-only: save only redacted status/process/counter observations and do not create configuration, alter routing/firewall state, or restart its service.

- [ ] **Step 2: Install the arm64 ZIP as an in-place update**

Push the verified artifact, install through KernelSU's supported command/API, reboot, re-enumerate ADB, and verify the installed module ID/version. Do not remove or recreate the canonical state file.

- [ ] **Step 3: Verify runtime and state continuity before login**

Require one supervisor, one daemon, no userspace helper in native mode, one localhost web process, a responsive API socket, `tailscale0`, and valid `status-json`. Prove state path ownership/mode and node/machine identity continuity where the backend exposes it; do not require an unchanged state-file hash.

- [ ] **Step 4: Validate physical KernelSU WebUI and official panel**

Open the module page, verify all dashboard fields/actions, open the official localhost panel, authenticate there, and return to the dashboard. Keep authentication material out of logs and evidence.

- [ ] **Step 5: Apply migration preferences explicitly**

After login, run the packaged CLI through the explicit socket to set `--accept-routes=false` and `--accept-dns=false`. Read preferences back from structured output and verify no Tailscale subnet routes or DNS takeover appeared.

- [ ] **Step 6: Verify real Tailscale connectivity**

Confirm the phone appears as a distinct online tailnet node, Tailscale ping reaches each existing tailnet node, and at least one actual TCP service is reachable by Tailscale IP. Record endpoint class and success only, not auth/session data.

- [ ] **Step 7: Exercise recovery and network transitions**

Switch Wi-Fi to cellular and back. Separately terminate the owned web child, daemon, and supervisor; verify bounded recovery, no duplicate processes, stable state identity, and ongoing ZeroTier reachability. Disable/re-enable the module and reboot once more, verifying complete owned teardown/startup.

- [ ] **Step 8: Record result and keep ZeroTier enabled**

Update device-test documentation with pass/fail and compatibility notes. Do not stop ZeroTier or add Tailscale subnet routes.

### Task 9: Install and Validate on `nezha`

**Files:**
- Create locally but ignore: `.device-tests/172.30.11.230_5555/<timestamp>/*`
- Modify only after results: `docs/device-tests/README.md`

- [ ] **Step 1: Repeat the hard gate with the current `nezha` serial**

Re-enumerate ADB and bind every operation to `172.30.11.230:5555`. Prove ZeroTier remains online using read-only status and process observations. Do not inspect secret-bearing content, create configuration, alter routes/firewall state, or restart its service.

- [ ] **Step 2: Install the same verified arm64 artifact**

Perform the in-place update and reboot. Confirm the runtime works through absolute paths even though `/system/bin/tailscale` is absent; absence of Magic Mount remains a supported condition.

- [ ] **Step 3: Repeat all runtime, WebUI, login, preference, and connectivity checks**

Require native TUN unless the feasibility gate explicitly selected userspace for this device. Apply `accept-routes=false` and `accept-dns=false` after login, verify structured readback, Tailscale ping, real TCP access, Wi-Fi/cellular rebinding, component recovery, disable/re-enable, and reboot.

- [ ] **Step 4: Compare both-device evidence**

Confirm both phones are distinct online Tailscale nodes, both retain ZeroTier access, neither accepts Tailscale routes/DNS, neither advertises routes, localhost web is not exposed on LAN/Tailscale, and no recursive ZeroTier-over-Tailscale path appears. Detection of recursive traffic fails the Tailscale test and triggers Tailscale rollback; it never triggers a ZeroTier change.

- [ ] **Step 5: Commit only documentation conclusions**

```bash
git add docs/device-tests/README.md
git commit -m "docs: record KernelSU device validation"
```

### Task 10: Documentation, Final Audit, and Release Candidate

**Files:**
- Modify: `README.md`
- Modify: `CHANGELOG.txt`
- Modify: `module.prop`
- Modify: `update.json`
- Modify: `docs/superpowers/specs/2026-09-04-kernelsu-tailscale-webui-design.md`

- [ ] **Step 1: Rewrite usage and upgrade documentation**

Document supported managers/architectures, native default, explicit userspace fallback, canonical state preservation, KernelSU dashboard actions, official panel localhost binding, absolute CLI examples, logs/status commands, and uninstall behavior. State that Magisk is statically checked but not runtime-validated in the first release.

- [ ] **Step 2: Document migration-specific operational policy separately**

Record that this network migration keeps `accept-routes=false` and `accept-dns=false` until ZeroTier parity is proven. Make clear these values are not silently enforced for general module users.

- [ ] **Step 3: Run the complete verification matrix from a clean checkout**

Require clean install dependencies, Python tests, frontend type/tests/build, no generated diff, shell syntax/lint, three package builds, package verifier success, binary manifest verification, and both device test summaries. Scan tracked files and built assets for private keys, auth URLs, IP-specific secrets, and captured node state.

- [ ] **Step 4: Review runtime safety manually**

Confirm every stop path validates PID/cmdline ownership; Action/Run toggle and WebUI enable/disable keep the module marker synchronized with the runtime; every WebUI command is enumerated; every network listener is loopback-only except Tailscale's configured UDP transport; native mode has no fallback route mutation; install/upgrade cannot erase state; and ZeroTier is untouched by the module.

- [ ] **Step 5: Build and hash the release candidate**

Create full/arm/arm64 artifacts in `dist/`, run the verifier, record SHA-256 values, and install the exact arm64 candidate already validated on both phones. Tag/release/fork publication remains a separate explicit repository operation after owner review.

- [ ] **Step 6: Commit documentation and release metadata**

```bash
git add README.md CHANGELOG.txt module.prop update.json docs
git commit -m "docs: prepare KernelSU-first module release"
```

## Completion Gate

This plan is complete only when the repository is clean, all static/frontend/package tests pass, the generated `webroot` is reproducible, the exact arm64 release candidate has passed both KernelSU phones, localhost:8088 is unreachable from non-loopback interfaces, both phones are online as distinct Tailscale nodes with migration preferences disabled, and ZeroTier remains online and unchanged. The broader ZeroTier-to-Tailscale routing migration is not resumed until these module gates and the separate NAS/`WayneShao` node gap are resolved.
