# WebUI engine updates

User scope: combine the Android native routing fix and in-module Tailscale engine
updates in the next Release, after user testing. No interim public beta.

The module remains an adapter around official binaries. Store downloaded pairs
under the private state root's engines directory; never overwrite immutable
module/runtime generations. Select an engine through an atomic pointer. Preserve
identity and configuration across engine updates and module upgrades.

WebUI offers check, download/verify, then apply. Check uses the official stable
package metadata. Downloads are constrained to the official HTTPS package host,
the device architecture, and a validated semantic version. Verify the official
archive checksum, extract only the two named regular-file members, and execute
bounded version checks before exposing an apply action.

Download failures leave the current runtime untouched. Apply uses the existing
controller lock, stops only owned services, snapshots identity state while stopped,
switches the engine pointer, and checks backend health against the previous
logged-in state. Failure stops the candidate and restores identity and selection
before starting the previous engine. Persist an interrupted-transaction journal
so a killed UI callback is recoverable on the next startup. Preserve disabled or
intentionally stopped services.

Only fixed action names cross the WebUI shell bridge; no user-provided URL or
shell argument is accepted. Network operations have bounded time and size. A
missing HTTPS-verifying downloader produces an actionable error, never a TLS
verification bypass. Report checksum authenticity accurately: HTTPS official-host
hash verification, not an independent publisher signature.

Validation includes checksum/version/architecture failure, stopped intent,
activation rollback, interrupted recovery, UI command restrictions and pending
state, plus real-device check/download/activation and existing identity checks.
