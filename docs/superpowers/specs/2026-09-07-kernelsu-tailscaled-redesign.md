# KernelSU-Tailscaled Runtime and Store-Ready Distribution

Status: owner approved the independent ID, explicit migration, and focused redesign.
The owner subsequently authorized standard ZIP installation through ksud on both
phones and immediate hot activation with preserved existing Tailscale identities.
The owner subsequently authorized code publication, an Actions-built source
prerelease, and submission for official store review after package verification.
Device reboot is not authorized. Long-term stability remains an observation gate.

## Identity and Platform

- Source: WayneShao/KernelSU-Tailscaled; module ID: kernelsu-tailscaled.
- New persistent root: /data/adb/kernelsu-tailscaled, root-only permissions.
- Candidate module version: 2.0.0-beta.5; integer versionCode: 20000005.
- Bundle official Tailscale 1.102.3; show engine and module versions separately.
- KernelSU first, shell hooks retained; keep Magisk-compatible script/install
  behavior where supported, without claiming untested WebUI parity.
- Reuse TypeScript/Vite/Lucide and pinned dependencies. No VPN protocol rewrite.
- Keep arm/arm64 package support; only the owner's arm64 phones are device-test targets.

## Runtime Layout and Ownership

Standard ZIP installation extracts a complete module into the manager-provided
MODPATH, including bin/tailscale, bin/tailscaled, optional userspace helper,
scripts, WebUI, metadata, and checksums. The installer must not overwrite live
external runtime binaries or mutate existing network settings.

Persistent state contains config, tailscaled.state, logs, run, and immutable
runtime bundles under releases. A validated current symlink selects one complete
bundle (scripts and binaries together). previous records the prior bundle for
inspection, not permission for arbitrary state-schema downgrades.

Thin service.sh/action.sh/control.sh entrypoints resolve the selected bundle.
First activation copies a fully validated manager module to a new bundle and
atomically publishes current. apply-staged explicitly activates the fixed
/data/adb/modules_update/kernelsu-tailscaled candidate without a device reboot.
It stops only the current owned runtime, switches the complete generation, and
starts it. Activation never silently downgrades the bundled engine. On a failed
new start retain both generations and the failure record; restore a previous
generation automatically only when the bundled engine version is unchanged.
Public updates remain standard manager ZIP installation. The complete installer
prepares manager assets, activates the runtime, and publishes WebUI and hooks
from the same ZIP. No post-install script repairs are part of deployment.
An already-open WebUI must be reopened to load changed assets. Active/staged
versions remain visible; Android reboot is not required.

At boot only, reconcile the manager's active MODDIR bundle: activate when no
current exists or its versionCode is greater than current. Retain current when
MODDIR is identical or older (including a hot-applied update before promotion).
Equal versionCode with a different bundle digest is an integrity/version error,
not an implicit replacement. Normal manager promotion after hot activation is
idempotent. Test normal ZIP promotion and hot-apply followed by promotion.

Runtime script location is derived from the actual bundle path (BUNDLE_DIR).
MODDIR means the active KernelSU module directory for disable/remove markers.
TS_DIR is the independent persistent root. Tests may override these locations
only through the explicit process environment, never via untrusted WebUI input.
Runtime binaries are BUNDLE_DIR/bin, not a shared global /system path.

All mutations share a bounded lock at TS_DIR/run/control.lock. Activation and
migration use that same lock. Controller stop must not deadlock waiting for a
supervisor that is waiting for the controller lock. Background processes must
not inherit and indefinitely hold the controller lock. Supervisor singleton
ownership is separate from the mutation lock. Verify PID, executable/script
identity and process start time before terminating processes or reclaiming locks.
No basename kill, global route flush, or foreign firewall cleanup.

The controller performs initial daemon/component startup while holding the
mutation lock, then hands off supervision after readiness is determined. It
must not wait for a supervisor that needs that lock to perform startup. All
background children close the inherited mutation-lock descriptor. Add start/stop
concurrency and activation-start lock regression tests. Helpers invoked under
an already-held lock use an explicit internal call contract; the WebUI never
controls the lock-held environment.

Build per-architecture files/bundle-ARCH.sha256 manifests over installed common
files and selected bin paths. Installer extracts the selected manifest as
MODPATH/bundle.sha256. Activation validates the complete manifest and rejects
symlinks, unsafe paths, and undeclared executable/runtime files before copying
only declared files into a generation. Never execute a candidate before verifying it.

## Commands and State

Public fixed command surface:
enable, disable, toggle, start, stop, restart, status, status-json, logs,
web-restart, diagnostics, migration-status, migrate-legacy, apply-staged.
Only fixed actions reach the shell; no arbitrary command/path fields in WebUI.

- Stop/disable use ownership records and known directories even with bad config.
- start is idempotent and bounded; enable records intent but does not mask a
  start failure as an intentional user disable.
- Supervision recovers owned process crashes with bounded backoff and visible
  failure information, not device reboots or continuous full network resets.
- Bad config or missing bundle yields failed/degraded state; status remains usable.
- API/health calls have hard timeouts. Logs are size-bounded and diagnostic
  output redacts authorization URLs, private keys, tokens, and proxy credentials.
