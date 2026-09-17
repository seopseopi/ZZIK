#!/usr/bin/env python3
"""Exercise five simulated roles against a new local bare Git repository.

Only Git coordination and a deliberately tiny contract fixture are tested.
This does not build ZZIK, run five AI agents, or test GitHub approval policies.
"""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def verify(destination):
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(ROOT):
        raise ValueError('Choose a new output directory outside the project')
    destination.mkdir(parents=True, mode=0o700)
    remote = destination / 'simulation.git'
    calls = 0
    events = []

    def command(cwd, *args, ok=True):
        nonlocal calls
        calls += 1
        p = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
        if ok and p.returncode:
            raise RuntimeError('Command failed: ' + args[0] + ' / ' + p.stderr[-1200:])
        return p

    def git(cwd, *args, ok=True):
        return command(cwd, 'git', *args, ok=ok)

    def record(name, **data):
        events.append(dict(check=name, **data))

    def identity(path, role):
        git(path, 'config', 'user.name', f'SIMULATED ROLE {role} - not a teammate')
        git(path, 'config', 'user.email', f'simulation-role-{role}@example.invalid')
        git(path, 'config', 'commit.gpgsign', 'false')

    def write(path, name, text):
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def commit(path, message):
        git(path, 'add', '.')
        git(path, 'commit', '-m', 'simulation: ' + message)
        return git(path, 'rev-parse', 'HEAD').stdout.strip()

    def push(path, branch):
        git(path, 'push', '-u', 'origin', branch)

    def checks(path, full=False):
        return command(path, sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', ok=not full)

    git(destination, 'init', '--bare', '--initial-branch=main', str(remote))
    roles = {}
    for n in range(1, 6):
        p = destination / f'role-{n}'
        git(destination, 'clone', str(remote), str(p))
        identity(p, n)
        assert [item.name for item in p.iterdir() if item.name != '.git'] == []
        roles[n] = p
        assert git(p, 'rev-parse', '--verify', 'HEAD', ok=False).returncode != 0
    record('five_separate_clones_start_without_commits', roles=5)

    one, two, three, four, five = [roles[n] for n in range(1, 6)]
    assert git(three, 'rev-parse', '--verify', 'origin/main', ok=False).returncode != 0
    record('role3_waits_for_root_commit')
    write(one, 'README.md', '# SIMULATION ONLY\nNot ZZIK implementation or contest contribution.\n')
    write(one, '.gitignore', '__pycache__/\n*.pyc\n')
    write(one, 'team.json', json.dumps({'scope': 'simulation', 'run_id': 'test', 'base': 'main'}))
    root = commit(one, 'role 1 creates the only root commit')
    push(one, 'main')
    for n in range(2, 6):
        git(roles[n], 'fetch', 'origin')
        git(roles[n], 'checkout', '-B', 'main', 'origin/main')
        assert git(roles[n], 'rev-parse', 'HEAD').stdout.strip() == root

    git(three, 'checkout', '-b', 'foundation/test/backend')
    write(three, 'contract.py', '''def validate(value):
    if set(value) != {'score', 'tags'} or not isinstance(value['score'], (int, float)):
        raise ValueError('analysis contract violated')
    return value
''')
    write(three, 'tests/test_contract.py', '''import unittest
from contract import validate
class ContractTest(unittest.TestCase):
    def test_valid(self): self.assertEqual(validate({'score': .8, 'tags': []})['score'], .8)
    def test_invalid(self):
        with self.assertRaises(ValueError): validate({'quality': .8, 'tags': []})
''')
    commit(three, 'role 3 writes a new minimal contract and actual assertions')
    push(three, 'foundation/test/backend')
    checks(three)
    git(two, 'fetch', 'origin')
    git(two, 'checkout', '-b', 'foundation/test/frontend', 'origin/foundation/test/backend')
    write(two, 'frontend/README.md', 'SIMULATION: role 2 owns frontend project initialization.\n')
    write(two, 'registry.json', '[]\n')
    commit(two, 'role 2 initializes the shared frontend boundary once')
    push(two, 'foundation/test/frontend')
    git(three, 'fetch', 'origin')
    git(three, 'merge', '--no-ff', 'origin/foundation/test/frontend', '-m', 'simulation: collect G1 frontend foundation')
    checks(three)
    foundation = git(three, 'rev-parse', 'HEAD').stdout.strip()
    git(three, 'checkout', 'main')
    git(three, 'merge', '--ff-only', foundation)
    push(three, 'main')
    frozen = git(three, 'rev-parse', 'HEAD').stdout.strip()
    record('G1_has_explicit_shared_commit_and_real_contract_tests', commit=frozen)

    for n in range(1, 6):
        p = roles[n]
        git(p, 'fetch', 'origin')
        git(p, 'checkout', '-b', f'work/test/role-{n}', 'origin/main')
        assert git(p, 'rev-parse', 'HEAD').stdout.strip() == frozen
    record('all_roles_branch_from_same_G1_commit')

    write(one, 'stack.json', json.dumps({'web': 'frontend', 'app': 'pipeline', 'data': 'fixture-only'}))
    write(three, 'pipeline.py', '''from contract import validate
from vision import analyze
from editing import choose

def process():
    return choose(validate(analyze()))
''')
    write(three, 'tests/test_pipeline.py', '''import json
import unittest
from pipeline import process
from screen import render
class PipelineTest(unittest.TestCase):
    def test_contract_to_render(self): self.assertEqual(render(process()), 'recommended')
    def test_shared_registry(self):
        with open('registry.json') as f: self.assertEqual(set(json.load(f)), {'editor', 'gallery'})
''')
    # Deliberate bad change to prove the gate rejects a contract violation.
    write(four, 'vision.py', "def analyze():\n    return {'quality': .8, 'tags': ['fixture']}\n")
    write(five, 'editing.py', "def choose(analysis):\n    return analysis['score'] >= .5\n")
    write(five, 'registry.json', '["editor"]\n')
    write(two, 'screen.py', "def render(selected):\n    return 'recommended' if selected else 'review'\n")
    write(two, 'registry.json', '["gallery"]\n')
    heads = {}
    for n in range(1, 6):
        heads[n] = commit(roles[n], f'role {n} fixture contribution; not a product implementation')
        push(roles[n], f'work/test/role-{n}')
    assert checks(three, full=True).returncode != 0
    record('role_branch_cannot_claim_full_integration_without_other_roles')

    git(three, 'checkout', '-b', 'assemble/test', frozen)
    git(three, 'fetch', 'origin')
    conflict_seen = False
    for n in (1, 3, 4, 5, 2):
        p = git(three, 'merge', '--no-ff', heads[n], '-m', f'simulation: integrate role {n}', ok=False)
        if p.returncode:
            assert n == 2
            assert git(three, 'diff', '--name-only', '--diff-filter=U').stdout.strip() == 'registry.json'
            write(three, 'registry.json', '["editor", "gallery"]\n')
            commit(three, 'resolve demonstrated overlap preserving both role registrations')
            conflict_seen = True
    assert conflict_seen
    record('shared_file_conflict_reproduced_and_both_changes_preserved')
    broken_head = git(three, 'rev-parse', 'HEAD').stdout.strip()
    assert checks(three, full=True).returncode != 0
    assert git(remote, 'rev-parse', 'main').stdout.strip() == frozen
    record('contract_regression_blocks_final_base_update', candidate=broken_head)
    write(four, 'vision.py', "def analyze():\n    return {'score': .8, 'tags': ['fixture']}\n")
    heads[4] = commit(four, 'role 4 corrects injected contract regression')
    push(four, 'work/test/role-4')
    git(three, 'fetch', 'origin')
    git(three, 'merge', '--no-ff', heads[4], '-m', 'simulation: integrate corrected role 4 head')
    assert checks(three, full=True).returncode == 0
    candidate = git(three, 'rev-parse', 'HEAD').stdout.strip()
    assert candidate != broken_head
    record('author_fix_merged_and_old_review_head_invalidated', head=candidate)
    push(three, 'assemble/test')

    # Resume coordinator in a fresh checkout without uncommitted local state.
    resumed = destination / 'role-3-resumed'
    git(destination, 'clone', str(remote), str(resumed))
    identity(resumed, 3)
    git(resumed, 'checkout', 'assemble/test')
    assert git(resumed, 'rev-parse', 'HEAD').stdout.strip() == candidate
    assert checks(resumed, full=True).returncode == 0
    record('fresh_coordinator_session_resumes_exact_remote_candidate')

    # A legitimate base update makes the earlier candidate/base review stale.
    git(one, 'fetch', 'origin')
    git(one, 'checkout', '-B', 'main', 'origin/main')
    write(one, 'NOTICE.md', 'SIMULATION: base changed while candidate was being checked.\n')
    commit(one, 'base update to test stale integration detection')
    push(one, 'main')
    git(resumed, 'fetch', 'origin')
    latest_base = git(resumed, 'rev-parse', 'origin/main').stdout.strip()
    assert latest_base != frozen
    record('base_change_requires_candidate_refresh_and_review')
    git(resumed, 'merge', '--no-ff', 'origin/main', '-m', 'simulation: refresh changed base')
    assert checks(resumed, full=True).returncode == 0
    refreshed = git(resumed, 'rev-parse', 'HEAD').stdout.strip()
    assert refreshed != candidate
    push(resumed, 'assemble/test')
    assert candidate != refreshed  # review of previous head is not sufficient
    record('refreshed_candidate_retested', head=refreshed)

    git(resumed, 'checkout', '-B', 'main', 'origin/main')
    git(resumed, 'merge', '--no-ff', refreshed, '-m', 'simulation: final merge after local gates')
    assert checks(resumed, full=True).returncode == 0
    final = git(resumed, 'rev-parse', 'HEAD').stdout.strip()
    push(resumed, 'main')
    for n, head in heads.items():
        assert git(remote, 'merge-base', '--is-ancestor', head, final).returncode == 0
    record('all_five_role_commit_histories_preserved_in_final_base')
    assert git(two, 'push', 'origin', 'HEAD:main', ok=False).returncode != 0
    assert git(remote, 'rev-parse', 'main').stdout.strip() == final
    record('stale_role_push_rejected_without_overwriting_final_base')
    for n in range(1, 6):
        assert git(roles[n], 'remote', 'get-url', 'origin').stdout.strip() == str(remote)
    assert git(resumed, 'status', '--porcelain').stdout.strip() == ''
    report = {
        'scope': 'local_git_coordination_with_minimal_fixture',
        'simulated_roles': 5, 'independent_agents': False,
        'github_accounts_or_reviews_executed': False,
        'full_zzik_implementation': False, 'aws_calls': 0,
        'git_commands_and_checks': calls, 'asserted_scenarios': len(events),
        'events': events, 'final_commit': final,
        'verification_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (destination / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    verify(args.output)
