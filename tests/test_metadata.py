import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetadataTests(unittest.TestCase):
    def test_bundled_tailscale_has_standalone_android_support(self):
        self.assertEqual(
            'v1.104.2',
            (ROOT / 'files/VERSION.txt').read_text(encoding='ascii').strip(),
        )

    def test_current_release_identity(self):
        props = dict(line.split('=', 1) for line in (ROOT / 'module.prop').read_text().splitlines() if '=' in line)
        self.assertEqual('kernelsu-tailscaled', props['id'])
        self.assertEqual('KernelSU-Tailscaled', props['name'])
        self.assertIn('/KernelSU-Tailscaled/', props['updateJson'])
        self.assertNotEqual('update.json', props['updateJson'].rsplit('/', 1)[-1])

    def test_store_metadata_preserves_provenance(self):
        self.assertTrue((ROOT / 'module.json').is_file(), 'Store metadata is missing')
        meta = json.loads((ROOT / 'module.json').read_text())
        self.assertFalse(meta['metamodule'])
        self.assertEqual('https://github.com/WayneShao/KernelSU-Tailscaled', meta['sourceUrl'])
        self.assertTrue(meta['summary'])
        authors = {author['name'] for author in meta['additionalAuthors']}
        self.assertIn('ryukora', authors)
        self.assertIn('ANASFANANI', authors)

    def test_retired_feed_is_absent_and_stable_feed_matches_release(self):
        self.assertFalse((ROOT / 'update.json').exists())
        meta = json.loads((ROOT / 'update-kernelsu.json').read_text())
        props = dict(line.split('=', 1) for line in (ROOT / 'module.prop').read_text().splitlines() if '=' in line)
        self.assertEqual(f"v{props['version']}", meta['version'])
        self.assertEqual(int(props['versionCode']), meta['versionCode'])
        self.assertEqual(
            f"https://github.com/WayneShao/KernelSU-Tailscaled/releases/download/v{props['version']}/KernelSU-Tailscaled-v{props['version']}.zip",
            meta['zipUrl'],
        )
