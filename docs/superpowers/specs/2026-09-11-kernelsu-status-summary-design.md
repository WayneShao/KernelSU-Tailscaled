# KernelSU Status Summary and Pending Update Controls

## Goal

Expose the most useful Tailscale health information in the KernelSU module list
description, while keeping service control, update application, and detailed
inspection available as separate actions when an update is staged or pending a
reboot.

## Status Summary

The runtime writes only the `description=` line in the active module metadata
and, when present, the KernelSU update staging metadata. All other module
fields remain unchanged. The summary is bounded and generated from the same
status model used by `status-json`:

`[time | state] Tailscale(version) | IPv4 | UI/update marker`

State values are running, degraded, stopped, failed, update pending reboot,
and migration required. IPv4 is shown only when valid; otherwise the summary
uses `not ready`. The UI marker means the local WebUI is available, not that an
external Tailscale admin panel is authenticated.

Updates use a temporary file and atomic replacement. Description refresh is
best effort and must never prevent daemon startup, stopping, recovery, or
module installation. Events that may refresh it are install completion,
service state transitions, supervisor health transitions, and explicit status
refreshes. Repeated identical summaries are not rewritten.

## WebUI Controls

The dashboard keeps three independent areas:

- Runtime control: enable/disable, refresh, and service restart.
- Update control: current runtime, staged runtime, and apply-staged action.
- Details: logs, diagnostics, migration status, and the official local panel.

When an update is staged or the module files are pending reboot, runtime and
details controls remain available. Applying a staged runtime is explicitly
labelled as a runtime switch and does not reboot Android. A module-file update
that still needs reboot is displayed separately from the currently running
service state.

## Error Handling

Malformed or unavailable status falls back to the fixed base description. A
failed description write is logged but does not change the command exit code.
Descriptions are sanitized for control characters and bounded to a length that
fits the KernelSU list layout.

## Verification

- Shell tests cover field preservation, atomic replacement, bounded output,
  duplicate-write suppression, and fallback behavior.
- WebUI tests cover runtime/update/details controls with staged updates and
  pending-reboot status.
- Browser tests cover running, stopped, degraded, failed, migration-required,
  and update-pending states.
- Package tests verify the dynamic updater does not invalidate module metadata
  or the immutable runtime manifest.
