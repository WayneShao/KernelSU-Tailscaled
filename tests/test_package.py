import hashlib
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "scripts" / "verify-package.py"


def with_manifest(entries: dict[str, bytes]) -> dict[str, bytes]:
    result = dict(entries)
    lines = []
    for name in sorted(path for path in entries if path.startswith("files/")):
        digest = hashlib.sha256(entries[name]).hexdigest()
        lines.append(f"{digest}  {name}")
    result["files/manifest.sha256"] = ("\n".join(lines) + "\n").encode()
    return result


def good_entries() -> dict[str, bytes]:
    return with_manifest(
        {
            "module.prop": (
                b"id=magisk-tailscaled\n"
                b"name=Magisk Tailscaled\n"
                b"version=1.102.3.1\n"
                b"versionCode=011020301\n"
                b"author=test\n"
                b"description=test fixture\n"
            ),
            "customize.sh": b"#!/system/bin/sh\nexit 0\n",
            "service.sh": b"#!/system/bin/sh\nexit 0\n",
            "uninstall.sh": b"#!/system/bin/sh\nexit 0\n",
            "webroot/index.html": b"<!doctype html><title>Tailscale</title>\n",
            "tailscale/config/module.conf": b"MODE=native\n",
            "tailscale/scripts/tailscale-service": b"#!/system/bin/sh\nexit 0\n",
            "files/tailscale-arm": b"arm-cli",
            "files/tailscaled-arm": b"arm-daemon",
            "files/tailscale-arm64": b"arm64-cli",
            "files/tailscaled-arm64": b"arm64-daemon",
            "files/VERSION.txt": b"v1.102.3\n",
        }
    )


def write_zip(path: Path, entries: dict[str, bytes]) -> None:
    executable = {
        "customize.sh",
        "service.sh",
        "uninstall.sh",
        "tailscale/scripts/tailscale-service",
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            mode = 0o755 if name in executable or name.startswith("files/tailscale") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            archive.writestr(info, content)


def entries_for_arch(arch: str) -> dict[str, bytes]:
    entries = good_entries()
    other = "arm64" if arch == "arm" else "arm"
    entries.pop(f"files/tailscale-{other}")
    entries.pop(f"files/tailscaled-{other}")
    entries.pop("files/manifest.sha256")
    return with_manifest(entries)


class PackageVerifierTests(unittest.TestCase):
    def run_verifier(self, archive: Path, arch: str = "all") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--zip", str(archive), "--arch", arch],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    def test_accepts_valid_full_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "module.zip"
            write_zip(archive, good_entries())

            result = self.run_verifier(archive)

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(f"OK: {archive} (all)\n", result.stdout)

    def assert_rejected(
        self,
        entries: dict[str, bytes],
        expected_error: str,
        arch: str = "all",
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "module.zip"
            write_zip(archive, entries)

            result = self.run_verifier(archive, arch)

            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn(expected_error, result.stderr)

    def test_rejects_parent_path(self) -> None:
        entries = good_entries()
        entries["../escape"] = b"bad"
        self.assert_rejected(entries, "unsafe ZIP path")

    def test_rejects_backslash_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "module.zip"
            entries = good_entries()
            entries["webroot/escape.js"] = b"bad"
            write_zip(archive_path, entries)
            raw = archive_path.read_bytes().replace(
                b"webroot/escape.js", b"webroot\\escape.js"
            )
            archive_path.write_bytes(raw)

            result = self.run_verifier(archive_path)

            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("unsafe ZIP path", result.stderr)

    def test_rejects_duplicate_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "module.zip"
            write_zip(archive_path, good_entries())
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(archive_path, "a") as archive:
                    archive.writestr("module.prop", b"id=other\n")

            result = self.run_verifier(archive_path)

            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("duplicate ZIP entry", result.stderr)

    def test_rejects_missing_module_metadata(self) -> None:
        entries = good_entries()
        entries.pop("module.prop")
        self.assert_rejected(entries, "missing required entry: module.prop")

    def test_rejects_invalid_module_id(self) -> None:
        entries = good_entries()
        entries["module.prop"] = entries["module.prop"].replace(
            b"id=magisk-tailscaled", b"id=wrong-module"
        )
        self.assert_rejected(entries, "unexpected module id")

    def test_rejects_missing_webui_entry(self) -> None:
        entries = good_entries()
        entries.pop("webroot/index.html")
        self.assert_rejected(entries, "missing required entry: webroot/index.html")

    def test_rejects_crlf_shell_script(self) -> None:
        entries = good_entries()
        entries["service.sh"] = b"#!/system/bin/sh\r\nexit 0\r\n"
        self.assert_rejected(entries, "CRLF text file: service.sh")

    def test_rejects_non_executable_shell_script(self) -> None:
        entries = good_entries()
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "module.zip"
            write_zip(archive_path, entries)
            rewritten = Path(temp_dir) / "rewritten.zip"
            with zipfile.ZipFile(archive_path) as source, zipfile.ZipFile(rewritten, "w") as target:
                for source_info in source.infolist():
                    info = zipfile.ZipInfo(source_info.filename)
                    info.create_system = 3
                    mode = 0o644 if source_info.filename == "service.sh" else (
                        source_info.external_attr >> 16
                    ) & 0o7777
                    info.external_attr = (0o100000 | mode) << 16
                    target.writestr(info, source.read(source_info))

            result = self.run_verifier(rewritten)

            self.assertNotEqual(0, result.returncode, result.stdout)
            self.assertIn("entry is not executable: service.sh", result.stderr)

    def test_rejects_missing_manifest(self) -> None:
        entries = good_entries()
        entries.pop("files/manifest.sha256")
        self.assert_rejected(entries, "missing required entry: files/manifest.sha256")

    def test_rejects_manifest_hash_mismatch(self) -> None:
        entries = good_entries()
        entries["files/tailscale-arm64"] = b"modified"
        self.assert_rejected(entries, "SHA-256 mismatch: files/tailscale-arm64")

    def test_rejects_full_package_missing_architecture(self) -> None:
        self.assert_rejected(
            entries_for_arch("arm64"),
            "missing architecture payload: arm",
        )

    def test_accepts_matching_architecture_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = Path(temp_dir) / "module-arm64.zip"
            write_zip(archive, entries_for_arch("arm64"))

            result = self.run_verifier(archive, "arm64")

            self.assertEqual(0, result.returncode, result.stderr)

    def test_rejects_other_architecture_in_specific_package(self) -> None:
        self.assert_rejected(
            good_entries(),
            "unexpected architecture payload: arm",
            arch="arm64",
        )


if __name__ == "__main__":
    unittest.main()
