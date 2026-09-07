import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from tests import test_release_builder


ROOT = Path(__file__).resolve().parents[1]
HOOKS = ("control.sh", "action.sh", "service.sh", "uninstall.sh", "module.prop")
SERVICE = r'''#!/bin/sh
. "$BUNDLE_DIR/tailscale/scripts/common.sh"
fixture_command() {
  printf '%s:%s\n' "$(sed -n 's/^versionCode=//p' "$BUNDLE_DIR/module.prop")" "$1" >> "$TRACE"
  case "$1" in
    start|enable)
      [ ! -f "$MODDIR/disable" ] && [ ! -f "$MODDIR/remove" ] || return 41
      [ ! -f "$BUNDLE_DIR/fail-start" ] || return 42
      printf '1\n' > "$RUN_DIR/wanted"
      touch "$RUN_DIR/fake-running"
      ;;
    stop|disable)
      printf '0\n' > "$RUN_DIR/wanted"
      rm -f "$RUN_DIR/fake-running"
      ;;
    toggle)
      if [ -f "$RUN_DIR/fake-running" ]; then fixture_command stop; else fixture_command start; fi
      ;;
    status-json) printf '{"schemaVersion":2}\n' ;;
  esac
}
with_control_lock fixture_command "$1"
'''


@unittest.skipUnless(os.name == "posix", "Execute under Linux/WSL for POSIX installer behavior")
class CompleteInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kst-complete-install-")
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.source = self.base / "source"
        self.builder = test_release_builder.ReleaseBuilderTests()
        self.builder.make_source(self.source)
        for name in ("control.sh", "customize.sh", "service.sh", "action.sh", "uninstall.sh", "module.prop"):
            shutil.copyfile(ROOT / name, self.source / name)
        for name in ("scripts", "tailscale", "webroot"):
            shutil.copytree(ROOT / name, self.source / name, dirs_exist_ok=True)
        (self.source / "tailscale/scripts/tailscale-service").write_text(SERVICE)
        (self.source / "files/VERSION.txt").write_text("1.102.3\n")
        for arch in ("arm", "arm64"):
            for name in ("tailscale", "tailscaled", "hev-socks5-tunnel-linux"):
                (self.source / f"files/{name}-{arch}").write_text("#!/bin/sh\nprintf '1.102.3\\n'\n")
        self.archive = self.build("first")

    def build(self, name):
        output = self.base / name
        built = self.builder.build(self.source, output)
        self.assertEqual(0, built.returncode, built.stdout + built.stderr)
        return next(output.glob("KernelSU-Tailscaled-v*.zip"))

    def device(self, name):
        base = self.base / name
        active = base / "modules/kernelsu-tailscaled"
        active.mkdir(parents=True)
        (active / "module.prop").write_text("id=kernelsu-tailscaled\n")
        (active / "update").touch()
        commands = base / "commands"
        commands.mkdir()
        # Manager ownership operations are simulated on unprivileged Linux CI.
        if os.geteuid() != 0:
            (commands / "chown").write_text("#!/bin/sh\nexit 0\n")
            (commands / "chown").chmod(0o755)
        return dict(os.environ, KST_ACTIVE_DIR=str(active), MODDIR=str(active),
                    TS_DIR=str(base / "state"), KST_LEGACY_DIR=str(base / "legacy"),
                    KST_LEGACY_MODULE=str(base / "modules/magisk-tailscaled"),
                    MODPATH=str(base / "modules_update/kernelsu-tailscaled"),
                    KST_STAGED_DIR=str(base / "modules_update/kernelsu-tailscaled"),
                    TRACE=str(base / "trace"), BOOTMODE="true", ARCH="arm64",
                    KST_LOCK_TIMEOUT="2", PATH=str(commands) + ":" + os.environ["PATH"])

    def install(self, env, archive=None, ok=True):
        archive = archive or self.archive
        staging = Path(env["MODPATH"])
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(archive) as package:
            (staging / "customize.sh").write_bytes(package.read("customize.sh"))
        harness = r'''
abort() { echo "$*" >&2; exit 1; }
ui_print() { echo "$*"; }
set_perm() { chmod "$4" "$1"; }
set_perm_recursive() {
  find "$1" -type d -exec chmod "$4" {} \;
  find "$1" -type f -exec chmod "$5" {} \;
}
. "$MODPATH/customize.sh"
# KernelSU retains only its active placeholder and does not promote staged files.
rm -f "$MODPATH/customize.sh" "$KST_ACTIVE_DIR/disable" "$KST_ACTIVE_DIR/remove"
cp -f "$MODPATH/module.prop" "$KST_ACTIVE_DIR/module.prop"
touch "$KST_ACTIVE_DIR/update"
'''
        result = subprocess.run(["sh", "-c", harness], env=dict(env, ZIPFILE=str(archive)),
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(ok, result.returncode == 0, result.stdout + result.stderr)
        return result

    def presentation(self, env):
        active = Path(env["KST_ACTIVE_DIR"])
        files = [active / name for name in HOOKS]
        files.extend(file for file in (active / "webroot").rglob("*") if file.is_file())
        return {file.relative_to(active).as_posix(): hashlib.sha256(file.read_bytes()).hexdigest()
                for file in files if file.exists()}

    def assert_usable(self, env):
        active = Path(env["KST_ACTIVE_DIR"])
        current = (Path(env["TS_DIR"]) / "current").resolve()
        self.assertEqual(Path(env["TS_DIR"]) / "releases", current.parent)
        self.assertEqual(0o755, active.stat().st_mode & 0o777)
        self.assertEqual(0o755, (active / "webroot").stat().st_mode & 0o777)
        if os.geteuid() == 0:
            self.assertEqual((0, 0), (active.stat().st_uid, active.stat().st_gid))
            for file in active.rglob("*"):
                self.assertEqual((0, 0), (file.stat().st_uid, file.stat().st_gid))
        self.assertTrue((Path(env["TS_DIR"]) / "run/fake-running").is_file())
        self.assertFalse((active / "scripts").exists(), "Manager publication must remain thin")
        with zipfile.ZipFile(self.archive) as package:
            for name in package.namelist():
                if name in HOOKS or name.startswith("webroot/"):
                    self.assertEqual(package.read(name), (active / name).read_bytes(), name)
        for name in HOOKS:
            self.assertEqual(0o644 if name == "module.prop" else 0o755,
                             (active / name).stat().st_mode & 0o777)
        for file in (active / "webroot").rglob("*"):
            self.assertEqual(0o755 if file.is_dir() else 0o644, file.stat().st_mode & 0o777)
        status = subprocess.run(["sh", str(active / "control.sh"), "status-json"], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, status.returncode, status.stdout + status.stderr)
        self.assertEqual(2, json.loads(status.stdout)["schemaVersion"])
        action = subprocess.run(["sh", str(active / "action.sh")], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(0, action.returncode, action.stdout + action.stderr)
        self.assertFalse((Path(env["TS_DIR"]) / "run/fake-running").exists())

    def test_same_zip_completes_two_independent_fresh_installs(self):
        first = self.device("device-a")
        second = self.device("device-b")
        archive_hash = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        for env in (first, second):
            self.install(env)
            self.assert_usable(env)
            self.assertFalse((Path(env["MODPATH"]) / "customize.sh").exists())
        self.assertEqual(self.presentation(first), self.presentation(second))
        self.assertEqual((Path(first["TS_DIR"]) / "current").resolve().name,
                         (Path(second["TS_DIR"]) / "current").resolve().name)
        self.assertEqual(archive_hash, hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_reinstall_starts_identical_generation_and_preserves_identity_config(self):
        env = self.device("existing")
        state = Path(env["TS_DIR"])
        (state / "config").mkdir(parents=True)
        identity = b'{"fixture":"already-migrated-identity"}\n'
        config = b"MODE=userspace\nDEVICE_HOSTNAME=unchanged\n"
        (state / "tailscaled.state").write_bytes(identity)
        (state / "config/module.conf").write_bytes(config)
        (state / "migration-awaiting-enable").touch()
        legacy = Path(env["KST_LEGACY_DIR"])
        legacy.mkdir()
        (legacy / "tailscaled.state").write_bytes(b"legacy identity must not replace the selected identity")
        self.install(env)
        before = (state / "current").resolve()
        (state / "run/fake-running").unlink()
        active = Path(env["KST_ACTIVE_DIR"])
        (active / "webroot/obsolete.js").write_text("stale asset")
        (active / "disable").touch()
        (active / "remove").touch()
        self.install(env)
        self.assertEqual(before, (state / "current").resolve())
        self.assertTrue((state / "run/fake-running").exists())
        self.assertEqual(identity, (state / "tailscaled.state").read_bytes())
        self.assertEqual(config, (state / "config/module.conf").read_bytes())
        self.assertFalse((state / "migration-awaiting-enable").exists())
        self.assertFalse((active / "disable").exists())
        self.assertFalse((active / "remove").exists())
        self.assertFalse((active / "webroot/obsolete.js").exists())

    def test_legacy_identity_and_pending_migration_install_ui_without_legacy_commands(self):
        for blocked in ("legacy", "pending"):
            with self.subTest(blocked=blocked):
                env = self.device(blocked)
                legacy = Path(env["KST_LEGACY_DIR"])
                legacy.mkdir()
                old = Path(env["KST_LEGACY_MODULE"])
                old.mkdir()
                (old / "control.sh").write_text('#!/bin/sh\ntouch "$TRACE.legacy"\n')
                original = b'{"fixture":"legacy-identity"}\n'
                if blocked == "legacy":
                    (legacy / "tailscaled.state").write_bytes(original)
                else:
                    (Path(env["TS_DIR"]) / "migration.pending").mkdir(parents=True)
                self.install(env)
                state = Path(env["TS_DIR"])
                self.assertTrue((state / "current").is_symlink())
                self.assertTrue((Path(env["KST_ACTIVE_DIR"]) / "webroot/index.html").is_file())
                self.assertFalse((state / "run/fake-running").exists())
                self.assertFalse((state / "tailscaled.state").exists())
                self.assertFalse(Path(env["TRACE"] + ".legacy").exists())
                self.assertFalse((old / "disable").exists())
                self.assertFalse((old / "remove").exists())
                if blocked == "legacy":
                    self.assertEqual(original, (legacy / "tailscaled.state").read_bytes())

    def test_tampered_zip_preserves_active_presentation_and_runtime(self):
        env = self.device("tamper")
        self.install(env)
        before = self.presentation(env)
        current = (Path(env["TS_DIR"]) / "current").resolve()
        trace = Path(env["TRACE"]).read_bytes()
        tampered = self.base / "tampered.zip"
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(tampered, "w") as target:
            for info in source.infolist():
                data = source.read(info)
                if info.filename == "webroot/index.html":
                    data += b"tampered"
                target.writestr(info, data)
        self.install(env, tampered, ok=False)
        self.assertEqual(before, self.presentation(env))
        self.assertEqual(current, (Path(env["TS_DIR"]) / "current").resolve())
        self.assertEqual(trace, Path(env["TRACE"]).read_bytes())

    def test_webroot_prepare_failure_preserves_active_presentation_and_runtime(self):
        env = self.device("copy-failure")
        self.install(env)
        before = self.presentation(env)
        trace = Path(env["TRACE"]).read_bytes()
        command = Path(env["KST_ACTIVE_DIR"]).parents[1] / "commands/cp"
        command.write_text('#!/bin/sh\ncase "$*" in *webroot*) exit 47;; esac\nexec /bin/cp "$@"\n')
        command.chmod(0o755)
        self.install(env, ok=False)
        self.assertEqual(before, self.presentation(env))
        self.assertEqual(trace, Path(env["TRACE"]).read_bytes())

    def test_same_engine_failed_start_restores_runtime_and_preserves_presentation(self):
        env = self.device("rollback")
        self.install(env)
        state = Path(env["TS_DIR"])
        before = self.presentation(env)
        current = (state / "current").resolve()
        metadata = self.source / "module.prop"
        metadata.write_text(re.sub(r"(?m)^versionCode=(\d+)$",
                                   lambda match: f"versionCode={int(match[1]) + 1}",
                                   metadata.read_text()))
        service = self.source / "tailscale/scripts/tailscale-service"
        service.write_text(SERVICE.replace('[ ! -f "$BUNDLE_DIR/fail-start" ] || return 42', 'return 42'))
        update = self.build("failed-update")
        self.install(env, update, ok=False)
        self.assertEqual(current, (state / "current").resolve())
        self.assertEqual(before, self.presentation(env))
        self.assertTrue((state / "run/fake-running").is_file())
        self.assertTrue((state / "run/activation-failure").is_file())

    @unittest.skipUnless(shutil.which("mksh") and shutil.which("busybox"), "Requires mksh and BusyBox")
    def test_complete_install_under_mksh_and_busybox_preserves_control_lock(self):
        env = self.device("android-shell")
        commands = Path(env["KST_ACTIVE_DIR"]).parents[1] / "commands"
        (commands / "sh").symlink_to(shutil.which("mksh"))
        # Ubuntu BusyBox omits flock; retain its real awk/mv and use host flock.
        busybox = commands / "busybox"
        busybox.write_text('#!/bin/sh\nif [ "$1" = flock ]; then shift; exec flock "$@"; fi\n'
                           f'exec "{shutil.which("busybox")}" "$@"\n')
        busybox.chmod(0o755)
        env["KST_BUSYBOX"] = str(busybox)
        self.install(env)
        self.assert_usable(env)


if __name__ == "__main__":
    unittest.main()
