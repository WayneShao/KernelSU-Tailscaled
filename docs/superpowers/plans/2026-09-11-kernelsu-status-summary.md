# KernelSU Status Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show live Tailscale health in the KernelSU module list and keep runtime, update, and details actions available during staged updates.

**Architecture:** Add a small shell status-summary writer that atomically updates only `description=` in active and staged module metadata. Extend the existing status model and renderer so runtime controls, update controls, and details remain separate when `stagedVersion` or pending-reboot diagnostics exist.

**Tech Stack:** POSIX shell on Android, TypeScript, Vite, Vitest, Playwright, Python unittest.

---

### Task 1: Dynamic module description

**Files:**
- Create: `scripts/status-summary.sh`
- Modify: `scripts/runtime-control.sh`, `scripts/install-runtime.sh`, `scripts/bundle-lib.sh`
- Test: `tests/test_status_summary.py`, `tests/test_runtime_static.py`

- [ ] Add failing shell tests for state formatting, field preservation, atomic replacement, bounded output, and fallback.
- [ ] Implement `kst_update_description` with sanitized bounded fields and temporary-file replacement; make failures non-fatal.
- [ ] Invoke it after install and runtime state transitions without adding a global service hook.
- [ ] Add the script to bundle required files and manifest generation.
- [ ] Run the focused tests and full Python unittest suite.

### Task 2: WebUI pending-update controls

**Files:**
- Modify: `webroot-src/src/model.ts`, `webroot-src/src/render.ts`, `webroot-src/src/main.ts`, `webroot-src/src/styles.css`
- Test: `webroot-src/src/main.test.ts`, `webroot-src/browser/dashboard.spec.ts`

- [ ] Add a fixture/test asserting staged updates keep runtime and details actions enabled.
- [ ] Render separate runtime and update-control sections, including pending-reboot wording.
- [ ] Keep `open-panel`, logs, diagnostics, and migration actions available unless their specific preconditions block them.
- [ ] Run typecheck, unit tests, and browser tests; rebuild committed `webroot`.

### Task 3: Package and release validation

**Files:**
- Modify: `tests/test_package.py`, `README.md`, `CHANGELOG.txt`
- Create: `docs/releases/v2.0.2.md`

- [ ] Add package assertions for the new script and dynamic-description behavior.
- [ ] Bump version to `2.0.2` only after implementation tests pass.
- [ ] Build and verify universal, ARM, and ARM64 packages reproducibly.
- [ ] Run all repository tests and shell checks.
- [ ] Commit, push, create the tag, wait for Actions, publish source and KernelSU distribution releases, and sync only required distribution metadata.