- Initialization sets hostname before interactive login, prefers a usable Android
  device name with product/model fallback, and does not overwrite admin naming.
- Fresh identity defaults to accept-dns=false, accept-routes=false, no exit node,
  no advertised routes. Imported/upgraded preferences are preserved and warnings
  show effective DNS/routes settings; no silent rewrite of user preferences.
- Proxy is explicit, loopback-only, optional, and never auto-discovers/persists a
  third-party configuration. Do not claim every daemon HTTP operation is control-only.

Health has distinct enabled intent, supervisor/daemon/API, backend login state,
native interface/address/routes, official panel, and optional measured reachability.
Native health never unconditionally returns success. NeedsLogin is not a crash;
expected peer routes are only checked when relevant to logged-in Running state.
The daemon remains the owner of native routes/netfilter. Record missing state
as degraded; do not automatically flush/rebuild foreign networking to hide it.
Explicit userspace mode remains separate; do not silently switch data planes.

## Status Contract

Preserve existing top-level keys: enabled, mode, moduleVersion, tailscaleVersion,
components, tailscale, prefs. Extend with schemaVersion=2, lifecycle,
diagnostics (array of objects with code, severity=info/warning/error, message),
and runtime (activeVersion, stagedVersion, previousVersion all nullable when
metadata is absent). webListen exposes only the validated loopback endpoint;
the full-panel link uses this effective endpoint rather than a hardcoded port.
components supervisor/daemon/dataPlane/web use running/stopped/unknown;
dataPlane running requires mode-specific readiness, not a PID alone.
lifecycle is disabled/stopped/starting/running/degraded/failed/migration-required.
tailscale and prefs are nullable JSON objects; frontend extracts only needed
fields and surfaces tailscale.Health. Unknown is distinct from stopped.
Malformed or timed-out status yields a visible error, not an empty panel.

## Explicit Legacy Migration

Old ID magisk-tailscaled and /data/adb/tailscale stay untouched during install.
If a legacy identity is present and the new identity is absent, report
migration-required instead of automatically starting a duplicate identity.

migrate-legacy is an explicit controller action. Require the old module to be
disabled/removed and prove legacy daemon/supervisor processes are stopped.
If ownership is ambiguous, stop migration with a specific error, without killing
the old process. Never automatically stop or uninstall another module.
Require the new runtime stopped and destination identity absent. Reject symlinks
at migration input/output boundaries; copy state atomically with 0600 permissions,
preserving node identity and embedded preferences. Import only recognized safe
module config fields as data, never source the old shell config. Keep source
files unchanged and record migration completion without secrets. Do not start
the imported node automatically; user enable is a separate action.
Old uninstall must not delete new state because it is in a separate root.
Uninstall stops only this module, defaults to preserving identity for reinstall,
and documents a separate explicit purge operation outside the WebUI allowlist.

## WebUI

Keep compact status, action toggle, Details/WebUI, and full-panel navigation.
Display DNS/admin hostname, IP, engine/module versions, intent, health warnings,
active/staged runtime versions, and diagnostics. UI follows actual outcomes;
all actions have pending/timeout/error states and restore valid enabled controls.
Offer explicit migration and staged-runtime application with confirmation and
specific reasons when prerequisites are unmet. Never expose reboot or a shell.
Official Tailscale web remains loopback-only; its failure does not restart VPN.

## Packaging and Store

Source candidate builds produce universal/arm/arm64 ZIPs. Store publication
selects only the universal ZIP, with root module.prop ID matching the destination
repository kernelsu-tailscaled. metadata module.json has metamodule=false,
summary, sourceUrl, and attribution. Support links use source Issues.
Verify install-time selected payload hashes, bundle content, ZIP modes/path/LF,
version ordering, metadata, and reproducible output. Keep licenses in Vite public.

CI tests build-only branches/PRs; tagged beta candidates remain pre-release.
Prepare store publication behind workflow_dispatch plus protected environment
and explicit destination check. It needs separately supplied scoped credentials
after store approval. Draft -> upload complete universal asset -> verify bytes
and metadata -> publish immutable -> verify store API. No live credentials or
store submission in this milestone. Preserve v1.102.3.1 and its update endpoint
until a deliberate migration release is available; never reuse its tag/assets.

## Acceptance and Test Layers

- Executed shell behavior tests: duplicate/concurrent start, bounded stop,
  invalid config stop, stale/reused PID, timeout, crash recovery/backoff,
  missing native address/routes, login-required, and disabled marker.
- Installer/migration/activation tests in disposable Linux paths with stubbed
  managers/CLI: source unchanged, stopped-source requirement, symlinks rejected,
  no destination overwrite, interrupted install isolation, generation switch,
  version/digest rejection, and same-engine activation rollback.
- Frontend tests for warnings, unknown state, partial data, migration, staged
  activation, clipboard rejection, and action timeout/recovery; browser smoke
  with mocked KernelSU bridge at desktop/mobile sizes before completion.
- Build ZIPs twice in the same toolchain, verify all three; store-gate tests
  check universal selection, matching ID, immutable release, and API download.
- External gates remain pending: device installation and multi-day coexistence,
  real migration of the owner's two identities, store review/credentials/API.
  Local tests cannot be reported as real Android or multi-day proof.
