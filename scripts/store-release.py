#!/usr/bin/env python3
"""Validate or publish one verified universal ZIP to the approved store repository."""

import argparse
import base64
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

SOURCE_REPO = "WayneShao/KernelSU-Tailscaled"
STORE_REPO = "KernelSU-Modules-Repo/kernelsu-tailscaled"
ZIP_TYPES = {"application/zip", "application/x-zip-compressed"}


def package_verifier():
    spec = importlib.util.spec_from_file_location("package_verifier", Path(__file__).with_name("verify-package.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(archive: Path, release: dict, destination: str) -> dict:
    if destination != STORE_REPO:
        raise ValueError("Unexpected store destination")
    verifier = package_verifier()
    verifier.verify(archive, "all")
    with zipfile.ZipFile(archive) as package:
        props = verifier.parse_module_prop(package.read("module.prop"))
        meta = json.loads(package.read("module.json"))
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", props["version"]):
        raise ValueError("Store publication requires a tested stable version")
    if meta.get("sourceUrl") != f"https://github.com/{SOURCE_REPO}":
        raise ValueError("Package sourceUrl does not identify this source repository")
    expected_name = f'KernelSU-Tailscaled-v{props["version"]}.zip'
    if archive.name != expected_name:
        raise ValueError("Store requires the universal ZIP, not an architecture-specific asset")
    if release.get("tag_name") != f'v{props["version"]}':
        raise ValueError("Release tag does not match module version")
    if release.get("draft") is not False or release.get("prerelease") is not False or release.get("immutable") is not True:
        raise ValueError("Source release must be published, stable, and immutable")
    matching = [asset for asset in release.get("assets", []) if asset.get("name") == expected_name]
    if len(matching) != 1:
        raise ValueError("Source release must contain exactly one matching universal ZIP")
    digest = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    if matching[0].get("content_type") not in ZIP_TYPES or matching[0].get("digest") != digest:
        raise ValueError("Source asset MIME type or SHA-256 digest does not match")
    return props


def gh(*arguments: str) -> str:
    result = subprocess.run(["gh", *arguments], text=True, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"GitHub command failed: {result.stderr.strip()}")
    return result.stdout


def api(endpoint: str) -> dict:
    result = json.loads(gh("api", endpoint, "-H", "Accept: application/vnd.github+json"))
    if not isinstance(result, dict):
        raise ValueError("Unexpected GitHub response")
    return result


def verify_uploaded(release: dict, archive: Path, *, published: bool) -> None:
    assets = release.get("assets", [])
    if len(assets) != 1 or assets[0].get("name") != archive.name:
        raise ValueError("Store release must contain exactly one universal ZIP asset")
    expected = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
    if assets[0].get("digest") != expected or assets[0].get("content_type") not in ZIP_TYPES:
        raise ValueError("Uploaded store asset failed MIME or digest verification")
    if release.get("draft") is not (not published):
        raise ValueError("Unexpected store release publication state")
    if published and release.get("immutable") is not True:
        raise ValueError("Published store release is not immutable; investigate before any further publication")


def publish(archive: Path, tag: str, destination: str) -> str:
    source = api(f"repos/{SOURCE_REPO}/releases/tags/{quote(tag, safe='')}")
    validate(archive, source, destination)
    settings = api(f"repos/{destination}/immutable-releases")
    if settings.get("enabled") is not True:
        raise ValueError("Store repository must enable immutable releases before publication")
    metadata = api(f"repos/{destination}/contents/module.json")
    document = json.loads(base64.b64decode(metadata["content"]))
    if document.get("sourceUrl") != f"https://github.com/{SOURCE_REPO}" or document.get("metamodule") is not False:
        raise ValueError("Store default-branch module.json is not configured for this module")
    repository = api(f"repos/{destination}")
    commit = api(f"repos/{destination}/commits/{quote(repository['default_branch'], safe='')}")["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid distribution metadata commit")
    notes = f"Source: https://github.com/{SOURCE_REPO}/releases/tag/{tag}\n\n{source.get('body') or ''}"
    # A failed upload remains a draft for inspection. Never replace tags or assets.
    gh("release", "create", tag, str(archive), "--repo", destination, "--draft",
       "--target", commit, "--title", f"KernelSU-Tailscaled {tag}", "--notes", notes)
    endpoint = f"repos/{destination}/releases/tags/{quote(tag, safe='')}"
    verify_uploaded(api(endpoint), archive, published=False)
    gh("release", "edit", tag, "--repo", destination, "--draft=false", "--latest")
    final = api(endpoint)
    verify_uploaded(final, archive, published=True)
    return final["html_url"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--destination", default=STORE_REPO)
    parser.add_argument("--publish", action="store_true", help="Create and publish a new store release after all gates pass")
    args = parser.parse_args()
    try:
        if args.publish:
            print(publish(args.zip, args.tag, args.destination))
        else:
            release = api(f"repos/{SOURCE_REPO}/releases/tags/{quote(args.tag, safe='')}")
            validate(args.zip, release, args.destination)
            print("Store gates passed; nothing published")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
