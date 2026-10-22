import os
import hashlib
import io
import tarfile
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix', 'POSIX shell required')
class EngineUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle = self.root / 'bundle'
        self.state = self.root / 'state'
        self.bundle.mkdir()
        self.state.mkdir()
        (self.bundle / 'engine-version').write_text('v1.104.2\n')
        (self.bundle / 'bin').mkdir()
        self.env = dict(os.environ, BUNDLE_DIR=str(self.bundle), TS_DIR=str(self.state))

    def tearDown(self):
        self.tmp.cleanup()

    def run_shell(self, code):
        library = ROOT / 'tailscale/scripts/engine-lib.sh'
        return subprocess.run(['sh', '-c', f'. "{library}"; ' + code],
                              env=self.env, text=True, capture_output=True)

    def test_bundled_engine_is_default(self):
        result = self.run_shell('engine_select; printf "%s" "$ENGINE_DIR"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.bundle))

    def test_selected_verified_engine_is_preserved_across_module_upgrade(self):
        engine = self.state / 'engines' / '1.106.0-arm64'
        (engine / 'bin').mkdir(parents=True)
        (engine / 'engine-version').write_text('1.106.0\n')
        (self.state / 'engine-current').symlink_to(engine)
        result = self.run_shell('engine_select; printf "%s" "$ENGINE_DIR"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(engine))
        (self.bundle / 'engine-version').write_text('1.108.0\n')
        self.assertEqual(self.run_shell('engine_select; printf "%s" "$ENGINE_DIR"').stdout,
                         str(self.bundle))

    def test_external_engine_pointer_is_rejected(self):
        (self.state / 'engine-current').symlink_to(self.bundle)
        result = self.run_shell('engine_select')
        self.assertNotEqual(result.returncode, 0)

    def test_version_validation_rejects_shell_and_path_syntax(self):
        for version in ('1.2.3/../../x', '1.2.3;id', '1.2', 'latest', '1.2.3-beta'):
            with self.subTest(version=version):
                result = self.run_shell(f"engine_valid_version '{version}'")
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_shell("engine_valid_version '1.104.2'").returncode, 0)

    def test_checksum_verification_detects_tampered_engine(self):
        for name in ('tailscale', 'tailscaled'):
            (self.bundle / 'bin' / name).write_bytes(b'original executable')
        names = ('bin/tailscale', 'bin/tailscaled', 'engine-version')
        (self.bundle / 'engine.sha256').write_text(''.join(
            f'{hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()}  {name}\n'
            for name in names))
        self.assertEqual(self.run_shell('engine_verify "$BUNDLE_DIR"').returncode, 0)
        (self.bundle / 'bin/tailscaled').write_bytes(b'tampered')
        self.assertNotEqual(self.run_shell('engine_verify "$BUNDLE_DIR"').returncode, 0)

    def prepare_transaction(self):
        engine = self.state / 'engines' / '1.106.0-arm64'
        (engine / 'bin').mkdir(parents=True)
        for name in ('tailscale', 'tailscaled'):
            (engine / 'bin' / name).write_bytes(b'candidate')
        (engine / 'engine-version').write_text('1.106.0\n')
        names = ('bin/tailscale', 'bin/tailscaled', 'engine-version')
        (engine / 'engine.sha256').write_text(''.join(
            f'{hashlib.sha256((engine / name).read_bytes()).hexdigest()}  {name}\n'
            for name in names))
        (self.state / 'engine-ready').symlink_to(engine)
        (self.state / 'run').mkdir()
        (self.state / 'run/wanted').write_text('1\n')
        (self.state / 'tailscaled.state').write_text('original identity')
        return engine

    def transaction(self, action='engine_apply', fail=False, disabled=False):
        update = ROOT / 'tailscale/scripts/engine-update.sh'
        return self.run_shell(f'''
          . "{update}"
          RUN_DIR="$TS_DIR/run"; STATE_FILE="$TS_DIR/tailscaled.state"
          SOCKET_FILE="$RUN_DIR/socket"
          cli_json() {{ printf 'NeedsLogin'; }}
          module_disabled() {{ return {0 if disabled else 1}; }}
          json_escape() {{ printf '%s' "$1"; }}
          kst_pointer() {{ ln -s "$2" "$TS_DIR/.$1.new" && mv -Tf "$TS_DIR/.$1.new" "$TS_DIR/$1"; }}
          kst_runtime() {{
            printf '%s\\n' "$2" >> "$TS_DIR/calls"
            if [ "$2" = stop ]; then printf '0\\n' > "$RUN_DIR/wanted"; fi
            if [ "$2" = start ]; then printf '1\\n' > "$RUN_DIR/wanted"; fi
            if [ "$2" = start ] && [ -L "$TS_DIR/engine-current" ]; then
              printf 'candidate changed identity' > "$STATE_FILE"
              {'return 1' if fail else 'return 0'}
            fi
          }}
          {action}
        ''')

    def test_failed_activation_restores_identity_and_previous_selection(self):
        self.prepare_transaction()
        result = self.transaction(fail=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / 'engine-current').exists())
        self.assertEqual((self.state / 'tailscaled.state').read_text(), 'original identity')
        self.assertFalse((self.state / 'engine-transaction').exists())
        self.assertEqual((self.state / 'calls').read_text().splitlines(), ['stop', 'start', 'stop', 'start'])

    def test_stopped_service_stays_stopped_after_engine_selection(self):
        engine = self.prepare_transaction()
        (self.state / 'run/wanted').write_text('0\n')
        result = self.transaction()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'engine-current').resolve(), engine)
        self.assertEqual((self.state / 'calls').read_text().splitlines(), ['stop'])
        self.assertEqual((self.state / 'tailscaled.state').read_text(), 'original identity')

    def test_interrupted_transaction_restores_saved_state(self):
        engine = self.prepare_transaction()
        journal = self.state / 'engine-transaction'
        journal.mkdir()
        (journal / 'previous').write_text('bundled\n')
        (journal / 'wanted').write_text('1\n')
        (journal / 'state-existed').touch()
        (journal / 'snapshot-ready').touch()
        (journal / 'tailscaled.state').write_text('saved identity')
        (self.state / 'engine-current').symlink_to(engine)
        result = self.transaction('engine_recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'tailscaled.state').read_text(), 'saved identity')
        self.assertFalse((self.state / 'engine-current').exists())

    def test_interrupted_recovery_respects_later_disable(self):
        engine = self.prepare_transaction()
        journal = self.state / 'engine-transaction'
        journal.mkdir()
        (journal / 'previous').write_text('bundled\n')
        (journal / 'wanted').write_text('1\n')
        (self.state / 'engine-current').symlink_to(engine)
        result = self.transaction('engine_recover', disabled=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.state / 'calls').read_text().splitlines(), ['stop'])
        self.assertFalse(journal.exists())

    def test_inert_partial_cleanup_is_not_treated_as_rollback(self):
        self.prepare_transaction()
        (self.state / '.engine-completed.123').mkdir()
        result = self.transaction('engine_recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.state / 'calls').exists())

    def test_invalid_recovery_metadata_does_not_stop_live_service(self):
        self.prepare_transaction()
        (self.state / 'engine-transaction').mkdir()
        result = self.transaction('engine_recover')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / 'calls').exists())

    def test_explicit_stop_intent_survives_recovery_and_next_engine_apply(self):
        self.prepare_transaction()
        journal = self.state / 'engine-transaction'
        journal.mkdir()
        (journal / 'previous').write_text('bundled\n')
        (journal / 'wanted').write_text('1\n')
        (journal / 'no-restart').touch()
        (self.state / 'run/wanted').write_text('0\n')
        result = self.transaction('engine_apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('start', (self.state / 'calls').read_text())

    def download_fixture(self, corrupt=False, symlink=False):
        download = self.root / 'download'
        download.mkdir()
        archive = download / 'archive'
        with tarfile.open(archive, 'w:gz') as tar:
            for name in ('tailscale', 'tailscaled'):
                data = b'#!/bin/sh\nprintf "1.106.0\\n"\n'
                member = tarfile.TarInfo(f'tailscale_1.106.0_arm64/{name}')
                member.size = len(data)
                if symlink and name == 'tailscaled':
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/system/bin/sh'
                    member.size = 0
                tar.addfile(member, io.BytesIO(data) if member.isfile() else None)
        digest = '0' * 64 if corrupt else hashlib.sha256(archive.read_bytes()).hexdigest()
        (download / 'checksum').write_text(digest)
        fakebin = self.root / 'fakebin'
        fakebin.mkdir()
        (fakebin / 'uname').write_text('#!/bin/sh\necho aarch64\n')
        (fakebin / 'curl').write_text('''#!/usr/bin/python3
import os, pathlib, sys, shutil
args = sys.argv[1:]
url = next(x for x in args if x.startswith('https://'))
source = 'checksum' if url.endswith('.sha256') else 'archive'
shutil.copyfile(pathlib.Path(os.environ['ENGINE_DOWNLOAD_FIXTURE']) / source,
                args[args.index('--output') + 1])
''')
        for path in fakebin.iterdir():
            path.chmod(0o755)
        self.env['PATH'] = str(fakebin) + ':' + os.environ['PATH']
        self.env['ENGINE_DOWNLOAD_FIXTURE'] = str(download)
        (self.state / 'engine-offer').write_text('1.106.0\n')
        (self.state / 'run').mkdir()

    def prepare_download(self):
        library = ROOT / 'tailscale/scripts/engine-update.sh'
        return self.run_shell(f'''
          . "{library}"
          RUN_DIR="$TS_DIR/run"
          bounded() {{ seconds=$1; shift; timeout "$seconds" "$@"; }}
          json_escape() {{ printf '%s' "$1"; }}
          kst_pointer() {{ ln -s "$2" "$TS_DIR/.$1.new" && mv -Tf "$TS_DIR/.$1.new" "$TS_DIR/$1"; }}
          engine_prepare
        ''')

    def test_verified_download_stages_both_binaries_without_selecting_them(self):
        self.download_fixture()
        result = self.prepare_download()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.state / 'engine-ready/bin/tailscaled').exists())
        self.assertFalse((self.state / 'engine-current').exists())

    def test_corrupt_archive_never_becomes_staged_or_active(self):
        self.download_fixture(corrupt=True)
        result = self.prepare_download()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / 'engine-ready').exists())
        self.assertFalse((self.state / 'engine-current').exists())

    def test_symlink_archive_member_is_rejected(self):
        self.download_fixture(symlink=True)
        result = self.prepare_download()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.state / 'engine-ready').exists())

