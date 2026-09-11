#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import PurePosixPath
from pathlib import Path


REQUIRED_ENTRIES = {
    "META-INF/com/google/android/update-binary",
    "META-INF/com/google/android/updater-script",
    "module.prop",
    "module.json",
    "control.sh",
    "scripts/bundle-lib.sh",
    "scripts/runtime-control.sh",
    "scripts/install-runtime.sh",
    "scripts/activate-runtime.sh",
    "scripts/migrate-legacy.sh",
    "scripts/status-summary.sh",
    "scripts/hot-finalize.sh",
    "customize.sh",
    "service.sh",
    "uninstall.sh",
    "webroot/index.html",
    "webroot/licenses/Apache-2.0.txt",
    "webroot/licenses/Lucide.txt",
    "tailscale/config/module.conf",
    "tailscale/scripts/tailscale-service",
    "files/manifest.sha256",
    "files/VERSION.txt",
}
TEXT_SUFFIXES = {
    ".conf",
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".prop",
    ".sh",
    ".ts",
    ".txt",
    ".yaml",
    ".yml",
}
SHA256_LINE = re.compile(r"^([0-9a-f]{64})  ([^\r\n]+)$")


class VerificationError(ValueError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify a KernelSU-Tailscaled module ZIP")
    parser.add_argument("--zip", dest="archive", required=True, type=Path)
    parser.add_argument("--arch", required=True, choices=("all", "arm", "arm64"))
    return parser.parse_args()


def fail(message: str) -> None:
    raise VerificationError(message)


def validate_path(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or not path.parts
        or "\\" in name
        or "//" in name
        or path.as_posix() != name
        or name.startswith("/")
        or ":" in path.parts[0]
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        fail(f"unsafe ZIP path: {name}")


def unix_mode(info: zipfile.ZipInfo) -> int:
    return (info.external_attr >> 16) & 0xFFFF


def is_executable_path(name: str) -> bool:
    return (
        name in {"customize.sh", "service.sh", "action.sh", "uninstall.sh", "control.sh"}
        or name.startswith("scripts/") and name.endswith(".sh")
        or name == "META-INF/com/google/android/update-binary"
        or name.startswith("tailscale/scripts/")
        or name.startswith("system/bin/")
        or name.startswith("files/tailscale-")
        or name.startswith("files/tailscaled-")
        or name.startswith("files/hev-socks5-tunnel-")
    )


def is_text_path(name: str) -> bool:
    path = PurePosixPath(name)
    return path.suffix.lower() in TEXT_SUFFIXES or name.startswith("tailscale/scripts/") or name in {"LICENSE", "NOTICE", "skip_mount", "META-INF/com/google/android/update-binary", "META-INF/com/google/android/updater-script"}


def parse_module_prop(content: bytes) -> dict[str, str]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        fail(f"module.prop is not UTF-8: {error}")
    properties: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            fail(f"invalid module.prop line: {line}")
        key, value = line.split("=", 1)
        properties[key] = value
    for key in ("id", "name", "version", "versionCode", "author", "description"):
        if not properties.get(key):
            fail(f"missing module.prop field: {key}")
    if properties["id"] != "kernelsu-tailscaled":
        fail(f"unexpected module id: {properties['id']}")
    if not properties["versionCode"].isdigit() or not 0 < int(properties["versionCode"]) <= 2147483647:
        fail("module versionCode is not an integer")
    return properties


def validate_bundles(archive: zipfile.ZipFile, names: set[str], arch: str) -> None:
    for selected in (('arm', 'arm64') if arch == 'all' else (arch,)):
        name = f'files/bundle-{selected}.sha256'
        if name not in names:
            fail(f'missing installed bundle manifest: {selected}')
        installed = {path: archive.read(path) for path in names if not path.startswith(('META-INF/', 'files/')) and not path.endswith('/') and path != 'customize.sh'}
        installed['engine-version'] = archive.read('files/VERSION.txt')
        installed['bin/tailscale'] = archive.read(f'files/tailscale-{selected}')
        installed['bin/tailscaled'] = archive.read(f'files/tailscaled-{selected}')
        helper = f'files/hev-socks5-tunnel-linux-{selected}'
        if helper in names:
            installed['bin/hev-socks5-tunnel'] = archive.read(helper)
        expected = ''.join(f'{hashlib.sha256(installed[path]).hexdigest()}  {path}\n' for path in sorted(installed)).encode('ascii')
        if archive.read(name) != expected:
            fail(f'installed bundle manifest mismatch: {selected}')


def validate_architecture(names: set[str], arch: str) -> None:
    expected = {"arm", "arm64"} if arch == "all" else {arch}
    unexpected = {"arm", "arm64"} - expected
    for current in sorted(expected):
        required = {
            f"files/tailscale-{current}",
            f"files/tailscaled-{current}",
        }
        if not required.issubset(names):
            fail(f"missing architecture payload: {current}")
    for current in sorted(unexpected):
        prefixes = (
            f"files/tailscale-{current}",
            f"files/tailscaled-{current}",
            f"files/hev-socks5-tunnel-linux-{current}",
        )
        if any(name in names for name in prefixes):
            fail(f"unexpected architecture payload: {current}")


def validate_manifest(archive: zipfile.ZipFile, names: set[str]) -> None:
    try:
        lines = archive.read("files/manifest.sha256").decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        fail(f"invalid SHA-256 manifest encoding: {error}")
    hashes: dict[str, str] = {}
    for line in lines:
        match = SHA256_LINE.fullmatch(line)
        if not match:
            fail(f"invalid SHA-256 manifest line: {line}")
        digest, name = match.groups()
        validate_path(name)
        if name in hashes:
            fail(f"duplicate SHA-256 manifest entry: {name}")
        hashes[name] = digest

    payloads = {
        name
        for name in names
        if name.startswith("files/") and name != "files/manifest.sha256" and not name.endswith("/")
    }
    missing = sorted(payloads - hashes.keys())
    extra = sorted(hashes.keys() - payloads)
    if missing:
        fail(f"missing SHA-256 manifest entry: {missing[0]}")
    if extra:
        fail(f"unknown SHA-256 manifest entry: {extra[0]}")
    for name in sorted(payloads):
        actual = hashlib.sha256(archive.read(name)).hexdigest()
        if actual != hashes[name]:
            fail(f"SHA-256 mismatch: {name}")


def verify(archive_path: Path, arch: str) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names: set[str] = set()
        for info in infos:
            raw_name = info.orig_filename
            validate_path(raw_name.rstrip("/") or raw_name)
            if info.filename in names:
                fail(f"duplicate ZIP entry: {info.filename}")
            names.add(info.filename)
            mode = unix_mode(info)
            if mode & 0o170000 == 0o120000:
                fail(f"symbolic link is not allowed: {info.filename}")

        for required in sorted(REQUIRED_ENTRIES):
            if required not in names:
                fail(f"missing required entry: {required}")

        for info in infos:
            name = info.filename
            if info.is_dir():
                continue
            content = archive.read(info)
            if is_text_path(name) and b"\r\n" in content:
                fail(f"CRLF text file: {name}")
            if is_executable_path(name) and not unix_mode(info) & 0o111:
                fail(f"entry is not executable: {name}")

        parse_module_prop(archive.read("module.prop"))
        validate_architecture(names, arch)
        validate_manifest(archive, names)
        validate_bundles(archive, names, arch)
        try:
            meta = json.loads(archive.read('module.json'))
            if not isinstance(meta, dict) or meta.get('metamodule') is not False:
                fail('module.json must declare metamodule=false')
        except (ValueError, UnicodeDecodeError) as error:
            fail(f'invalid module.json: {error}')


def main() -> int:
    args = parse_args()
    try:
        verify(args.archive, args.arch)
    except (OSError, VerificationError, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.archive} ({args.arch})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
