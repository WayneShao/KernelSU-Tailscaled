import hashlib
import os
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hot-finalize.sh"


@unittest.skipUnless(shutil.which("sh"), "POSIX shell required")
class HotFinalizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.mod = root / "modules/kernelsu-tailscaled"
        self.state = root / "state"
        self.current = self.state / "releases/current"
        self.staged = root / "modules_update/kernelsu-tailscaled"
        for path in (self.mod / "webroot", self.current / "webroot", self.current / "bin", self.staged / "webroot", self.state / "run"):
            path.mkdir(parents=True, exist_ok=True)
        for directory in (self.mod, self.current, self.staged):
            (directory / "module.prop").write_text("id=kernelsu-tailscaled\nversion=2.0.4\nversionCode=20000010\ndescription=test\n")
            for name in ("control.sh", "action.sh", "service.sh", "uninstall.sh"):
                (directory / name).write_text(name)
            (directory / "webroot/index.html").write_text("web")
        cli = self.current / "bin/tailscale"
        cli.write_text("#!/bin/sh\nexit 0\n")
        cli.chmod(0o755)
        digest = hashlib.sha256((self.current / "webroot/index.html").read_bytes()).hexdigest()
        manifest = f"{digest}  webroot/index.html\n"
        (self.current / "bundle.sha256").write_text(manifest)
        (self.staged / "bundle.sha256").write_text(manifest)
        (self.mod / "update").touch()
        (self.state / "run/wanted").write_text("1\n")
        (self.state / "run/lifecycle").write_text("running\n")
        self.sock = socket.socket(socket.AF_UNIX)
        self.sock.bind(str(self.state / "run/tailscaled.sock"))

    def tearDown(self):
        self.sock.close()
        self.temp.cleanup()

    def run_finalize(self):
        env = os.environ | {
            "MODDIR": str(self.mod), "TS_DIR": str(self.state),
            "KST_STAGED_DIR": str(self.staged), "BUNDLE_DIR": str(self.current),
        }
        return subprocess.run(["sh", str(SCRIPT)], env=env, capture_output=True, text=True)

    def test_matching_healthy_hot_install_clears_pending_update(self):
        self.assertEqual(0, self.run_finalize().returncode)
        self.assertFalse((self.mod / "update").exists())
        self.assertFalse(self.staged.exists())

    def test_mismatched_manager_view_preserves_pending_update(self):
        (self.mod / "webroot/index.html").write_text("different")
        self.assertEqual(0, self.run_finalize().returncode)
        self.assertTrue((self.mod / "update").exists())
        self.assertTrue(self.staged.exists())

    def test_unhealthy_runtime_preserves_pending_update(self):
        (self.state / "run/lifecycle").write_text("failed\n")
        self.assertEqual(0, self.run_finalize().returncode)
        self.assertTrue((self.mod / "update").exists())
        self.assertTrue(self.staged.exists())


if __name__ == "__main__":
    unittest.main()
