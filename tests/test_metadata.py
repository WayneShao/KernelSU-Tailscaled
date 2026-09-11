import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetadataTests(unittest.TestCase):
    def test_current_release_identity(self):
        props = dict(line.split('=', 1) for line in (ROOT / 'module.prop').read_text().splitlines() if '=' in line)
        self.assertEqual('kernelsu-tailscaled', props['id'])
        self.assertEqual('KernelSU-Tailscaled', props['name'])
        self.assertEqual('2.0.4', props['version'])
        self.assertEqual(20000010, int(props['versionCode']))
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

    def test_retired_feed_is_absent_and_current_feed_matches_release(self):
        self.assertFalse((ROOT / 'update.json').exists())
        meta = json.loads((ROOT / 'update-kernelsu.json').read_text())
        self.assertEqual('v2.0.4', meta['version'])
        self.assertEqual(20000010, meta['versionCode'])
        self.assertIn('/v2.0.4/KernelSU-Tailscaled-v2.0.4.zip', meta['zipUrl'])
