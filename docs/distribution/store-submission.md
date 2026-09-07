## Module

- Module ID: `kernelsu-tailscaled`
- Display name: KernelSU-Tailscaled
- Maintainer: @WayneShao
- Source: https://github.com/WayneShao/KernelSU-Tailscaled
- Support: https://github.com/WayneShao/KernelSU-Tailscaled/issues

An independently maintained, KernelSU-first integration of the official Tailscale
daemon on rooted Android, without occupying Android's VPN slot. It provides a
local status WebUI, access to the official loopback panel, serialized lifecycle
control, isolated login state, and a complete ZIP installer with hot activation.

## Candidate And Verification

- Candidate: `2.0.0-beta.5` (prerelease)
- Source release: https://github.com/WayneShao/KernelSU-Tailscaled/releases/tag/v2.0.0-beta.5
- Universal ARM/ARM64 ZIP: https://github.com/WayneShao/KernelSU-Tailscaled/releases/download/v2.0.0-beta.5/KernelSU-Tailscaled-v2.0.0-beta.5.zip
- Build job: https://github.com/WayneShao/KernelSU-Tailscaled/actions/runs/34106297847/job/101691983943
- Publication workflow: https://github.com/WayneShao/KernelSU-Tailscaled/actions/runs/34107166975
- Verification record: https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/docs/verification/2026-09-07-beta.5.md

The same ARM64 ZIP was installed through ksud on PKX110 and nezha, with runtime
components and the Tailscale backend running afterward. The verification record
distinguishes these results from final physical WebUI inspection, broader
compatibility, and multi-day stability, which are not claimed. This is a request
for manual review of a prerelease project, not a statement that it is stable.

## Provenance And Licensing

This is an independently maintained derivative of `ryukora/Magisk-Tailscaled`.
Fork history and attribution to ryukora and ANASFANANI are retained. It is not an
official Tailscale or KernelSU product. Original BSD-3-Clause licensing and
bundled dependency notices are preserved:

- https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/LICENSE
- https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/NOTICE
- https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/module.json

Requested distribution repository: `KernelSU-Modules-Repo/kernelsu-tailscaled`.
The maintained source remains at `WayneShao/KernelSU-Tailscaled`. After approval,
the distribution repository will publish one universal ZIP in an immutable
release, with public index and download verification performed separately.
