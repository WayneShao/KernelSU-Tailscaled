import concurrent.futures
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'posix' and Path('/proc').exists(), 'Linux behavior tests; run in WSL')
class RuntimeBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kst-runtime-')
        self.root = Path(self.temp.name)
        self.bundle = self.root / 'bundle'
        self.state = self.root / 'state'
        self.mod = self.root / 'module'
        self.bin = self.bundle / 'bin'
        self.mod.mkdir()
        self.bin.mkdir(parents=True)
        shutil.copytree(ROOT / 'tailscale', self.bundle / 'tailscale')
        for file in (self.bundle / 'tailscale/scripts').iterdir():
            if file.is_file():
                file.write_bytes(file.read_bytes().replace(b'#!/system/bin/sh', b'#!/bin/sh'))
                file.chmod(0o755)
        (self.bundle / 'module.prop').write_text('version=2.0.0-beta.1\nversionCode=20000001\n')
        (self.mod / 'module.prop').write_text('version=2.0.0-beta.1\n')
        for name in ['tailscale', 'tailscaled', 'ip', 'nc', 'settings', 'getprop']:
            shutil.copy(ROOT / 'tests/runtime/fake_runtime.py', self.bin / name)
            (self.bin / name).chmod(0o755)
        (self.state / 'config').mkdir(parents=True)
        (self.state / 'run').mkdir()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.config = (ROOT / 'tailscale/config/module.conf').read_text().replace('127.0.0.1:8088', f'127.0.0.1:{self.port}').replace('SUPERVISOR_INTERVAL=5', 'SUPERVISOR_INTERVAL=1').replace('RESTART_BACKOFF_MAX=60', 'RESTART_BACKOFF_MAX=4')
        self.set_config(self.config)
        self.write_status()
        (self.root / 'prefs.json').write_text(json.dumps({'Hostname': '', 'CorpDNS': False, 'RouteAll': False, 'Persist': {'PrivateNodeKey': 'PRIVATE_SENTINEL'}}))
        (self.root / 'link').touch()
        (self.root / 'addresses').write_text('7: tailscale0 inet 100.100.1.1/32 scope global tailscale0\n')
        (self.root / 'routes').write_text('100.100.1.2 dev tailscale0 table 52 src 100.100.1.1\n')
        self.env = dict(os.environ, BUNDLE_DIR=str(self.bundle), TS_DIR=str(self.state), MODDIR=str(self.mod), FIXTURE_ROOT=str(self.root), PATH=str(self.bin) + ':' + os.environ['PATH'], KST_SHELL='/bin/sh', KST_CLI_TIMEOUT='1', KST_START_TIMEOUT='3', KST_STOP_TIMEOUT='1', KST_LOCK_TIMEOUT='2', KST_STAGED_DIR=str(self.root / 'staged'))
        self.scripts = self.bundle / 'tailscale/scripts'
        self.service = self.scripts / 'tailscale-service'

    def tearDown(self):
        self.run_command('stop', timeout=15)
        for proc in Path('/proc').iterdir():
            if proc.name.isdigit() and int(proc.name) != os.getpid():
                try:
                    if str(self.root).encode() in (proc / 'cmdline').read_bytes():
                        os.kill(int(proc.name), signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
        self.temp.cleanup()

    def set_config(self, text):
        (self.state / 'config/module.conf').write_text(text)

    def write_status(self, backend='Running', peers=True, **extra):
        status = {'BackendState': backend, 'TailscaleIPs': ['100.100.1.1'], 'Self': {'DNSName': 'fixture.example.ts.net.'}, 'Peer': {'peer': {'TailscaleIPs': ['100.100.1.2']}} if peers else {}, 'Health': []}
        status.update(extra)
        (self.root / 'status.json').write_text(json.dumps(status))

    def run_command(self, command, timeout=15, env=None):
        return subprocess.run(['/bin/sh', str(self.service), command], env=env or self.env, capture_output=True, text=True, timeout=timeout)

    def status(self):
        result = self.run_command('status-json')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def start(self):
        result = self.run_command('start')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def common(self, body):
        return subprocess.run(['/bin/sh', '-c', '. "$BUNDLE_DIR/tailscale/scripts/common.sh"; ' + body], env=self.env, capture_output=True, text=True, timeout=10)

    def test_native_health_rejects_missing_interface(self):
        (self.root / 'link').unlink()
        result = subprocess.run(['/bin/sh', str(self.scripts / 'tailscale-tunnel'), 'health'], env=self.env)
        self.assertNotEqual(result.returncode, 0)

    @unittest.skipUnless(shutil.which('busybox'), 'Install BusyBox for the actual AWK parser regression')
    def test_busybox_json_parser_handles_scalars_and_arrays(self):
        payload = {'BackendState': 'Running', 'flag': True, 'empty': None,
                   'number': 123, 'fraction': 1.25, 'list': [False, None, 4]}
        result = subprocess.run([shutil.which('busybox'), 'awk', '-v', 'action=backend',
                                 '-f', str(self.scripts / 'json.awk')],
                                input=json.dumps(payload), text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('Running', result.stdout.strip())

    @unittest.skipUnless(shutil.which('mksh'), 'Install mksh for Android descriptor inheritance regression')
    def test_android_mksh_inherits_control_and_supervisor_locks(self):
        env = dict(self.env, KST_SHELL=shutil.which('mksh'))
        try:
            result = subprocess.run([env['KST_SHELL'], str(self.service), 'start'],
                                    env=env, capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired as error:
            self.fail((error.stdout or b'').decode() + (error.stderr or b'').decode())
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn('Bad file descriptor', result.stderr)
        time.sleep(0.5)
        self.assertEqual('running', self.status()['components']['supervisor'])
        stopped = subprocess.run([env['KST_SHELL'], str(self.service), 'stop'],
                                 env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(0, stopped.returncode, stopped.stdout + stopped.stderr)

    def test_config_is_data_not_shell(self):
        sentinel = self.root / 'INJECTED'
        self.set_config(self.config + f'UNKNOWN=$(touch {sentinel})\n')
        result = self.run_command('start')
        self.assertFalse(sentinel.exists())
        self.assertNotEqual(result.returncode, 0)

    def test_stop_and_disable_work_with_invalid_configuration(self):
        self.start()
        self.set_config('MODE=invalid\n')
        self.assertEqual(self.run_command('stop').returncode, 0)
        self.assertEqual(self.run_command('disable').returncode, 0)
        self.assertTrue((self.mod / 'disable').exists())
        status = self.status()
        self.assertEqual(status['schemaVersion'], 2)
        self.assertEqual(status['lifecycle'], 'disabled')
        self.assertEqual(status['components']['daemon'], 'stopped')

    def test_in_progress_migration_blocks_start_and_is_visible(self):
        (self.state / 'migration.pending').mkdir()
        (self.state / 'tailscaled.state').write_text('IMPORTED')
        self.assertEqual(self.status()['lifecycle'], 'migration-required')
        self.assertNotEqual(self.run_command('start').returncode, 0)
        self.assertFalse((self.root / 'starts').exists())

    def test_migration_origin_prevents_pending_fresh_defaults_rewrite(self):
        (self.state / 'tailscaled.state').write_text('IMPORTED')
        (self.state / 'migration-origin').touch()
        (self.state / 'migration-awaiting-enable').touch()
        (self.state / 'fresh-defaults.pending').touch()
        self.assertIn('migrat', json.dumps(self.status()['diagnostics']).lower())
        self.start()
        self.assertFalse((self.root / 'sets').exists())

    def test_pid_starttime_prevents_reused_pid_termination(self):
        proc = subprocess.Popen(['/bin/sleep', '30'])
        try:
            pidfile = self.state / 'run/foreign.pid'
            result = self.common(f'write_pid "{pidfile}" {proc.pid} /bin/sleep; sed -i "2s/.*/1/" "{pidfile}"; stop_owned "{pidfile}" /bin/sleep')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait()

    def test_failed_owned_stop_retains_record_and_returns_failure(self):
        proc = subprocess.Popen(['/bin/sleep', '30'])
        try:
            pidfile = self.state / 'run/foreign.pid'
            result = self.common(f'write_pid "{pidfile}" {proc.pid} /bin/sleep; kill() {{ return 1; }}; stop_owned "{pidfile}" /bin/sleep')
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(pidfile.exists())
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait()

    def test_failed_identity_check_retains_live_process_record(self):
        proc = subprocess.Popen(['/bin/sleep', '30'])
        try:
            pidfile = self.state / 'run/foreign.pid'
            result = self.common(f'write_pid "{pidfile}" {proc.pid} /bin/sleep; '
                                 'pid_matches() { return 1; }; '
                                 f'stop_owned "{pidfile}" /bin/sleep')
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(pidfile.exists())
            self.assertIsNone(proc.poll())
        finally:
            proc.terminate()
            proc.wait()

    def test_unverified_live_daemon_preserves_socket_and_blocks_restart(self):
        self.assertEqual(self.run_command('start').returncode, 0)
        self.common('stop_owned "$SUPERVISOR_PID" "$SUPERVISOR_SCRIPT"')
        pidfile = self.state / 'run/tailscaled.pid'
        original = pidfile.read_text()
        lines = original.splitlines()
        lines[3] = '/different-generation/tailscaled'
        pidfile.write_text('\n'.join(lines) + '\n')
        sock = self.state / 'run/tailscaled.sock'
        self.assertTrue(sock.exists())
        before = (self.root / 'starts').read_text()
        try:
            stop = subprocess.run(['/bin/sh', str(self.scripts / 'tailscale-daemon'), 'stop'],
                                  env=self.env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(stop.returncode, 0)
            self.assertTrue(pidfile.exists())
            self.assertTrue(sock.exists())
            start = subprocess.run(['/bin/sh', str(self.scripts / 'tailscale-daemon'), 'start'],
                                   env=self.env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(start.returncode, 0)
            self.assertTrue(sock.exists())
            self.assertEqual(before, (self.root / 'starts').read_text())
        finally:
            pidfile.write_text(original)

    def test_stop_failure_propagates_and_restart_does_not_start(self):
        daemon = self.scripts / 'tailscale-daemon'
        daemon.write_text('#!/bin/sh\ncase "$1" in stop) exit 9;; *) touch "$FIXTURE_ROOT/restarted";; esac\n')
        self.assertNotEqual(self.run_command('stop').returncode, 0)
        self.assertEqual((self.state / 'run/lifecycle').read_text().strip(), 'failed')
        self.assertNotEqual(self.run_command('restart').returncode, 0)
        self.assertFalse((self.root / 'restarted').exists())

    def test_lock_rejects_spoofed_inheritance_and_is_bounded(self):
        lock = self.state / 'run/control.lock'
        with lock.open('w') as handle:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
            result = self.common('KST_LOCK_HELD=1; export KST_LOCK_HELD; with_control_lock true')
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertIn('lock', result.stderr.lower())

    def test_disabled_marker_does_not_start_daemon(self):
        (self.mod / 'disable').touch()
        self.assertNotEqual(self.run_command('start').returncode, 0)
        self.assertFalse((self.root / 'starts').exists())

    def test_duplicate_concurrent_start_is_singleton_and_stop_is_bounded(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_command('start'), range(2)))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len((self.root / 'starts').read_text().splitlines()), 1)
        started = time.monotonic()
        self.assertEqual(self.run_command('stop').returncode, 0)
        self.assertLess(time.monotonic() - started, 6)
        self.assertEqual(self.status()['components']['daemon'], 'stopped')

    def test_activation_inherited_lock_start_and_background_fd_close(self):
        result = self.common('with_control_lock "$BUNDLE_DIR/tailscale/scripts/tailscale-service" start')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.common('with_control_lock true')
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ['supervisor.pid', 'tailscaled.pid', 'web.pid']:
            pid = (self.state / 'run' / name).read_text().splitlines()[0]
            self.assertFalse(Path('/proc') .joinpath(pid, 'fd/9').exists(), name)

    def test_only_supervisor_holds_singleton_lock(self):
        self.start()
        time.sleep(0.3)
        supervisor = (self.state / 'run/supervisor.pid').read_text().splitlines()[0]
        holders = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if any(fd.resolve() == self.state / 'run/supervisor.lock' for fd in (proc / 'fd').iterdir()):
                    holders.append(proc.name)
            except OSError:
                pass
        self.assertEqual(holders, [supervisor])

    def test_orphaned_supervisor_pass_cannot_stop_new_runtime(self):
        import fcntl
        self.env['KST_LOCK_TIMEOUT'] = '10'
        self.start()
        supervisor = int((self.state / 'run/supervisor.pid').read_text().splitlines()[0])
        lock = self.state / 'run/control.lock'
        with lock.open('w') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            child = None
            deadline = time.monotonic() + 3
            while child is None and time.monotonic() < deadline:
                children = Path(f'/proc/{supervisor}/task/{supervisor}/children').read_text().split()
                for pid in children:
                    try:
                        if b'tailscale-supervisor' in Path(f'/proc/{pid}/cmdline').read_bytes():
                            child = int(pid)
                            break
                    except OSError:
                        pass
                time.sleep(0.02)
            self.assertIsNotNone(child, 'Supervisor did not enter its blocked control pass')
            os.kill(supervisor, signal.SIGKILL)
            (self.state / 'run/supervisor.pid').unlink()
            (self.state / 'run/wanted').write_text('0\n')
        time.sleep(0.6)
        self.assertTrue((self.state / 'run/tailscaled.sock').exists(),
                        'An orphaned supervisor pass removed the live daemon socket')
        self.assertEqual('running', self.status()['components']['daemon'])

    def test_truthful_status_address_routes_health_and_secret_projection(self):
        self.start()
        status = self.status()
        self.assertEqual(status['schemaVersion'], 2)
        self.assertEqual(status['components']['dataPlane'], 'running')
        self.assertNotIn('PRIVATE_SENTINEL', json.dumps(status))
        self.assertIsNone(status['runtime']['stagedVersion'])
        (self.root / 'addresses').write_text('')
        status = self.status()
        self.assertEqual(status['lifecycle'], 'degraded')
        self.assertEqual(status['components']['dataPlane'], 'stopped')
        (self.root / 'addresses').write_text('7: tailscale0 inet 100.100.1.1/32 scope global tailscale0\n')
        (self.root / 'routes').write_text('100.100.1.2 via 192.0.2.1 dev foreign0\n')
        self.assertEqual(self.status()['components']['dataPlane'], 'stopped')
        self.write_status(Health=['Fixture upstream warning'])
        self.assertIn('Fixture upstream warning', json.dumps(self.status()))

    def test_needs_login_is_not_daemon_crash_or_peer_route_requirement(self):
        self.write_status(backend='NeedsLogin')
        (self.root / 'routes').write_text('')
        self.start()
        status = self.status()
        self.assertEqual(status['components']['daemon'], 'running')
        self.assertEqual(status['components']['dataPlane'], 'unknown')
        self.assertIn('login', json.dumps(status['diagnostics']).lower())
        time.sleep(2)
        self.assertEqual(len((self.root / 'starts').read_text().splitlines()), 1)

    def test_cli_timeout_and_malformed_json_are_visible(self):
        self.start()
        (self.root / 'cli-hang').touch()
        started = time.monotonic()
        status = self.status()
        self.assertLess(time.monotonic() - started, 5)
        self.assertIsNone(status['tailscale'])
        self.assertEqual(status['lifecycle'], 'degraded')
        self.assertTrue(status['diagnostics'])
        (self.root / 'cli-hang').unlink()
        (self.root / 'status.json').write_text('{"BackendState":"Running",broken}')
        self.assertIsNone(self.status()['tailscale'])

    def test_fresh_defaults_before_login_and_imported_prefs_untouched(self):
        self.write_status(backend='NeedsLogin', peers=False)
        self.start()
        sets = (self.root / 'sets').read_text()
        for argument in ['--accept-dns=false', '--accept-routes=false', '--exit-node=', '--advertise-routes=', '--hostname=fixture-phone']:
            self.assertIn(argument, sets)
        self.run_command('stop')
        (self.root / 'sets').unlink()
        self.start()
        self.assertFalse((self.root / 'sets').exists())

    def test_existing_identity_never_rewrites_preferences(self):
        (self.state / 'tailscaled.state').write_text('IMPORTED')
        (self.root / 'prefs.json').write_text(json.dumps({'Hostname': 'admin-name', 'CorpDNS': True, 'RouteAll': True}))
        self.start()
        self.assertFalse((self.root / 'sets').exists())
        self.assertIn('dns', json.dumps(self.status()['diagnostics']).lower())

    def test_unusable_display_name_falls_back_to_android_product(self):
        (self.root / 'device-name').write_text('***')
        self.start()
        self.assertIn('--hostname=fixture-product', (self.root / 'sets').read_text())

    def test_enable_failure_preserves_enabled_intent(self):
        (self.mod / 'disable').touch()
        (self.root / 'daemon-fail').touch()
        self.assertNotEqual(self.run_command('enable').returncode, 0)
        self.assertFalse((self.mod / 'disable').exists())
        self.assertEqual(self.status()['lifecycle'], 'failed')

    def test_crash_recovery_backoff_and_no_foreign_network_mutation(self):
        self.start()
        pid = int((self.state / 'run/tailscaled.pid').read_text().splitlines()[0])
        (self.root / 'daemon-fail').touch()
        os.kill(pid, signal.SIGKILL)
        time.sleep(8)
        starts = list(map(float, (self.root / 'starts').read_text().splitlines()))
        self.assertGreaterEqual(len(starts), 3)
        gaps = [b - a for a, b in zip(starts[1:], starts[2:])]
        self.assertGreaterEqual(gaps[-1], 1.8)
        self.assertLessEqual(len(starts), 5)
        (self.root / 'daemon-fail').unlink()
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if self.status()['components']['daemon'] == 'running':
                break
            time.sleep(0.3)
        self.assertEqual(self.status()['components']['daemon'], 'running')
        calls = (self.root / 'ip-calls').read_text()
        self.assertNotRegex(calls, r'\b(flush|replace|del)\b')

    def test_logs_are_bounded_and_redacted(self):
        (self.state / 'logs').mkdir()
        (self.state / 'logs/tailscaled.log').write_text(('https://login.tailscale.com/a/SECRET tskey-auth-SECRET privkey:SECRET\n' * 20000))
        result = self.run_command('logs')
        self.assertEqual(result.returncode, 0)
        self.assertLess(len(result.stdout), 40000)
        self.assertNotIn('SECRET', result.stdout)

    def test_log_writer_has_a_real_disk_limit(self):
        target = self.state / 'logs/fixture.log'
        target.parent.mkdir()
        result = subprocess.run(['awk', '-v', 'destination=' + str(target), '-f', str(self.scripts / 'log-filter.awk')], input=('x' * 1000 + '\n') * 1000, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(target.stat().st_size, 262144)

    def test_json_escape_round_trips_control_characters(self):
        value = 'quote " slash \\ tab\t cr\r newline\nend'
        result = self.common("json_escape '" + value + "'")
        self.assertEqual(json.loads('"' + result.stdout + '"'), value)

    def test_json_parser_rejects_duplicate_keys_and_malformed_literals(self):
        for text in ['{"BackendState":"Running","BackendState":"Stopped"}', '{"BackendState":"Running","x":01}', '{"BackendState":"Running","x":[1,]}', '{"BackendState":"Running"} garbage']:
            result = subprocess.run(['awk', '-v', 'action=status', '-f', str(self.scripts / 'json.awk')], input=text, text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0, text)

    def test_busybox_applets_are_used_when_provided(self):
        busybox = self.bin / 'busybox'
        busybox.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$FIXTURE_ROOT/applets"\nexec "$@"\n')
        busybox.chmod(0o755)
        self.env['KST_BUSYBOX'] = str(busybox)
        self.start()
        self.assertIn('awk', (self.root / 'applets').read_text().splitlines())

    def test_enable_then_concurrent_start_stop_preserves_singleton(self):
        self.start()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(self.run_command, ['start', 'stop']))
        self.assertTrue(all(result.returncode == 0 for result in results), [(result.returncode, result.stdout, result.stderr) for result in results])
        live = []
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if str(self.bin / 'tailscaled').encode() in (proc / 'cmdline').read_bytes():
                    live.append(proc.name)
            except OSError:
                pass
        self.assertLessEqual(len(live), 1)


if __name__ == '__main__':
    unittest.main()
