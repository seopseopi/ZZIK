#!/usr/bin/env python3
"""Validate team inputs and produce a deterministic Kiro/Git assembly plan.

Read-only: does not implement code, create PRs, review or merge on its own.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
REVIEWERS = {'1': '3', '2': '5', '3': '1', '4': '3', '5': '2'}
ORDER = [1, 3, 4, 5, 2]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(config, manifest):
    require(config.get('version') == 1, 'Unsupported version')
    require(config.get('mode') in {'rehearsal', 'contest'}, 'Invalid mode')
    require(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config.get('repository', '')), 'Set repository as OWNER/REPO')
    base = config.get('base_branch', '')
    require(bool(base) and not base.startswith('-'), 'Set the provided integration target branch')
    require(subprocess.run(['git', 'check-ref-format', '--branch', base], capture_output=True).returncode == 0, 'Invalid base branch')
    run = config.get('run_id', '')
    require(re.fullmatch(r'[a-z0-9][a-z0-9-]{0,39}', run), 'Invalid run_id')
    require(config.get('starter_import_allowed') is True and bool(config.get('rules_reference', '').strip()), 'Record confirmed starter-import permission and its source')
    roles = config.get('roles', {})
    require(set(roles) == set('12345'), 'Assign all five roles')
    require(all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})', v) for v in roles.values()), 'Set actual GitHub logins')
    if config['mode'] == 'contest':
        require(len({v.lower() for v in roles.values()}) == 5, 'Contest plan requires five actual distinct role owners')
    require({u['role'] for u in manifest['units']} == set(range(1, 6)), 'Incomplete role manifest')
    for number in range(1, 6):
        require(base not in {f'work/{run}/role-{number}', f'assemble/{run}'}, 'Base must differ from generated branches')
    return config


def repository_name(remote):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', remote)
    require(match is not None, 'origin must be an explicit GitHub SSH/HTTPS repository without embedded credentials')
    return match[1]


def plan(config, manifest):
    validate(config, manifest)
    run = config['run_id']
    return {
        'scope': 'kiro_execution_instructions_not_background_automation',
        'repository': config['repository'], 'base_branch': config['base_branch'],
        'assembly_branch': f'assemble/{run}', 'coordinator_role': 3,
        'candidate_merge_order': ORDER, 'final_merge_method': 'merge-commit',
        'aws_execution_allowed': False,
        'distinct_role_accounts': len({v.lower() for v in config['roles'].values()}),
        'roles': [{
            'role': n, 'owner': config['roles'][str(n)],
            'branch': f'work/{run}/role-{n}',
            'reviewer_role': int(REVIEWERS[str(n)]),
            'reviewer': config['roles'][REVIEWERS[str(n)]],
            'units_in_order': [u['id'] for u in manifest['units'] if u['role'] == n],
            'commit_rule': 'one_coherent_tested_change; no_empty_or_quota_commits',
            'handoff': f'starter/roles/{n:02}.md',
        } for n in range(1, 6)],
        'final_gates': ['all_30_units_implemented', 'contracts_and_types', 'backend_tests',
                        'frontend_build', 'real_api_e2e', 'compose_restart', 'backup_restore',
                        'review_exact_role_heads_and_candidate', 'all_required_github_checks_and_reviews'],
    }


def preflight(config, manifest, role):
    result = plan(config, manifest)
    def output(*command):
        return subprocess.check_output(command, cwd=ROOT, stderr=subprocess.PIPE, text=True).strip()
    actual = repository_name(output('git', 'remote', 'get-url', 'origin'))
    require(actual.lower() == config['repository'].lower(), 'origin differs from configured official/rehearsal repository; do not redirect automatically')
    require(not output('git', 'status', '--porcelain'), 'Commit or resolve local changes before assembly')
    login = output('gh', 'api', 'user', '--jq', '.login')
    require(login.lower() == config['roles'][str(role)].lower(), 'Authenticated account does not match this role')
    repo = json.loads(output('gh', 'api', f'repos/{actual}'))
    require(repo.get('permissions', {}).get('push') is True, 'No repository push permission')
    require(output('git', 'ls-remote', '--heads', 'origin', config['base_branch']), 'Configured base branch does not exist on origin')
    result.update(preflight='passed', role=role, note='Branch protection and exact-head review/check gates still apply at merge time')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'preflight'])
    parser.add_argument('--config', type=Path, default=ROOT / '.zzik-assembly.json')
    parser.add_argument('--role', type=int, choices=range(1, 6))
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text())
        manifest = json.loads((ROOT / 'starter/manifest.json').read_text())
        if args.command == 'preflight':
            require(args.role is not None, 'preflight requires --role')
            result = preflight(config, manifest, args.role)
        else:
            result = plan(config, manifest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'blocked', 'reason': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
