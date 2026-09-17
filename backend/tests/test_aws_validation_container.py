"""Exercise the shell entrypoint without Docker, credentials or network access."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launcher(tmp_path):
    script = tmp_path / 'scripts/aws_validation_container.sh'
    script.parent.mkdir()
    shutil.copy2(ROOT / 'scripts/aws_validation_container.sh', script)
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    docker = binaries / 'docker'
    docker.write_text(f'#!{sys.executable}\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
    docker.chmod(0o755)
    uname = binaries / 'uname'
    uname.write_text('#!/bin/sh\nprintf "Linux\\n"\n')
    uname.chmod(0o755)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('AWS_', 'ZZIK_'))}
    env['PATH'] = str(binaries) + os.pathsep + env['PATH']
    env['AWS_ACCESS_KEY_ID'] = 'TEST_SECRET_NOT_TO_FORWARD'
    def run(mode, **extra):
        return subprocess.run(['bash', str(script), mode], env={**env, **extra}, capture_output=True, text=True)
    return run


def test_plan_container_has_no_network_or_host_credentials(launcher):
    result = launcher('plan')
    assert result.returncode == 0
    args = json.loads(result.stdout)
    assert args[args.index('--network') + 1] == 'none'
    assert '--pull=never' in args and '--read-only' in args
    assert '--execute' not in args and '--env-file' not in args
    assert 'AWS_EC2_METADATA_DISABLED=true' in args
    assert 'TEST_SECRET_NOT_TO_FORWARD' not in result.stdout
    assert args.count('--mount') == 1 and 'dst=/reports' in args[args.index('--mount') + 1]


@pytest.mark.parametrize('values', [
    {}, {'ZZIK_IAM_USERNAME': 'kmuct-edu-05', 'ZZIK_VALIDATION_BUCKET': 'someone-else-bucket'},
    {'ZZIK_IAM_USERNAME': 'kmuct-edu-05', 'ZZIK_VALIDATION_BUCKET': 'kmuct-edu-05-test'}])
def test_live_missing_scope_stops_before_docker(launcher, values):
    result = launcher('execute', **values)
    assert result.returncode == 2 and not result.stdout


def test_live_command_pins_region_role_and_call_limit(launcher):
    result = launcher('execute', ZZIK_IAM_USERNAME='kmuct-edu-05',
                      ZZIK_VALIDATION_BUCKET='kmuct-edu-05-test', ZZIK_EXPECTED_ROLE='AssignedRole')
    assert result.returncode == 0
    args = json.loads(result.stdout)
    assert args[args.index('--network') + 1] == 'host'
    assert '--execute' in args
    assert args[args.index('--expected-role') + 1] == 'AssignedRole'
    assert args[args.index('--region') + 1] == 'us-east-1'
    assert args[args.index('--max-calls') + 1] == '7'
    assert 'AWS_EC2_METADATA_V1_DISABLED=true' in args
    assert '--env-file' not in args and '-p' not in args and '--privileged' not in args
