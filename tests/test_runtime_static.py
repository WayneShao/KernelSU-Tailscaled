import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [
        ROOT / line
        for line in result.stdout.splitlines()
        if line and (ROOT / line).is_file()
    ]


def shell_sources() -> list[Path]:
    roots = [
        ROOT / "customize.sh",
        ROOT / "service.sh",
        ROOT / "action.sh",
        ROOT / "uninstall.sh",
        ROOT / "control.sh",
    ]
    roots.extend(path for path in (ROOT / "tailscale" / "scripts").glob("*") if path.suffix != '.awk')
    roots.extend((ROOT / "scripts").glob("*.sh"))
    roots.extend((ROOT / "system" / "bin").glob("*"))
    return [path for path in roots if path.is_file()]


class RuntimeStaticTests(unittest.TestCase):
    def test_runtime_layout_is_complete(self) -> None:
        required = {
            "action.sh",
            "skip_mount",
            "tailscale/config/module.conf",
            "tailscale/scripts/common.sh",
            "tailscale/scripts/tailscale-daemon",
            "tailscale/scripts/tailscale-service",
            "tailscale/scripts/tailscale-supervisor",
            "tailscale/scripts/tailscale-tunnel",
            "tailscale/scripts/tailscale-web",
        }
        missing = sorted(name for name in required if not (ROOT / name).is_file())
        self.assertEqual([], missing, f"missing runtime files: {missing}")

    def test_default_configuration_is_native_and_loopback_only(self) -> None:
        config = (ROOT / "tailscale/config/module.conf").read_text(encoding="utf-8")
        self.assertIn("MODE=native\n", config)
        self.assertIn("TUN_NAME=tailscale0\n", config)
        self.assertIn("TAILSCALE_PORT=41641\n", config)
        self.assertIn("WEB_LISTEN=127.0.0.1:8088\n", config)
        self.assertIn("SOCKS_LISTEN=127.0.0.1:1055\n", config)

    def test_common_helpers_validate_owned_processes(self) -> None:
        source = (ROOT / "tailscale/scripts/common.sh").read_text(encoding="utf-8")
        for function in (
            "log()",
            "read_pid()",
            "pid_matches()",
            "stop_owned()",
            "socket_ready()",
            "tcp_ready()",
            "load_config()",
            "module_disabled()",
        ):
            self.assertIn(function, source)
        self.assertIn("/proc/$pid/cmdline", source)
        self.assertNotIn("eval ", source)

    def test_service_command_surface_is_fixed(self) -> None:
        source = (ROOT / "tailscale/scripts/tailscale-service").read_text(
            encoding="utf-8"
        )
        for command in (
            "enable)",
            "disable)",
            "toggle)",
            "start)",
            "stop)",
            "restart)",
            "status)",
            "status-json)",
            "logs)",
            "web-restart)",
        ):
            self.assertIn(command, source)
        self.assertNotIn("eval ", source)

    def test_action_button_delegates_to_toggle(self) -> None:
        source = (ROOT / "action.sh").read_text(encoding="utf-8")
        self.assertIn('MODDIR=${0%/*}', source)
        self.assertIn('"$MODDIR/control.sh" toggle', source)

    def test_boot_service_respects_disable_marker(self) -> None:
        source = (ROOT / "service.sh").read_text(encoding="utf-8")
        self.assertIn('MODDIR=${0%/*}', source)
        self.assertIn('"$MODDIR/disable"', source)
        self.assertIn('"$MODDIR/control.sh" boot', source)

    def test_installer_validates_bundle_and_delegates_complete_install(self) -> None:
        source = (ROOT / "customize.sh").read_text(encoding="utf-8")
        self.assertIn('"$MODPATH/bin/tailscale"', source)
        self.assertIn('"$MODPATH/bin/tailscaled"', source)
        self.assertIn('"$MODPATH/bundle.sha256"', source)
        self.assertIn('kst_verify_bundle "$MODPATH"', source)
        self.assertIn('scripts/install-runtime.sh', source)
        self.assertNotIn('/data/adb/tailscale', source)
        self.assertNotIn('> "$STATE_FILE"', source)
        self.assertNotIn('rm -rf "$TS_DIR"', source)

    def test_official_web_is_bound_to_loopback(self) -> None:
        source = (ROOT / "tailscale/scripts/tailscale-web").read_text(encoding="utf-8")
        self.assertIn('web --listen="$WEB_LISTEN"', source)
        self.assertIn('WEB_LISTEN=127.0.0.1:8088', (ROOT / "tailscale/config/module.conf").read_text(encoding="utf-8"))

    def test_control_proxy_is_explicit_and_optional(self) -> None:
        config = (ROOT / "tailscale/config/module.conf").read_text(encoding="utf-8")
        daemon = (ROOT / "tailscale/scripts/tailscale-daemon").read_text(encoding="utf-8")
        self.assertIn("CONTROL_PROXY=\n", config)
        self.assertIn('HTTPS_PROXY="$CONTROL_PROXY"', daemon)
        self.assertIn('NO_PROXY="127.0.0.1,localhost"', daemon)

    def test_fresh_hostname_prefers_device_name_and_preserves_existing_state(self) -> None:
        config = (ROOT / "tailscale/config/module.conf").read_text(encoding="utf-8")
        daemon = (ROOT / "tailscale/scripts/tailscale-daemon").read_text(encoding="utf-8")
        self.assertIn("DEVICE_HOSTNAME=\n", config)
        self.assertIn('HOSTNAME_MARKER="$TS_DIR/hostname.initialized"', daemon)
        self.assertIn("initialize_hostname()", daemon)
        self.assertIn("getprop ro.product.name", daemon)
        self.assertIn('set --hostname="$hostname"', daemon)
        self.assertIn('settings get global device_name', daemon)
        self.assertIn('[ -f "$FRESH_MARKER" ] || return 0', daemon)
        self.assertIn('--accept-dns=false --accept-routes=false', daemon)

    def test_legacy_runtime_files_are_removed(self) -> None:
        legacy = {
            "tailscale/settings.ini",
            "tailscale/scripts/start.sh",
            "tailscale/scripts/tailscaled.inotify",
            "tailscale/scripts/tailscaled.service",
            "tailscale/scripts/tailscaled.tun",
            "tailscale/scripts/tailscaled.tun.down",
            "tailscale/scripts/tailscaled.tun.up",
            "system/bin/tailscaled.tun",
        }
        present = sorted(name for name in legacy if (ROOT / name).exists())
        self.assertEqual([], present, f"legacy runtime files: {present}")

    def test_shell_and_config_files_use_lf(self) -> None:
        checked_suffixes = {".sh", ".ini", ".conf", ".yaml", ".yml"}
        offenders = []
        for path in repository_files():
            if path.suffix.lower() in checked_suffixes and b"\r\n" in path.read_bytes():
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders, f"CRLF files: {offenders}")

    def test_runtime_never_terminates_processes_by_basename(self) -> None:
        pattern = re.compile(r"\b(?:pidof|pkill|killall)\b")
        offenders = []
        for path in shell_sources():
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders, f"broad process matching: {offenders}")

    def test_module_does_not_install_global_service_hooks(self) -> None:
        pattern = re.compile(r"/data/adb/(?:ksu/)?service\.d")
        offenders = []
        for path in shell_sources():
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders, f"global service hooks: {offenders}")

    def test_runtime_does_not_depend_on_system_overlay_wrappers(self) -> None:
        pattern = re.compile(r"/system/bin/tailscale(?:d)?(?:\s|$)")
        offenders = []
        for path in shell_sources():
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], offenders, f"system overlay dependency: {offenders}")


if __name__ == "__main__":
    unittest.main()
