#!/usr/bin/env python3
"""Mechanical starter round trip, not independent prompt-only reimplementation."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile

from starter import ROOT, export, replay_reference, status, require


def run(root, *command):
    subprocess.run(command, cwd=root, check=True)


def verify(output, behavior):
    state = export(ROOT, 'HEAD', output)
    require(len(status(output)['pending_units']) == len(state['units']) == 30, 'Full starter gate must be red')
    run(output, sys.executable, 'scripts/check_harness.py')
    run(output, 'npm', '--prefix', 'frontend', 'ci')
    run(output, 'npm', '--prefix', 'contracts/codegen', 'ci')
    run(output, 'npm', '--prefix', 'frontend', 'run', 'types:check')
    run(output, 'npm', '--prefix', 'frontend', 'run', 'build')
    profiles = []
    with tempfile.TemporaryDirectory(prefix='zzik-role-check-') as temporary:
        for role in range(1, 6):
            root = Path(temporary) / str(role)
            role_state = export(ROOT, 'HEAD', root, str(role))
            result = status(root)
            expected = [u['id'] for u in role_state['units'] if u['role'] == role]
            require(result['pending_units'] == expected, 'Role profile leaked/missed a boundary')
            require(not result['changed_protected_files'] and not result['missing_units'], 'Broken profile')
            profiles.append({'role': role, 'pending_units': len(expected)})
    report = replay_reference(ROOT, output)
    run(output, sys.executable, 'scripts/check_harness.py')
    run(output, 'npm', '--prefix', 'frontend', 'run', 'types:check')
    run(output, 'npm', '--prefix', 'frontend', 'run', 'build')
    if behavior:
        require(bool(os.environ.get('TEST_DATABASE_URL')) and bool(os.environ.get('ZZIK_E2E_DATABASE_URL')), 'Set dedicated test and E2E database URLs')
        run(output, sys.executable, '-m', 'pytest', '-q', 'backend/tests')
        run(output / 'frontend', 'npx', 'playwright', 'install', 'chromium')
        run(output, sys.executable, 'scripts/run_integration.py')
    report.update(source_commit=state['source_commit'], reference_commit=state['reference_commit'], profiles=profiles,
                  scaffold_contract_and_build=True, reassembled_behavior_tests=behavior, aws_verified=False)
    (output / 'starter-verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--behavior', action='store_true')
    args = parser.parse_args()
    verify(args.output.resolve(), args.behavior)
