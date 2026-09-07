# KernelSU-Tailscaled Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development for bounded
> components and independent review; primary agent owns integration and verification.

**Goal:** Implement the approved isolated-ID redesign and prepare official store
distribution without publishing a new stable release. A subsequent owner request
authorizes standard ZIP installation and immediate hot activation on both phones,
with preserved identities and no reboot. The owner also authorized an Actions-built
source prerelease and subsequent store submission. The complete ZIP must handle
activation and manager files; no device-specific post-install repair scripts.

**Architecture:** Thin KernelSU hooks select a complete immutable runtime bundle.
One bounded mutation lock coordinates controller, supervisor, activation, and
migration. TypeScript consumes a versioned health/status contract; Python builds
and verifies manager-installable packages and distribution gates.

**Tech Stack:** POSIX/BusyBox shell, official Tailscale binaries, TypeScript,
Vite/Vitest, Python unittest/zipfile, GitHub Actions, WSL Linux test harness.

## Task 1: Spec Review and Identity Contract

- [ ] Review spec and plan for ownership, lock order, migration, release gates.
- [ ] Change module metadata to kernelsu-tailscaled / KernelSU-Tailscaled /
  2.0.0-beta.5 / 20000005; preserve existing v1 published assets and main endpoint.
- [ ] Add central metadata module.json and update source references on feature branch.
- [ ] Verify no packaged old module-path hardcoding except explicit migration paths.

## Task 2: Executable Runtime Contracts

Files: tailscale/scripts/*, tailscale/config/module.conf,
tests/test_runtime_static.py, tests/runtime/*, tests/test_runtime_behavior.py.

- [ ] Add failing executed tests for truthful native health, bad-config stop,
  bounded CLI, serialized controls, supervisor ownership, and log redaction.
- [ ] Implement runtime changes against spec's BUNDLE_DIR/MODDIR/TS_DIR interface.
- [ ] Keep API schemaVersion=2 and compatibility keys; do not copy private state
  into diagnostics. Preserve fresh/imported preference distinction.
- [ ] Run WSL shell tests and Python wrapper. Add failure fixtures before fixes.
- [ ] Review spec compliance, then code quality; fix and commit runtime changes.

## Task 3: Isolated Installation, Migration, Activation

Files: customize.sh, uninstall.sh, service.sh, action.sh, control.sh,
scripts/activate-runtime.sh, scripts/migrate-legacy.sh,
tests/test_install_lifecycle.py and shell fixtures.

- [ ] Write failing staging/migration tests with disposable source/destination,
  fake CLI/process identities, malformed config, and symlink attacks.
- [ ] Install bins into MODPATH/bin with manifest validation; never overwrite
  live persistent binaries during manager installation.
- [ ] Implement bounded same-lock generation activation and fixed staged candidate.
- [ ] Implement explicit copy-only migration, legacy stopped proof, no overwrite,
  root-only state and idempotent migration status. Preserve old files.
- [ ] Bootstrap disabled/first-run/staged states without automatic legacy takeover.
- [ ] Test boot-only manager promotion reconciliation, equal-version digest
  rejection, and hot activation followed by manager promotion without downgrade.
- [ ] Test rollback/rejection and uninstall state retention; review and commit.

## Task 4: Status and Actions WebUI

Files: webroot-src/src/{api,model,render,main,styles}*, fixtures, webroot build.

- [ ] Extend model tests first with schemaVersion 2, warnings, unknown state,
  active/staged versions, migration-required, and nullable upstream JSON.
- [ ] Implement fixed control.sh action bridge and bounded operations.
- [ ] Keep current ergonomic commands; expose diagnostics and confirmed explicit
  migration/apply actions. Restore buttons on failure and handle clipboard errors.
- [ ] npm ci; npm run typecheck; npm test; npm run build.
- [ ] Playwright mocked-bridge desktop/mobile screenshots and behavior tests;
  source review before generated build commit. Real device checks follow the
  separately authorized standard ZIP install and hot activation.

## Task 5: Verified Universal Store Distribution

Files: scripts/build_release.py, scripts/verify-package.py,
scripts/store-release.py, tests/test_{package,release_builder,store_release}.py,
.github/workflows/*, update.json, module.json, README.md, CHANGELOG.txt.

- [ ] Test new identity, candidate version, installer required files, manifests,
  architecture payloads, licenses, deterministic bytes, and installed bundle hash.
- [ ] Store-gate tests reject wrong repo/ID, non-immutable release, wrong asset,
  and metadata mismatch. Store upload picks one universal ZIP only.
- [ ] Build/test CI on feature branches; v2 beta tags never publish stable by default.
- [ ] Prepare explicit protected manual store publish with preconditions and
  separately supplied scoped credential; no live store publish in this milestone.
- [ ] Explain standard install, explicit migration, hot runtime vs staged WebUI,
  compatibility limits, state retention and rollback boundaries.

## Task 6: Integration and Verification

- [ ] Run Python suite, WSL runtime/installer suite, ShellCheck, frontend types,
  unit/browser tests, and two full release builds with SHA comparison.
- [ ] Verify all ZIPs, metadata, licenses, LF, permissions, no private state.
- [ ] Obtain independent spec and code review; resolve material findings.
- [ ] Commit/push feature branch; run cloud build-only CI and verify artifacts.
- [ ] Update these task statuses and final candidate verification record once.
- [ ] Install the verified ZIP through ksud on both current ADB transports;
  explicitly stop/disable old Tailscale, migrate retained login, hot activate v2,
  and verify node identity/access. Do not reboot or alter ZeroTier/routers.
- [ ] Keep the old stable release and store untouched. Record unexecuted
  full manager promotion, userspace, soak and store gates as pending, not passed.
