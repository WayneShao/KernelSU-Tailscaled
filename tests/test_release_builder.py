import hashlib
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_release.py"
VERIFIER = ROOT / "scripts" / "verify-package.py"


class ReleaseBuilderTests(unittest.TestCase):
    def make_source(self, root: Path) -> None:
        files = {
            "module.prop": b"id=kernelsu-tailscaled\nname=KernelSU-Tailscaled\nversion=1.2.3.4\nversionCode=01020304\nauthor=test\ndescription=test\n",
            "module.json": b'{"metamodule":false,"sourceUrl":"https://github.com/WayneShao/KernelSU-Tailscaled"}\n',
            "update-kernelsu.json": b"{}\n",
            "control.sh": b"#!/system/bin/sh\nexit 0\n",
            "scripts/bundle-lib.sh": b"#!/system/bin/sh\nexit 0\n",
            "scripts/runtime-control.sh": b"#!/system/bin/sh\nexit 0\n",
            "scripts/install-runtime.sh": b"#!/system/bin/sh\nexit 0\n",
            "scripts/activate-runtime.sh": b"#!/system/bin/sh\nexit 0\n",
            "scripts/migrate-legacy.sh": b"#!/system/bin/sh\nexit 0\n",
            "customize.sh": b"#!/system/bin/sh\nexit 0\n",
            "service.sh": b"#!/system/bin/sh\nexit 0\n",
            "action.sh": b"#!/system/bin/sh\nexit 0\n",
            "uninstall.sh": b"#!/system/bin/sh\nexit 0\n",
            "skip_mount": b"\n",
            "LICENSE": b"test license\n",
            "NOTICE": b"test notice\n",
            "update.json": b"{}\n",
            "META-INF/com/google/android/update-binary": b"#!/sbin/sh\nexit 0\n",
            "META-INF/com/google/android/updater-script": b"#MAGISK\n",
            "webroot/index.html": b"<!doctype html><title>Tailscale</title>\n",
            "webroot/licenses/Apache-2.0.txt": b"Apache License 2.0 fixture\n",
            "webroot/licenses/Lucide.txt": b"Lucide license fixture\n",
            "tailscale/config/module.conf": b"MODE=native\n",
            "tailscale/scripts/tailscale-service": b"#!/system/bin/sh\nexit 0\n",
            "files/VERSION.txt": b"v1.2.3\n",
            "files/tailscale-arm": b"arm-cli",
            "files/tailscaled-arm": b"arm-daemon",
            "files/hev-socks5-tunnel-linux-arm": b"arm-tunnel",
            "files/tailscale-arm64": b"arm64-cli",
            "files/tailscaled-arm64": b"arm64-daemon",
            "files/hev-socks5-tunnel-linux-arm64": b"arm64-tunnel",
        }
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

    def build(self, source: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--source",
                str(source),
                "--output",
                str(output),
                "--use-existing-binaries",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_builds_verified_reproducible_architecture_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            source = temp / "source"
            first = temp / "first"
            second = temp / "second"
            self.make_source(source)
            customize_before = (source / "customize.sh").read_bytes()

            first_result = self.build(source, first)
            second_result = self.build(source, second)

            self.assertEqual(0, first_result.returncode, first_result.stderr)
            self.assertEqual(0, second_result.returncode, second_result.stderr)
            expected = {
                "KernelSU-Tailscaled-v1.2.3.4.zip": "all",
                "KernelSU-Tailscaled-arm-v1.2.3.4.zip": "arm",
                "KernelSU-Tailscaled-arm64-v1.2.3.4.zip": "arm64",
            }
            self.assertEqual(expected.keys(), {path.name for path in first.glob("*.zip")})
            for name, arch in expected.items():
                first_zip = first / name
                second_zip = second / name
                self.assertEqual(
                    hashlib.sha256(first_zip.read_bytes()).digest(),
                    hashlib.sha256(second_zip.read_bytes()).digest(),
                )
                verified = subprocess.run(
                    [sys.executable, str(VERIFIER), "--zip", str(first_zip), "--arch", arch],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(0, verified.returncode, verified.stderr)
                with zipfile.ZipFile(first_zip) as archive:
                    names = set(archive.namelist())
                    self.assertIn("META-INF/com/google/android/update-binary", names)
                    architectures = ('arm', 'arm64') if arch == 'all' else (arch,)
                    for selected in architectures:
                        manifest = dict(line.split('  ', 1)[::-1] for line in archive.read(f'files/bundle-{selected}.sha256').decode().splitlines())
                        self.assertEqual(hashlib.sha256(archive.read(f'files/tailscale-{selected}')).hexdigest(), manifest['bin/tailscale'])
                        self.assertIn('control.sh', manifest)
                        self.assertIn('scripts/activate-runtime.sh', manifest)
                        self.assertNotIn('bundle.sha256', manifest)
                        self.assertEqual(hashlib.sha256(archive.read('module.prop')).hexdigest(), manifest['module.prop'])
                    update_binary_mode = (
                        archive.getinfo("META-INF/com/google/android/update-binary").external_attr >> 16
                    ) & 0o777
                    self.assertEqual(0o755, update_binary_mode)
                    if arch != "all":
                        other = "arm64" if arch == "arm" else "arm"
                        self.assertNotIn(f"files/tailscale-{other}", names)
            self.assertEqual(customize_before, (source / "customize.sh").read_bytes())


if __name__ == "__main__":
    unittest.main()
