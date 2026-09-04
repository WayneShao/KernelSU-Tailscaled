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
    return [ROOT / line for line in result.stdout.splitlines() if line]


def shell_sources() -> list[Path]:
    roots = [
        ROOT / "customize.sh",
        ROOT / "service.sh",
        ROOT / "action.sh",
        ROOT / "uninstall.sh",
    ]
    roots.extend((ROOT / "tailscale" / "scripts").glob("*"))
    roots.extend((ROOT / "system" / "bin").glob("*"))
    return [path for path in roots if path.is_file()]


class RuntimeStaticTests(unittest.TestCase):
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
