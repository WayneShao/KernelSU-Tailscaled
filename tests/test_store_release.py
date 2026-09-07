import copy
import base64
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests.test_package import good_entries, with_bundles, write_zip

ROOT = Path(__file__).resolve().parents[1]


class StoreReleaseTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("store_release", ROOT / "scripts/store-release.py")
        self.store = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.store)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "KernelSU-Tailscaled-v2.0.0.zip"
        entries = good_entries()
        entries["module.prop"] = entries["module.prop"].replace(b"version=1.102.3.1", b"version=2.0.0")
        entries["module.json"] = b'{"metamodule":false,"sourceUrl":"https://github.com/WayneShao/KernelSU-Tailscaled"}\n'
        write_zip(self.path, with_bundles(entries))
        self.release = {
            "tag_name": "v2.0.0", "draft": False, "prerelease": False, "immutable": True,
            "assets": [{"name": self.path.name, "content_type": "application/zip",
                        "digest": "sha256:" + hashlib.sha256(self.path.read_bytes()).hexdigest()}],
        }

    def test_accepts_verified_universal_immutable_source(self):
        result = self.store.validate(self.path, self.release, self.store.STORE_REPO)
        self.assertEqual("2.0.0", result["version"])

    def test_rejects_wrong_destination(self):
        with self.assertRaisesRegex(ValueError, "destination"):
            self.store.validate(self.path, self.release, "WayneShao/KernelSU-Tailscaled")

    def test_rejects_mutable_draft_prerelease_or_wrong_tag(self):
        for key, value in (("immutable", False), ("draft", True), ("prerelease", True), ("tag_name", "v2.0.1")):
            with self.subTest(key=key):
                release = copy.deepcopy(self.release)
                release[key] = value
                with self.assertRaises(ValueError):
                    self.store.validate(self.path, release, self.store.STORE_REPO)

    def test_rejects_wrong_mime_digest_missing_or_duplicate_asset(self):
        for mutation in ("mime", "digest", "missing", "duplicate"):
            with self.subTest(mutation=mutation):
                release = copy.deepcopy(self.release)
                if mutation == "mime":
                    release["assets"][0]["content_type"] = "application/octet-stream"
                elif mutation == "digest":
                    release["assets"][0]["digest"] = "sha256:" + "0" * 64
                elif mutation == "missing":
                    release["assets"] = []
                else:
                    release["assets"] *= 2
                with self.assertRaises(ValueError):
                    self.store.validate(self.path, release, self.store.STORE_REPO)

    def test_beta_cannot_enter_stable_store_pipeline(self):
        entries = good_entries()
        entries["module.prop"] = entries["module.prop"].replace(b"version=1.102.3.1", b"version=2.0.0-beta.1")
        write_zip(self.path, with_bundles(entries))
        with self.assertRaisesRegex(ValueError, "stable"):
            self.store.validate(self.path, self.release, self.store.STORE_REPO)

    def api_response(self, endpoint):
        destination = self.store.STORE_REPO
        if endpoint.startswith(f"repos/{self.store.SOURCE_REPO}/releases/"):
            return self.release
        if endpoint.endswith("/immutable-releases"):
            return {"enabled": True}
        if endpoint.endswith("/contents/module.json"):
            content = {"metamodule": False, "sourceUrl": f"https://github.com/{self.store.SOURCE_REPO}"}
            return {"content": base64.b64encode(json.dumps(content).encode()).decode()}
        if endpoint == f"repos/{destination}":
            return {"default_branch": "main"}
        if endpoint.endswith("/commits/main"):
            return {"sha": "a" * 40}
        release = copy.deepcopy(self.release)
        release["draft"] = not self.published
        release["immutable"] = self.published
        release["html_url"] = "https://github.com/" + destination + "/releases/tag/v2.0.0"
        if self.bad_upload:
            release["assets"][0]["digest"] = "sha256:" + "0" * 64
        return release

    def test_publish_verifies_draft_before_publishing_and_never_replaces_assets(self):
        self.published = False
        self.bad_upload = False
        commands = []

        def gh(*arguments):
            commands.append(arguments)
            if arguments[:2] == ("release", "edit"):
                self.published = True
            return ""

        with patch.object(self.store, "api", side_effect=self.api_response), patch.object(self.store, "gh", side_effect=gh):
            result = self.store.publish(self.path, "v2.0.0", self.store.STORE_REPO)
        self.assertIn("/releases/tag/v2.0.0", result)
        self.assertEqual([("release", "create"), ("release", "edit")], [args[:2] for args in commands])
        self.assertIn("--draft", commands[0])
        self.assertEqual(1, commands[0].count(str(self.path)))
        self.assertFalse(any("--clobber" in args for args in commands))

    def test_bad_upload_stays_draft(self):
        self.published = False
        self.bad_upload = True
        with patch.object(self.store, "api", side_effect=self.api_response), patch.object(self.store, "gh") as command:
            with self.assertRaisesRegex(ValueError, "digest"):
                self.store.publish(self.path, "v2.0.0", self.store.STORE_REPO)
        self.assertEqual(1, command.call_count)
        self.assertEqual(("release", "create"), command.call_args.args[:2])

    def test_immutable_setting_failure_prevents_all_release_writes(self):
        def response(endpoint):
            if endpoint.endswith("/immutable-releases"):
                return {"enabled": False}
            return self.api_response(endpoint)

        with patch.object(self.store, "api", side_effect=response), patch.object(self.store, "gh") as command:
            with self.assertRaisesRegex(ValueError, "enable immutable"):
                self.store.publish(self.path, "v2.0.0", self.store.STORE_REPO)
        command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
