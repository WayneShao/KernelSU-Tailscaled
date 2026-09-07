# KernelSU Store Research and Redesign Constraints

Checked: 2026-09-07. Historical snapshot from the research stage, before approval.
Source repository: https://github.com/WayneShao/KernelSU-Tailscaled
No deployment or publication was performed during that research stage. Later
authorized implementation and delivery are recorded in
[the beta.5 verification record](../verification/2026-09-07-beta.5.md).

## Authoritative Sources

- Submission entry: https://modules.kernelsu.org/submission/
- Submission documentation: https://github.com/KernelSU-Modules-Repo/submission
- Submission implementation at 356939c960b8112f5fd15fbd0bec7bea4cd8f3e2:
  https://github.com/KernelSU-Modules-Repo/submission/blob/356939c960b8112f5fd15fbd0bec7bea4cd8f3e2/index.js
- Module ID validation:
  https://github.com/KernelSU-Modules-Repo/submission/blob/356939c960b8112f5fd15fbd0bec7bea4cd8f3e2/bot.js
- Current example and metadata: https://github.com/KernelSU-Modules-Repo/org.kernelsu.example
- Store validator at bf9d418f6d058a531a056e6d97e4a341de3d9b25:
  https://github.com/KernelSU-Modules-Repo/modules/blob/bf9d418f6d058a531a056e6d97e4a341de3d9b25/scripts/fetch-data.ts
- Store default-download selection:
  https://github.com/KernelSU-Modules-Repo/modules/blob/bf9d418f6d058a531a056e6d97e4a341de3d9b25/src/pages/modules.json.ts
- Official module format: https://kernelsu.org/guide/module.html
- Developer keyring: https://github.com/KernelSU-Modules-Repo/developers
- Example approval: https://github.com/KernelSU-Modules-Repo/submission/issues/51

These are the official KernelSU endpoints, not third-party module directories.
They do not establish the submission requirements of other KernelSU forks.

## Actual Submission Flow

1. Choose the stable module ID before submitting. Name the issue
   `[submission] MODULE_ID` in KernelSU-Modules-Repo/submission.
2. Supply the maintained source, module purpose, provenance, released ZIP,
   supported/tested platforms, and known limitations in the issue body.
   Some of these are review context rather than machine-validated fields.
3. Wait for manual approval. The current handler has an unconditional manual
   review branch; the README's immediate automatic approval description is stale.
4. Approval creates a repository under KernelSU-Modules-Repo and invites the
   submitter as an administrator. Accept the invitation.
5. Populate its default branch and repository metadata, then publish a valid
   immutable release containing the installable module ZIP.
6. Verify the module in the public store API, website, and Manager. A repository
   invitation alone is not proof of listing or a working download.

The source repository can remain under WayneShao. A separate distribution
repository can link to it through sourceUrl. Transfer is a different documented
submission type; it is not required for the new distribution-repository flow.
No approval lead time is promised. Existing pending issues show that approval
is not immediate. No minimum stars/followers requirement was found in the
active submission handler; do not invent one or promise acceptance.

## Validated Store Requirements

| Item | Current rule or documented expectation |
| --- | --- |
| Repository name | Valid module ID; exact match to ZIP module.prop id |
| ID syntax | `^[a-zA-Z][a-zA-Z0-9._-]+$` |
| Reserved IDs | Prefixes com.android, com.google, org.lsposed, io.github.lsposed, org.kernelsu, io.github.kernelsu; IDs containing example also rejected |
| Display name | Distribution repository Description; non-empty is validated |
| Description | README.md on the default branch |
| Support | Repository Website/Homepage points to support, such as source Issues |
| Metadata | module.json with metamodule=false, summary, sourceUrl; additionalAuthors when appropriate |
| Release | Non-draft, immutable, with a ZIP asset |
| ZIP MIME | application/zip or application/x-zip-compressed in the validator |
| ZIP metadata | Root module.prop with id, version, versionCode |
| Version ordering | Integer versionCode, increasing for subsequent releases |
| Release channel | Stable release or pre-release; example says stable is shown by default |
| Changelog | Release body |

Use README/module.json from the current example rather than the old SUMMARY
and APK wording in the submission README. The current validator extracts
version/versionCode from module.prop, not a mandatory tag-name pattern.

The example requires uploads to be the submitter's own module or explicitly
permitted uploads of another developer's module. Describe this as an independently
maintained derivative with substantial changes, preserve upstream attribution,
and let maintainers evaluate the submission. The existing BSD-3-Clause license
permits modification and redistribution subject to its notices and conditions;
it is not a guarantee that the store will approve a submission.

## Release and Signing Implications

- Immutable releases lock the associated tag and assets. Stage all assets in a
  draft, verify them, then publish. Fixes require a new version, not replacing
  published ZIPs or moving tags.
