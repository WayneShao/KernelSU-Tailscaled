#!/usr/bin/python3
import json
import os
import signal
import socket
import sys
import time
from pathlib import Path

root = Path(os.environ['FIXTURE_ROOT'])
name = Path(sys.argv[0]).name
args = sys.argv[1:]

def option(prefix):
    return next(item.split('=', 1)[1] for item in args if item.startswith(prefix + '='))

def serve(sock):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        time.sleep(0.1)

if name == 'tailscaled':
    with (root / 'starts').open('a') as stream:
        stream.write(str(time.monotonic()) + '\n')
    if (root / 'daemon-fail').exists():
        sys.exit(1)
    sock = socket.socket(socket.AF_UNIX)
    sock.bind(option('--socket'))
    sock.listen()
    Path(option('--state')).touch()
    serve(sock)
elif name == 'tailscale':
    if 'version' in args:
        print('1.102.3')
    elif 'web' in args:
        sock = socket.socket()
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        host, port = option('--listen').split(':')
        sock.bind((host, int(port)))
        sock.listen()
        serve(sock)
    elif 'status' in args:
        if (root / 'cli-hang').exists():
            time.sleep(20)
        print((root / 'status.json').read_text())
    elif 'prefs' in args:
        print((root / 'prefs.json').read_text())
    elif 'set' in args:
        with (root / 'sets').open('a') as stream:
            stream.write(json.dumps(args) + '\n')
    else:
        sys.exit(2)
elif name == 'ip':
    with (root / 'ip-calls').open('a') as stream:
        stream.write(' '.join(args) + '\n')
    if 'link' in args:
        sys.exit(0 if (root / 'link').exists() else 1)
    if 'address' in args or 'addr' in args:
        print((root / 'addresses').read_text())
    elif 'route' in args:
        print((root / 'routes').read_text())
elif name == 'nc':
    try:
        with socket.create_connection((args[-2], int(args[-1])), timeout=0.2):
            pass
    except OSError:
        sys.exit(1)
elif name == 'settings':
    print((root / 'device-name').read_text() if (root / 'device-name').exists() else 'Fixture Phone')
elif name == 'getprop':
    print('fixture-product')
