"""Deterministic Git planning without modifying remotes or credentials."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('assembly_plan', ROOT / 'scripts/assembly_plan.py')
assembly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assembly)


def config():
    return {'version': 1, 'mode': 'contest', 'repository': 'example/official', 'base_branch': 'main',
            'run_id': 'event-01', 'starter_import_allowed': True, 'rules_reference': 'fixture permission',
            'roles': {str(n): f'member-{n}' for n in range(1, 6)}}


def manifest():
    return json.loads((ROOT / 'starter/manifest.json').read_text())


def test_covers_every_unit_and_assigns_other_reviewers():
    c = config()
    p = assembly.plan(c, manifest())
    units = [u for r in p['roles'] for u in r['units_in_order']]
    assert len(units) == len(set(units)) == 30
    assert set(units) == {u['id'] for u in manifest()['units']}
    assert all(r['owner'] != r['reviewer'] for r in p['roles'])
    assert p['repository'] == 'example/official' and p['base_branch'] == 'main'
    assert p['candidate_merge_order'] == [1, 3, 4, 5, 2]
    assert p['aws_execution_allowed'] is False


@pytest.mark.parametrize('field,value', [('repository', ''), ('repository', 'https://github.com/a/b'),
    ('base_branch', '-main'), ('base_branch', 'bad..branch'), ('base_branch', 'assemble/event-01'),
    ('starter_import_allowed', False), ('rules_reference', ''), ('run_id', '../escape')])
def test_missing_or_unsafe_setup_blocks_plan(field, value):
    c = config()
    c[field] = value
    with pytest.raises(ValueError):
        assembly.plan(c, manifest())


def test_does_not_claim_independent_review_with_same_account():
    c = config()
    c['roles']['2'] = c['roles']['1']
    with pytest.raises(ValueError, match='distinct'):
        assembly.plan(c, manifest())
    c['mode'] = 'rehearsal'
    assert assembly.plan(c, manifest())['distinct_role_accounts'] == 4


@pytest.mark.parametrize('remote', ['https://github.com/org/repo.git', 'git@github.com:org/repo.git', 'https://github.com/org/repo'])
def test_repository_identity(remote):
    assert assembly.repository_name(remote) == 'org/repo'


@pytest.mark.parametrize('remote', ['https://token@github.com/org/repo', 'https://other.example/org/repo', '/tmp/repo'])
def test_reject_other_or_credential_bearing_remote(remote):
    with pytest.raises(ValueError):
        assembly.repository_name(remote)
