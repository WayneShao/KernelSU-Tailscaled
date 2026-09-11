import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Execute under Linux/WSL for POSIX lifecycle behavior")
class InstallLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kst-install-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.module = self.base / "modules/kernelsu-tailscaled"
        self.staged = self.base / "modules_update/kernelsu-tailscaled"
        self.state = self.base / "state"
        self.legacy = self.base / "legacy"
        self.old_module = self.base / "modules/magisk-tailscaled"
        self.trace = self.base / "trace"
        self.make_bundle(self.module, 20000001)
        self.env = dict(os.environ, MODDIR=str(self.module), TS_DIR=str(self.state),
                        KST_STAGED_DIR=str(self.staged), KST_LEGACY_DIR=str(self.legacy),
                        KST_LEGACY_MODULE=str(self.old_module), TRACE=str(self.trace))

    def make_bundle(self, path, code, engine="1.102.3", fail=False):
        path.mkdir(parents=True, exist_ok=True)
        for name in ("control.sh", "scripts/bundle-lib.sh", "scripts/activate-runtime.sh",
                     "scripts/migrate-legacy.sh", "scripts/runtime-control.sh",
                     "scripts/status-summary.sh", "scripts/hot-finalize.sh",
                     "tailscale/scripts/common.sh"):
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        (path / "module.prop").write_text(
            f"id=kernelsu-tailscaled\nversion=2.0.0-beta.{code - 20000000}\nversionCode={code}\n")
        (path / "engine-version").write_text(engine + "\n")
        (path / "tailscale/scripts/tailscale-service").write_text(
            '#!/bin/sh\n'
            'printf "%s:%s\\n" "$(sed -n "s/^versionCode=//p" "$BUNDLE_DIR/module.prop")" "$1" >> "$TRACE"\n'
            'case "$1" in\n'
            'start|enable) ' + ('exit 19' if fail else 'mkdir -p "$TS_DIR/run"; echo 1 > "$TS_DIR/run/wanted"; touch "$TS_DIR/run/fake-running"') + ';;\n'
            'stop|disable) echo 0 > "$TS_DIR/run/wanted"; rm -f "$TS_DIR/run/fake-running";;\n'
            'status-json) printf \'{"schemaVersion":2}\\n\';;\n'
            'esac\n')
        (path / "bin").mkdir(exist_ok=True)
        for binary in ("tailscale", "tailscaled"):
            (path / f"bin/{binary}").write_text("#!/bin/sh\nexit 0\n")
        for file in path.rglob("*"):
            if file.is_file():
                file.chmod(0o755 if file.suffix == ".sh" or "scripts" in file.parts or "bin" in file.parts else 0o644)
        self.manifest(path)

    def manifest(self, path):
        files = sorted(file for file in path.rglob("*") if file.is_file() and file.name != "bundle.sha256")
        (path / "bundle.sha256").write_text("".join(
            f"{hashlib.sha256(file.read_bytes()).hexdigest()}  {file.relative_to(path).as_posix()}\n"
            for file in files))

    def run_control(self, action, ok=True, entry=None):
        result = subprocess.run(["sh", str((entry or self.module) / "control.sh"), action], env=self.env,
                                text=True, capture_output=True, timeout=20)
        if ok:
            self.assertEqual(0, result.returncode, result.stderr + result.stdout)
        else:
            self.assertNotEqual(0, result.returncode, result.stderr + result.stdout)
        return result

    def active(self):
        return (self.state / "current").resolve()

    def legacy_identity(self):
        self.legacy.mkdir()
        (self.legacy / "tailscaled.state").write_text('{"fixture":"identity"}\n')
        self.old_module.mkdir(parents=True)
        (self.old_module / "disable").touch()

    def test_first_boot_creates_complete_private_generation(self):
        self.run_control("boot")
        self.assertEqual(self.state / "releases", self.active().parent)
        self.assertTrue((self.active() / "bin/tailscaled").is_file())
        self.assertTrue((self.active() / "control.sh").is_file())
        self.assertEqual(0o700, self.state.stat().st_mode & 0o777)

    def test_boot_from_installed_active_view_uses_verified_current(self):
        self.run_control("boot")
        before = self.active()
        (self.module / "bundle.sha256").unlink()
        for directory in ("scripts", "tailscale", "bin"):
            shutil.rmtree(self.module / directory)
        self.run_control("boot")
        self.assertEqual(before, self.active())

    def test_first_install_staged_entry_works_with_manager_placeholder(self):
        self.make_bundle(self.staged, 20000001)
        shutil.rmtree(self.module)
        self.module.mkdir()
        shutil.copyfile(self.staged / "module.prop", self.module / "module.prop")
        (self.module / "update").touch()
        self.run_control("status-json", entry=self.staged)
        self.run_control("disable", entry=self.staged)
        self.run_control("enable", entry=self.staged)
        self.assertTrue((self.active() / "bin/tailscaled").exists())
        self.assertTrue((self.state / "run/fake-running").exists())

    def test_hash_failure_does_not_select_candidate(self):
        (self.module / "bin/tailscaled").write_text("tampered")
        self.run_control("boot", ok=False)
        self.assertFalse((self.state / "current").exists())

    def test_symlink_payload_rejected(self):
        binary = self.module / "bin/tailscaled"
        binary.unlink()
        binary.symlink_to(self.module / "bin/tailscale")
        self.run_control("boot", ok=False)

    def test_undeclared_executable_rejected(self):
        (self.module / "bin/injected").write_text("extra")
        self.run_control("boot", ok=False)

    def test_manager_disable_is_respected(self):
        (self.module / "disable").touch()
        self.run_control("boot")
        self.assertFalse(self.trace.exists())

    def test_hot_apply_preserves_enabled_intent_and_manager_cannot_downgrade(self):
        self.run_control("boot")
        before = self.active()
        self.make_bundle(self.staged, 20000002)
        self.run_control("apply-staged")
        after = self.active()
        self.assertNotEqual(before, after)
        self.assertEqual(before, (self.state / "previous").resolve())
        self.run_control("boot")
        self.assertEqual(after, self.active())
        self.assertIn("20000002:start", self.trace.read_text())

    def test_normal_manager_upgrade_selects_new_generation(self):
        self.run_control("boot")
        self.make_bundle(self.module, 20000002)
        (self.module / "update").touch()
        self.run_control("boot")
        self.assertIn("versionCode=20000002", (self.active() / "module.prop").read_text())

    def test_equal_version_different_content_rejected(self):
        self.run_control("boot")
        before = self.active()
        (self.module / "engine-version").write_text("1.102.4\n")
        self.manifest(self.module)
        (self.module / "update").touch()
        self.run_control("boot", ok=False)
        self.assertEqual(before, self.active())

    def test_engine_downgrade_rejected_before_stop(self):
        self.run_control("boot")
        before = self.trace.read_text()
        self.make_bundle(self.staged, 20000002, engine="1.100.0")
        self.run_control("apply-staged", ok=False)
        self.assertEqual(before, self.trace.read_text())

    def test_hot_runtime_uses_selected_controller_not_manager_controller(self):
        self.run_control("boot")
        self.make_bundle(self.staged, 20000002)
        implementation = self.staged / "scripts/runtime-control.sh"
        implementation.write_text(implementation.read_text().replace(
            'kst_dispatch() {', 'kst_dispatch() {\n  printf "selected-controller\\n" >> "$TRACE"'))
        self.manifest(self.staged)
        self.run_control("apply-staged")
        self.run_control("status-json")
        self.assertIn("selected-controller", self.trace.read_text())

    def test_failed_same_engine_activation_rolls_back(self):
        self.run_control("boot")
        before = self.active()
        self.make_bundle(self.staged, 20000002, fail=True)
        self.run_control("apply-staged", ok=False)
        self.assertEqual(before, self.active())
        self.assertTrue((self.state / "run/activation-failure").exists())

    def test_failed_same_engine_manager_boot_rolls_back(self):
        self.run_control("boot")
        before = self.active()
        self.make_bundle(self.module, 20000002, fail=True)
        (self.module / "update").touch()
        self.run_control("boot", ok=False)
        self.assertEqual(before, self.active())
        self.assertTrue((self.state / "run/activation-failure").exists())

    def test_legacy_identity_blocks_automatic_start(self):
        self.legacy_identity()
        self.run_control("boot", ok=False)
        self.assertFalse(self.trace.exists())

    def test_migration_copies_without_deleting_or_starting(self):
        self.legacy_identity()
        original = (self.legacy / "tailscaled.state").read_bytes()
        self.run_control("migrate-legacy")
        self.assertEqual(original, (self.state / "tailscaled.state").read_bytes())
        self.assertEqual(original, (self.legacy / "tailscaled.state").read_bytes())
        self.assertEqual(0o600, (self.state / "tailscaled.state").stat().st_mode & 0o777)
        self.assertFalse(self.trace.exists())
        self.run_control("boot")
        self.assertFalse(self.trace.exists())

    def test_migration_accepts_fully_removed_legacy_module(self):
        self.legacy_identity()
        shutil.rmtree(self.old_module)
        self.run_control("migrate-legacy")
        self.assertTrue((self.state / "tailscaled.state").exists())

    def test_migration_rejects_legacy_watcher_with_exact_root_argument(self):
        self.legacy_identity()
        watcher = subprocess.Popen(["/usr/bin/python3", "-c", "import time; time.sleep(30)",
                                    "inotifyd", "tailscaled.inotify", str(self.old_module)])
        try:
            self.run_control("migrate-legacy", ok=False)
            self.assertFalse((self.state / "tailscaled.state").exists())
        finally:
            watcher.terminate()
            watcher.wait(timeout=5)

    def test_migration_allows_stopped_selected_generation_controller(self):
        self.run_control("boot")
        self.run_control("stop")
        self.legacy_identity()
        self.run_control("migrate-legacy")
        self.assertTrue((self.state / "tailscaled.state").exists())

    def test_migration_cleanup_failure_does_not_block_committed_identity(self):
        self.legacy_identity()
        commands = self.base / "commands"
        commands.mkdir()
        remove = commands / "rm"
        remove.write_text('#!/bin/sh\ncase "$2" in */.migration-complete.*|*/migration.pending) exit 44;; esac\nexec /bin/rm "$@"\n')
        remove.chmod(0o755)
        self.env["PATH"] = str(commands) + ":" + os.environ["PATH"]
        self.run_control("migrate-legacy")
        self.assertTrue((self.state / "tailscaled.state").is_file())
        self.assertFalse((self.state / "migration.pending").exists())

    def test_migration_retries_after_identity_publication_failure(self):
        self.legacy_identity()
        (self.legacy / "config").mkdir()
        (self.legacy / "config/module.conf").write_text("MODE=native\n")
        commands = self.base / "commands"
        commands.mkdir()
        link = commands / "ln"
        link.write_text('#!/bin/sh\ncase "$2" in */tailscaled.state) exit 43;; esac\nexec /bin/ln "$@"\n')
        link.chmod(0o755)
        self.env["PATH"] = str(commands) + ":" + os.environ["PATH"]
        self.run_control("migrate-legacy", ok=False)
        self.assertFalse((self.state / "tailscaled.state").exists())
        self.assertTrue((self.state / "migration.pending").is_dir())
        self.env["PATH"] = os.environ["PATH"]
        self.run_control("migrate-legacy")
        self.assertTrue((self.state / "tailscaled.state").is_file())
        self.assertFalse((self.state / "migration.pending").exists())

    def test_migration_requires_disabled_legacy_module(self):
        self.legacy_identity()
        (self.old_module / "disable").unlink()
        self.run_control("migrate-legacy", ok=False)
        self.assertFalse((self.state / "tailscaled.state").exists())

    def test_migration_does_not_overwrite_new_identity(self):
        self.legacy_identity()
        self.state.mkdir()
        destination = self.state / "tailscaled.state"
        destination.write_text("existing")
        self.run_control("migrate-legacy", ok=False)
        self.assertEqual("existing", destination.read_text())

    def test_migration_never_executes_legacy_configuration(self):
        self.legacy_identity()
        (self.legacy / "config").mkdir()
        sentinel = self.base / "should-not-exist"
        (self.legacy / "config/module.conf").write_text(f"MODE=native\nCONTROL_PROXY=$(touch {sentinel})\n")
        self.run_control("migrate-legacy", ok=False)
        self.assertFalse(sentinel.exists())
        self.assertFalse((self.state / "tailscaled.state").exists())

    def test_migration_rejects_symlink_state(self):
        self.legacy_identity()
        state = self.legacy / "tailscaled.state"
        copy = self.base / "external-state"
        state.rename(copy)
        state.symlink_to(copy)
        self.run_control("migrate-legacy", ok=False)

    def test_migration_rejects_out_of_range_configuration_before_copy(self):
        self.legacy_identity()
        (self.legacy / "config").mkdir()
        (self.legacy / "config/module.conf").write_text("MODE=native\nTAILSCALE_PORT=999999\n")
        self.run_control("migrate-legacy", ok=False)
        self.assertFalse((self.state / "tailscaled.state").exists())

    def test_real_zip_failed_activation_preserves_running_generation_and_view(self):
        from tests.test_release_builder import ReleaseBuilderTests
        self.run_control("boot")
        active_before = self.active()
        view_before = (self.module / "control.sh").read_bytes()
        source = self.base / "source"
        builder = ReleaseBuilderTests()
        builder.make_source(source)
        # Real hooks and runtime scripts; only executable binaries are host fixtures.
        for name in ("control.sh", "customize.sh", "service.sh", "action.sh", "uninstall.sh"):
            shutil.copyfile(ROOT / name, source / name)
        shutil.copytree(ROOT / "scripts", source / "scripts", dirs_exist_ok=True)
        shutil.copytree(ROOT / "tailscale", source / "tailscale", dirs_exist_ok=True)
        (source / "module.prop").write_text((ROOT / "module.prop").read_text())
        (source / "files/VERSION.txt").write_text("1.102.3\n")
        for arch in ("arm", "arm64"):
            for name in ("tailscale", "tailscaled", "hev-socks5-tunnel-linux"):
                (source / f"files/{name}-{arch}").write_text("#!/bin/sh\nexit 0\n")
        result = builder.build(source, self.base / "packages")
        self.assertEqual(0, result.returncode, result.stderr)
        archive = next((self.base / "packages").glob("KernelSU-Tailscaled-v*.zip"))
        self.assertTrue(zipfile.is_zipfile(archive))
        self.staged.mkdir(parents=True)
        harness = self.base / "install.sh"
        harness.write_text('''#!/bin/sh
abort() { echo "$*" >&2; exit 1; }
ui_print() { echo "$*"; }
set_perm() { chmod "$4" "$1"; }
set_perm_recursive() { find "$1" -type d -exec chmod "$4" {} \\;; find "$1" -type f -exec chmod "$5" {} \\;; }
. "$INSTALLER"
rm -f "$MODPATH/customize.sh"
''')
        env = dict(self.env, BOOTMODE="true", ARCH="arm64", ZIPFILE=str(archive),
                   MODPATH=str(self.staged), INSTALLER=str(ROOT / "customize.sh"),
                   KST_ACTIVE_DIR=str(self.module), KST_SHELL="/bin/sh",
                   KST_START_TIMEOUT="2", KST_STOP_TIMEOUT="1", KST_CLI_TIMEOUT="1")
        if os.geteuid() != 0:
            commands = self.base / "manager-commands"
            commands.mkdir()
            (commands / "chown").write_text("#!/bin/sh\nexit 0\n")
            (commands / "chown").chmod(0o755)
            env["PATH"] = str(commands) + ":" + env["PATH"]
        installed = subprocess.run(["sh", str(harness)], env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(0, installed.returncode, installed.stdout + installed.stderr)
        self.assertEqual(active_before, self.active())
        self.assertEqual(view_before, (self.module / "control.sh").read_bytes())
        self.assertTrue((self.state / "run/activation-failure").is_file())


if __name__ == "__main__":
    unittest.main()
