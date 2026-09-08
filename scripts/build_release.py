#!/usr/bin/env python3
import argparse
import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath


ROOT_FILES = (
    "module.prop",
    "module.json",
    "control.sh",
    "customize.sh",
    "service.sh",
    "action.sh",
    "uninstall.sh",
    "skip_mount",
    "LICENSE",
    "NOTICE",
    "update-kernelsu.json",
    "scripts/bundle-lib.sh",
    "scripts/runtime-control.sh",
    "scripts/install-runtime.sh",
    "scripts/activate-runtime.sh",
    "scripts/migrate-legacy.sh",
)
TREE_DIRS = ("META-INF", "tailscale", "webroot")
TEXT_SUFFIXES = {
    ".conf", ".css", ".html", ".ini", ".js", ".json", ".md",
    ".prop", ".sh", ".ts", ".txt", ".yaml", ".yml",
}
ARCHITECTURES = ("arm", "arm64")
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build deterministic KernelSU-Tailscaled ZIP files")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--use-existing-binaries", action="store_true")
    return parser.parse_args()


def module_version(source: Path) -> str:
    match = re.search(r"^version=(.+)$", (source / "module.prop").read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise ValueError("module.prop has no version")
    return match.group(1).strip()


def normalized_bytes(path: Path, name: str) -> bytes:
    data = path.read_bytes()
    if PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES or name.startswith("tailscale/scripts/") or name in {"LICENSE", "NOTICE", "skip_mount", "META-INF/com/google/android/update-binary", "META-INF/com/google/android/updater-script"}:
        data = data.replace(b"\r\n", b"\n")
    return data


def executable(name: str) -> bool:
    return (
        name in {"customize.sh", "service.sh", "action.sh", "uninstall.sh", "control.sh"}
        or name.startswith("scripts/") and name.endswith(".sh")
        or name == "META-INF/com/google/android/update-binary"
        or name.startswith("tailscale/scripts/")
        or name.startswith("files/tailscale-")
        or name.startswith("files/tailscaled-")
        or name.startswith("files/hev-socks5-tunnel-")
    )


def common_entries(source: Path) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    for name in ROOT_FILES:
        path = source / name
        if path.is_symlink():
            raise ValueError(f"symbolic link is not allowed: {path}")
        if not path.is_file():
            raise FileNotFoundError(f"missing release file: {name}")
        entries[name] = normalized_bytes(path, name)
    for directory in TREE_DIRS:
        root = source / directory
        if not root.is_dir():
            raise FileNotFoundError(f"missing release directory: {directory}")
        for path in sorted(root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"symbolic link is not allowed: {path}")
            if path.is_file():
                name = path.relative_to(source).as_posix()
                entries[name] = normalized_bytes(path, name)
    return entries


def payload_entries(source: Path, architectures: tuple[str, ...]) -> dict[str, bytes]:
    names = ["files/VERSION.txt"]
    for arch in architectures:
        names.extend(
            (
                f"files/tailscale-{arch}",
                f"files/tailscaled-{arch}",
                f"files/hev-socks5-tunnel-linux-{arch}",
            )
        )
    payloads: dict[str, bytes] = {}
    for name in names:
        path = source / name
        if path.is_symlink():
            raise ValueError(f"symbolic link is not allowed: {path}")
        if not path.is_file():
            if name.startswith("files/hev-socks5-tunnel-"):
                continue
            raise FileNotFoundError(f"missing release payload: {name}")
        payloads[name] = normalized_bytes(path, name)
    return payloads


def manifest(payloads: dict[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(payloads[name]).hexdigest()}  {name}\n"
        for name in sorted(payloads)
    ).encode("ascii")


def write_archive(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100755 if executable(name) else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, entries[name], compresslevel=9)


def build(source: Path, output: Path) -> list[Path]:
    source = source.resolve()
    output.mkdir(parents=True, exist_ok=True)
    version = module_version(source)
    common = common_entries(source)
    variants = (
        ("all", ARCHITECTURES, f"KernelSU-Tailscaled-v{version}.zip"),
        ("arm", ("arm",), f"KernelSU-Tailscaled-arm-v{version}.zip"),
        ("arm64", ("arm64",), f"KernelSU-Tailscaled-arm64-v{version}.zip"),
    )
    results = []
    for _, architectures, filename in variants:
        payloads = payload_entries(source, architectures)
        for arch in architectures:
            installed = {name: data for name, data in common.items() if not name.startswith("META-INF/") and name != "customize.sh"}
            installed["engine-version"] = payloads["files/VERSION.txt"]
            installed["bin/tailscale"] = payloads[f"files/tailscale-{arch}"]
            installed["bin/tailscaled"] = payloads[f"files/tailscaled-{arch}"]
            helper = payloads.get(f"files/hev-socks5-tunnel-linux-{arch}")
            if helper is not None:
                installed["bin/hev-socks5-tunnel"] = helper
            payloads[f"files/bundle-{arch}.sha256"] = manifest(installed)
        entries = {**common, **payloads, "files/manifest.sha256": manifest(payloads)}
        archive = output / filename
        write_archive(archive, entries)
        results.append(archive)
    return results


def main() -> int:
    args = parse_args()
    for archive in build(args.source, args.output):
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        print(f"{digest}  {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
