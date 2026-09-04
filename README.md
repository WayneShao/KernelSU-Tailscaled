# Magisk Tailscaled

Run the official static Tailscale daemon on rooted Android without occupying
Android's VPN slot. This fork adds a KernelSU WebUI, native TUN support, owned
process supervision, reproducible release packages, and an explicit userspace
fallback.

## Install

1. Download the package matching the device architecture from
   [Releases](https://github.com/WayneShao/Magisk-Tailscaled/releases/latest).
2. Install the ZIP through KernelSU or Magisk Manager.
3. Reboot once to apply a normal module installation.
4. Open the module Details/WebUI page and use **Open full panel** to sign in.

The Action/Run button toggles the module immediately. The Details page shows
the node name, backend state, Tailscale IP, route and DNS preferences, component
health, and installed versions. It also provides fixed controls for refresh,
copy IP, enable/disable, runtime restart, logs, and the official local panel.

## Runtime

The default configuration uses native TUN:

```text
tailscaled --tun=tailscale0 \
  --state=/data/adb/tailscale/tailscaled.state \
  --socket=/data/adb/tailscale/run/tailscaled.sock \
  --port=41641
```

Persistent state lives under `/data/adb/tailscale`. Upgrades preserve the node
identity, preferences, `module.conf`, and logs. Processes are stopped only
after their PID and `/proc/<pid>/cmdline` identity match the module-owned
executable.

The local official panel listens only on `127.0.0.1:8088`. It is opened by
navigating the KernelSU WebView rather than embedding or proxying it.

## Configuration

The persistent configuration is `/data/adb/tailscale/config/module.conf`:

```ini
MODE=native
TUN_NAME=tailscale0
TAILSCALE_PORT=41641
WEB_LISTEN=127.0.0.1:8088
SOCKS_LISTEN=127.0.0.1:1055
CONTROL_PROXY=
DEVICE_HOSTNAME=
SUPERVISOR_INTERVAL=5
RESTART_BACKOFF_MAX=60
```

Set `MODE=userspace` only when native TUN is unavailable. `CONTROL_PROXY` may
point to a loopback HTTP or SOCKS5 proxy, for example
`http://127.0.0.1:7890`, when Android's DNS returns Fake-IP addresses that are
not reachable by root processes. This affects the Tailscale control-plane HTTP
connection, not WireGuard peer traffic.

`DEVICE_HOSTNAME` is optional. When empty, a new node initializes its explicit
Tailscale hostname once from Android's `ro.product.name`. An existing explicit
hostname is preserved. The dashboard prefers the backend-provided DNS name so
renaming a machine in the Tailscale admin console is reflected in the UI.

## Service Commands

```text
/data/adb/modules/magisk-tailscaled/tailscale/scripts/tailscale-service \
  {enable|disable|toggle|start|stop|restart|status|status-json|logs|web-restart}
```

These commands operate only on this module's processes. The WebUI invokes a
fixed allowlist and does not accept arbitrary commands or paths.

## Development

```bash
python -m unittest discover -s tests -v
cd webroot-src
npm ci
npm run typecheck
npm test
npm run build
cd ..
sh scripts/build-release.sh --use-existing-binaries --output dist
```

WebUI files can be replaced in the active module and reloaded without an
Android reboot. Runtime scripts can be replaced and applied with a module
service restart. Normal public updates remain signed-off ZIP installations.

## Packages

Each release contains full, arm-only, and arm64-only ZIP files. Every archive
has normalized ordering and timestamps, Unix executable modes, and a
`files/manifest.sha256` covering its binary payload. CI rebuilds and verifies
all packages before publishing a tag release.

## Credits And License

- [Tailscale](https://github.com/tailscale/tailscale) for `tailscale` and
  `tailscaled`.
- [KernelSU](https://github.com/tiann/KernelSU) for root management and its
  module WebUI bridge.
- [hev-socks5-tunnel](https://github.com/heiher/hev-socks5-tunnel) for the
  userspace fallback tunnel.
- [ryukora/Magisk-Tailscaled](https://github.com/ryukora/Magisk-Tailscaled)
  and prior contributors for the upstream module history.

See [LICENSE](LICENSE), [NOTICE](NOTICE), and the license texts bundled under
`webroot/licenses`.
