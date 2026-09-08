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

## Release And Verification

- Current stable version: `2.0.0`
- Source release: https://github.com/WayneShao/KernelSU-Tailscaled/releases/tag/v2.0.0
- Universal ARM/ARM64 ZIP: https://github.com/WayneShao/KernelSU-Tailscaled/releases/download/v2.0.0/KernelSU-Tailscaled-v2.0.0.zip
- Build job: https://github.com/WayneShao/KernelSU-Tailscaled/actions/runs/34179076192/job/101914259478
- Publication verification: https://github.com/WayneShao/KernelSU-Tailscaled/actions/runs/34179419831
- Release record: https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/docs/releases/v2.0.0.md
- Runtime verification: https://github.com/WayneShao/KernelSU-Tailscaled/blob/main/docs/verification/2026-09-07-beta.5.md

Version 2.0.0 promotes the beta.5 runtime, installer, and WebUI without changes
to that code. The beta.5 ARM64 package was installed through ksud on PKX110 and
nezha with runtime components and the Tailscale backend running afterward.
The verification record preserves the limits on physical WebUI inspection,
broader compatibility, and multi-day observation; the stable classification
does not add unperformed device verification claims.

Only the `kernelsu-tailscaled` module line is maintained. The unused v1 Release
and update channel are retired. Existing v2 installations upgrade normally;
retained data under the old module ID uses a one-time manual migration procedure.

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