- The validator explicitly filters on release.immutable. Existing personal
  v1.102.3.1 was checked and is immutable=false, so its prior public release
  status alone does not satisfy the store requirements.
- The current list API selects releases[0].releaseAssets[0] as the default
  download; it does not select by Android ABI. Publish one universal module ZIP
  to the distribution repository. Keep per-ABI packages in source releases if
  desired. Do not make checksums or architecture-specific ZIPs the default asset.
- The validator reads metadata from the first ZIP. Keep metadata identical in
  all assets and do not rely on asset order to perform architecture detection.
- Developer X.509 identity issuance exists as a separate project. No certificate
  issuance/signature check was found in the inspected submission and store
  indexing gate. Do not claim that obtaining a developer certificate is a
  prerequisite for this listing flow, or equate it with GitHub release attestation.
- Publishing into a second repository requires an explicitly scoped credential
  or GitHub App for that repository; the source workflow's ordinary GITHUB_TOKEN
  does not implicitly gain cross-repository write access.
- Store verification must check the module API, version, download target, ZIP ID,
  and byte digest after publication, not only a successful Actions job.

## Current Repository Findings

- Renamed the source to WayneShao/KernelSU-Tailscaled and updated local origin.
  Upstream remains ryukora/Magisk-Tailscaled, with history/fork attribution intact.
- Enabled source Issues and set Homepage to that support endpoint.
- Installed module ID remains magisk-tailscaled; installed display name remains
  Magisk Tailscaled. Neither was changed during research.
- Existing source release has arm, arm64, and universal ZIPs. It is retained as-is.
- Current updateJson and package filenames still use the old source name.
  Update them deliberately with the new identity/release design, preserving
  a working old-client update path. Do not rewrite already published packages.
- New module ID is still a decision: retain ID for in-place updates, or use an
  independent ID and explicit migration. A source repository rename is separate.

## Runtime Problems Driving the Redesign

These are source findings, not a new diagnosis of the devices:

- tailscale-tunnel health returns success unconditionally in native mode.
  The dashboard can therefore mark the data plane running when it is not.
- service entrypoints and supervisor restarts have no shared lifecycle lock.
  Concurrent start/stop/update operations need an ownership and serialization rule.
- load_config runs before command dispatch. Invalid network configuration can
  prevent even stop/disable from stopping owned processes.
- CLI status calls have no enforced timeout; frontend work can remain pending.
- WebUI omits Tailscale Health warnings and collapses parser failures to one
  error, hiding actionable distinctions.
- Installer replaces binaries in the shared live runtime directory before the
  manager applies the new module directory. This can mix old scripts and new
  binaries, and separate renames are not a transaction over the whole bundle.
- Uninstall deletes /data/adb/tailscale unconditionally. A renamed module must
  not share this deletion domain with the original module.
- Runtime static tests mostly assert source strings, not lifecycle behavior.
  The 32 existing Python tests passed during research; they do not prove the
  runtime is stable under concurrent operations, failures, or network changes.

## Recommended Design Direction (Pending Approval)

Keep official Tailscale binaries and the current TypeScript/Vite/Lucide UI.
Prefer a focused runtime redesign over cosmetic renaming or a new VPN engine.

- Thin KernelSU lifecycle hooks call one serialized module control path.
- Separate enabled intent, daemon/API state, login state, data-plane state,
  peer reachability, and last diagnostic errors. Unknown is not healthy.
- Stopping owned processes must work even when settings are invalid.
- Use bounded probes, bounded restart backoff, and visible failure state;
  do not silently repair or flush another module's network configuration.
- Use an isolated persistent state directory for an independent module ID;
  provide explicit, single-owner migration preserving Tailscale identity.
- Standard ZIP install, fully staged bundle verification, controlled activation,
  and a retained previous runtime. Validate state-schema compatibility before
  offering a binary downgrade; do not promise arbitrary rollback.
- Native mode remains explicit. Userspace mode stays separately documented
  and tested. No automatic mode, DNS, route, or proxy changes on network events.
- Fresh install defaults to no accepted DNS/subnet routes and no exit node;
  upgrades preserve explicit existing preferences and show actual effective values.
- Keep the compact status page and full-panel navigation; add surfaced Health
  errors, bounded actions, user-triggered diagnostics, and redacted log export.
- Execute lifecycle/failure tests in CI, then validate only the two agreed phones
  after the owner ends the observation period. No device deployment now.
- Separate source build, candidate verification, immutable distribution publish,
  and post-publish store checks. Store submission waits for testable candidates.

The home OpenWrt init-script repair is a separate deployment integration issue,
not proof of a cause in the Android module. Do not conflate the two projects.

## Next Gate

Confirm the new module ID/migration policy and approve the focused design before
implementing the runtime refactor. Do not submit to the official store, publish
new stable artifacts, modify phones/routers, or migrate ZeroTier routes implicitly.
