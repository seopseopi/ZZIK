#!/usr/bin/env python3
"""Check work-package dependencies, source paths, API and Python call boundaries."""
import argparse
import difflib
import importlib
import inspect
import json
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def validate_plan(plan):
    tasks = plan['tasks']
    ids = [task['id'] for task in tasks]
    if ids != [f'M{i:02}' for i in range(1, 18)]:
        raise ValueError('Task IDs must be M01 through M17 exactly once, in order.')
    by_id = {task['id']: task for task in tasks}
    roles = {str(role['id']) for role in plan['roles']}
    if roles != {'1', '2', '3', '4', '5'}:
        raise ValueError('Expected exactly five team roles.')
    checked, visiting = set(), set()

    def visit(task_id):
        if task_id in visiting:
            raise ValueError(f'Dependency cycle at {task_id}.')
        if task_id in checked:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id]['depends_on']:
            if dependency not in by_id:
                raise ValueError(f'Unknown dependency {dependency}.')
            visit(dependency)
        visiting.remove(task_id)
        checked.add(task_id)

    for task in tasks:
        visit(task['id'])
        if str(task['owner']) not in roles or any(str(role) not in roles for role in task['collaborators']):
            raise ValueError(f'Invalid owner/collaborator in {task["id"]}.')
        if not task['acceptance'] or not task['validation']:
            raise ValueError(f'Missing completion checks in {task["id"]}.')
        for path in [task['prompt'], *task['files']]:
            if not (ROOT / path).is_file():
                raise ValueError(f'Missing referenced file: {path}')
    for role in plan['roles']:
        for path in [role['prompt'], *role['files']]:
            if not (ROOT / path).is_file():
                raise ValueError(f'Missing role file: {path}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write-contract', action='store_true', help='Update OpenAPI snapshot after reviewing the API change.')
    args = parser.parse_args()
    plan = json.loads((ROOT / 'docs/hackathon/plan.json').read_text())
    validate_plan(plan)
    subprocess.run([sys.executable, str(ROOT / 'scripts/render_hackathon_prompts.py'), '--check'], check=True)
    from backend.app.main import app
    schema = app.openapi()
    schema = {**schema, 'paths': {path: operations for path, operations in schema['paths'].items() if path.startswith('/api/')}}
    rendered = json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    destination = ROOT / 'contracts/openapi.json'
    if args.write_contract:
        destination.write_text(rendered)
        print('Updated contracts/openapi.json; review before committing.')
    elif not destination.exists() or destination.read_text() != rendered:
        previous = destination.read_text() if destination.exists() else ''
        diff = ''.join(difflib.unified_diff(previous.splitlines(True), rendered.splitlines(True), fromfile='saved OpenAPI', tofile='current OpenAPI'))
        print(diff[:16000])
        raise ValueError('API contract changed. Review consumers, then use --write-contract.')
    for boundary in json.loads((ROOT / 'contracts/python-interfaces.json').read_text())['interfaces']:
        target = importlib.import_module(boundary['module'])
        for name in boundary['symbol'].split('.'):
            target = getattr(target, name)
        actual = [name for name in inspect.signature(target).parameters if name != 'self']
        if actual != boundary['parameters']:
            raise ValueError(f'Python interface changed: {boundary["module"]}.{boundary["symbol"]}: {actual}')
    for task in plan['tasks']:
        for endpoint in task['endpoints']:
            method, path = endpoint.split(' ', 1)
            if method.lower() not in schema['paths'].get(path, {}):
                raise ValueError(f'{task["id"]} references missing endpoint: {endpoint}')
    print(f'Harness passed: {len(plan["roles"])} roles, {len(plan["tasks"])} tasks, dependency graph, paths, API snapshot and Python signatures.')
    print('Scope: this checks declared interfaces; real response behavior requires the server integration tests.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, AttributeError, FileNotFoundError) as error:
        print(f'Harness check failed: {error}', file=sys.stderr)
        sys.exit(1)
