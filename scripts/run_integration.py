#!/usr/bin/env python3
"""Run real API/worker/web E2E in a disposable schema and file store.

Requires an existing local PostgreSQL database ending in _e2e. Never resets the
whole database or uses the application's .env database/storage configuration.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]


def local_database(value: str):
    try:
        url = make_url(value)
    except Exception:
        raise ValueError('ZZIK_E2E_DATABASE_URL must be a valid local PostgreSQL URL.') from None
    if url.get_backend_name() != 'postgresql' or url.host not in {'127.0.0.1', 'localhost', '::1'} or not (url.database or '').endswith('_e2e'):
        raise ValueError('Refusing to run outside a local PostgreSQL database ending in _e2e.')
    if url.query:
        raise ValueError('Use a local test database URL without extra connection options.')
    return url


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def wait_ready(address, children, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in children):
            raise RuntimeError('A service exited before readiness. See logs/integration/.')
        try:
            with urllib.request.urlopen(address, timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(.2)
    raise RuntimeError('Service readiness timed out. See logs/integration/.')


def stop(children):
    for process in children:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    for process in children:
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def main():
    raw = os.environ.get('ZZIK_E2E_DATABASE_URL', '')
    if not raw:
        raise ValueError('Set ZZIK_E2E_DATABASE_URL to an existing local *_e2e database.')
    url = local_database(raw)
    schema = 'zzik_e2e_' + uuid.uuid4().hex
    engine = create_engine(url, pool_pre_ping=True)
    api_port, web_port = free_port(), free_port()
    while api_port == web_port:
        web_port = free_port()
    origin = f'http://127.0.0.1:{web_port}'
    env = dict(os.environ)
    env.update({
        'DATABASE_URL': url.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False),
        'STORAGE_BACKEND': 'local', 'FACE_ANALYSIS_PROVIDER': 'fixture',
        'DEMO_ENABLED': 'true', 'COOKIE_SECURE': 'false',
        'FIXTURE_MANIFEST': str(ROOT / 'backend/fixtures/manifest.json'),
        'ALLOWED_ORIGINS': origin, 'GEOCODING_URL': '',
        'AWS_EC2_METADATA_DISABLED': 'true',
        'PLAYWRIGHT_BASE_URL': origin,
        'VITE_API_PROXY_TARGET': f'http://127.0.0.1:{api_port}',
    })
    logs = ROOT / 'logs/integration' / schema
    logs.mkdir(parents=True)
    children, handles = [], []
    created = False

    def checked(command):
        process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)
        try:
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            stop([process])

    def launch(command, name, cwd=ROOT):
        handle = (logs / f'{name}.log').open('w')
        handles.append(handle)
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=handle, stderr=subprocess.STDOUT, start_new_session=True)
        children.append(process)

    try:
        with engine.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        with tempfile.TemporaryDirectory(prefix='zzik-e2e-storage-') as storage:
            env['STORAGE_ROOT'] = storage
            try:
                checked([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'])
                checked([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'check'])
                checked([sys.executable, '-m', 'backend.app.seed'])
                launch([sys.executable, '-m', 'uvicorn', 'backend.app.main:app', '--host', '127.0.0.1', '--port', str(api_port)], 'api')
                launch([sys.executable, '-m', 'backend.app.worker'], 'worker')
                launch(['npm', 'run', 'dev', '--', '--host', '127.0.0.1', '--port', str(web_port), '--strictPort'], 'frontend', ROOT / 'frontend')
                wait_ready(f'http://127.0.0.1:{api_port}/api/health/ready', children)
                wait_ready(origin, children)
                print('Isolated API + worker + web ready; running real-server E2E.', flush=True)
                checked(['npm', '--prefix', 'frontend', 'run', 'test:e2e'])
            finally:
                stop(children)
                for handle in handles:
                    handle.close()
    finally:
        try:
            if created:
                with engine.begin() as connection:
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            engine.dispose()
    print('Integration passed. Child processes, temporary schema and file store removed.')


def interrupted(*_):
    raise KeyboardInterrupt


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, interrupted)
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as error:
        # Connection exceptions can include credentials. Keep raw details off CI output.
        print(f'Integration setup failed ({type(error).__name__}); check the test DB configuration.', file=sys.stderr)
        sys.exit(1)
