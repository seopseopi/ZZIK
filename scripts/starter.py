#!/usr/bin/env python3
"""Export a commit-only rehearsal starter; completion checks never execute learner code."""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
MARKER = 'ZZIK_STARTER:'
STATE = '.starter-state.json'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(path):
    value = PurePosixPath(path)
    require(bool(path) and bool(value.parts) and '\x00' not in path and not value.is_absolute() and '..' not in value.parts and '\\' not in path, 'Unsafe relative path')
    return value


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def python_nodes(source):
    data = source.encode()
    lines = data.splitlines(keepends=True)
    offsets, cursor = [], 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line)
    result = {}
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # FastAPI uses route docstrings in OpenAPI; retain that contract text.
            body = node.body
            if (len(body) > 1 and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
                body = body[1:]
            first, last = body[0], body[-1]
            result[node.name] = (offsets[first.lineno - 1] + first.col_offset,
                                 offsets[last.end_lineno - 1] + last.end_col_offset)
    return result


def python_edit(source, unit, reference=None):
    nodes = python_nodes(source)
    names = list(nodes) if unit['symbols'] == '*' else unit['symbols']
    require(bool(names) and len(names) == len(set(names)), 'Empty/duplicate Python symbols')
    refs = python_nodes(reference) if reference is not None else None
    data = source.encode()
    edits = []
    for name in names:
        require(name in nodes and (refs is None or name in refs), 'Missing Python function: ' + name)
        replacement = (reference.encode()[slice(*refs[name])] if refs is not None else
                       f'raise NotImplementedError("{MARKER}{unit["id"]}:{name}")'.encode())
        edits.append((*nodes[name], replacement))
    for start, end, replacement in sorted(edits, reverse=True):
        data = data[:start] + replacement + data[end:]
    ast.parse(data)
    return data.decode(), names


def ts_edit(source, unit, reference=None):
    payload = dict(source=source, path=unit['path'], id=unit['id'], symbols=unit['symbols'])
    if reference is not None:
        payload['reference'] = reference
    command = ['node', str(ROOT / 'contracts/codegen/starter.mjs')]
    result = subprocess.run(command, input=json.dumps(payload), text=True, capture_output=True)
    require(result.returncode == 0, 'TypeScript body transform failed; install contracts/codegen dependencies')
    result = json.loads(result.stdout)
    return result['source'], result['symbols']


def edit(source, unit, reference=None):
    return (python_edit if unit['kind'] == 'python' else ts_edit)(source, unit, reference)


def validate_manifest(manifest, plan):
    require(manifest['version'] == 1 and manifest['scope'] == 'local-fixture-rehearsal', 'Unsupported starter scope')
    require(re.fullmatch('[0-9a-f]{40}', manifest['reference_commit']), 'Pin the full reference commit')
    ids, assigned, roles, tasks = set(), {}, set(), set()
    task_ids = {t['id'] for t in plan['tasks']}
    for unit in manifest['units']:
        require(re.fullmatch('[a-z0-9-]+', unit['id']) and unit['id'] not in ids, 'Duplicate/invalid unit ID')
        ids.add(unit['id'])
        require(unit['role'] in range(1, 6) and set(unit['tasks']) <= task_ids and unit['tasks'], 'Invalid role/tasks')
        safe_path(unit['path'])
        require(unit['kind'] in {'python', 'typescript', 'file'}, 'Unknown unit kind')
        symbols = unit.get('symbols', '*')
        require(symbols == '*' or isinstance(symbols, list) and symbols and len(symbols) == len(set(symbols)), 'Invalid symbols')
        prior = assigned.setdefault(unit['path'], [])
        require(not prior or symbols != '*' and all(p != '*' and not set(p) & set(symbols) for p in prior), 'Overlapping ownership')
        prior.append(symbols)
        if unit['kind'] == 'file':
            safe_path(unit['template'])
        roles.add(unit['role'])
        tasks.update(unit['tasks'])
    require(roles == set(range(1, 6)) and tasks == task_ids, 'Starter must cover all 5 roles and M01-M17')
    require(set(manifest['role_checks']) == set('12345') and all(manifest['role_checks'].values()), 'Missing role checks')


def extract_commit(repo, ref, destination):
    require(not destination.exists() and not destination.is_symlink(), 'Output must be a new directory')
    require(not destination.resolve().is_relative_to(repo.resolve()), 'Export outside the source repository')
    archive = git(repo, 'archive', '--format=tar', ref)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        members = tar.getmembers()
        for member in members:
            parts = safe_path(member.name).parts
            require(member.isfile() or member.isdir(), 'Symlinks and submodules are not supported')
            require(not any(p in {'.git', '.venv', 'node_modules', 'data', 'logs', 'backups'} for p in parts), 'Private/generated file in commit')
            require(not any(p.startswith('.env') and p != '.env.example' for p in parts), 'Environment secrets must not be exported')
            require(not member.name.endswith(('.pem', '.key')), 'Key files must not be exported')
        destination.mkdir(parents=True, mode=0o700)
        for member in members:
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(tar.extractfile(member).read())
                target.chmod(0o755 if member.mode & 0o111 else 0o644)


def protected_paths(root):
    prefixes = ('backend/tests/', 'frontend/e2e/', 'backend/alembic/', 'contracts/', 'starter/',)
    names = {'backend/app/models.py', 'backend/app/schemas.py', 'backend/app/responses.py', 'frontend/src/generated/api.d.ts',
             'scripts/check_harness.py', 'scripts/run_integration.py', 'scripts/verify_backup_restore.py',
             'scripts/verify_restart.py', 'scripts/starter.py'}
    return sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink()
                  and (p.relative_to(root).as_posix() in names or p.relative_to(root).as_posix().startswith(prefixes)))


def disable_browser_demo(root):
    # Keep no second completed backend/editor implementation in the learner package.
    shutil.rmtree(root / 'frontend/src/demo')
    demo = root / 'frontend/src/demo'
    demo.mkdir()
    (demo / 'api.ts').write_text('export async function demoRequest(_path: string, _options: RequestInit): Promise<Response> { throw new Error("STARTER_DEMO_DISABLED: use the real API"); }\n')
    (demo / 'images.ts').write_text('export async function downloadDemoPhoto(_id: string, _version?: string): Promise<void> { throw new Error("STARTER_DEMO_DISABLED"); }\nexport async function downloadDemoZip(_ids: string[]): Promise<void> { throw new Error("STARTER_DEMO_DISABLED"); }\n')
    (demo / 'DemoToolbar.tsx').write_text('export default function DemoToolbar() { return null; }\n')
    for name in ('frontend/demo-e2e',):
        shutil.rmtree(root / name)
    (root / 'frontend/playwright.demo.config.ts').unlink()
    package = root / 'frontend/package.json'
    data = json.loads(package.read_text())
    data['scripts'] = {k: v for k, v in data['scripts'].items() if ':demo' not in k}
    package.write_text(json.dumps(data, indent=2) + '\n')
    for name in ('frontend/src/api.ts', 'frontend/src/main.tsx'):
        p = root / name
        s = p.read_text().replace('import.meta.env.MODE === "demo"', 'false').replace("import.meta.env.MODE==='demo'", 'false')
        p.write_text(s)


def write_handoffs(root, manifest, plan, state):
    directory = root / 'starter/roles'
    directory.mkdir(exist_ok=True)
    for role in plan['roles']:
        number = role['id']
        units = [u for u in manifest['units'] if u['role'] == number]
        tasks = [t for t in plan['tasks'] if t['owner'] == number or number in t['collaborators']]
        text = [f'# 담당 {number}: {role["title"]} — starter 인계', '',
                f'기준: `{manifest["reference_commit"]}` / 현재 프로필: `{state["profile"]}`.',
                '연습용 빈 구현이다. 원본 작업 문서의 완료 상태는 기준본의 기록이며 이 checkout의 완료 상태가 아니다.',
                'START_HERE.md → AGENTS.md → 해당 역할 프롬프트 → M 작업 프롬프트 순서로 읽는다.', '', '## 구현할 경계', '']
        for unit in units:
            text.append(f'- `{unit["id"]}`: `{unit["path"]}` / {", ".join(unit["tasks"])} / ' + ('파일 전체' if unit['kind'] == 'file' else ', '.join(unit['symbols'])))
        text += ['', '## 작업·의존 관계', '']
        for task in tasks:
            text.append(f'- [{task["id"]}](../../docs/hackathon/tasks/{task["id"]}.md): 선행 {", ".join(task["depends_on"]) or "공통 계약"}; 주관 {task["owner"]}번.')
        text += ['', '## 검사와 인계', '',
                 f'`python scripts/starter.py check --root . --role {number}`는 자신의 남은 stub과 보호 파일 변경을 검사한다. 이 검사만으로 동작 완료는 아니다.',
                 '전용 TEST_DATABASE_URL / ZZIK_E2E_DATABASE_URL 설정과 개발 환경 설치 후 아래 검사를 실행한다. full 프로필에서는 다른 역할의 미구현 의존성이 먼저 필요할 수 있다.', '', '```sh',
                 *manifest['role_checks'][str(number)], '```', '',
                 '공유 파일은 자신의 함수만 수정한다. 함수 시그니처·OpenAPI·DB·기존 전원 승인 정책을 유지한다. 스텁 문구만 지우거나 테스트/fixture를 약화해서 통과시키지 않는다.',
                 '작업 결과에 변경 함수·선행 역할·테스트 명령/결과·남은 외부 검증을 적고, 자신이 실제 수행한 커밋으로 PR을 만든다. 완성본 복사는 재구현 리허설의 증거가 아니다.', '']
        (directory / f'{number:02}.md').write_text('\n'.join(text))


def export(repo, ref, destination, profile='all'):
    commit = git(repo, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()
    manifest = json.loads(git(repo, 'show', commit + ':starter/manifest.json'))
    plan = json.loads(git(repo, 'show', commit + ':docs/hackathon/plan.json'))
    validate_manifest(manifest, plan)
    require(profile in {'all', '1', '2', '3', '4', '5'}, 'Invalid profile')
    # A tooling commit cannot silently replace the CI-verified application baseline.
    for path in {u['path'] for u in manifest['units']}:
        require(git(repo, 'show', commit + ':' + path) == git(repo, 'show', manifest['reference_commit'] + ':' + path), 'Application baseline drift: ' + path)
    extract_commit(repo, commit, destination)
    resolved, active = [], []
    for unit in manifest['units']:
        unit = dict(unit)
        target = destination / unit['path']
        source = target.read_text()
        if unit['kind'] == 'file':
            masked = (destination / unit['template']).read_text()
            require(MARKER + unit['id'] in masked, 'Template marker missing')
        else:
            masked, unit['symbols'] = edit(source, unit)
        resolved.append(unit)
        if profile == 'all' or int(profile) == unit['role']:
            target.write_text(masked)
            active.append(unit['id'])
    manifest['units'] = resolved
    disable_browser_demo(destination)
    # The learner workflow must not publish the unimplemented exercise as the demo.
    shutil.rmtree(destination / '.github/workflows')
    (destination / '.github/workflows').mkdir()
    shutil.copyfile(destination / 'starter/templates/ci.yml', destination / '.github/workflows/starter.yml')
    state = {'version': 1, 'profile': profile, 'source_commit': commit,
             'reference_commit': manifest['reference_commit'], 'scope': manifest['scope'],
             'units': resolved, 'active_units': active}
    write_handoffs(destination, manifest, plan, state)
    guide = (destination / 'starter/START_HERE.md').read_text()
    (destination / 'START_HERE.md').write_text(guide)
    (destination / 'README.md').write_text('# 찍 / ZZIK — 로컬 연습용 starter\n\n구현이 비어 있는 연습용 코드입니다. **[START_HERE.md](START_HERE.md)**부터 읽으세요.\n\n기준 코드: `' + manifest['reference_commit'] + '` / 프로필: `' + profile + '`. 운영 완료본이 아닙니다.\n')
    agents = destination / 'AGENTS.md'
    agents.write_text('# Starter 추가 규칙\n\n먼저 START_HERE.md와 starter/roles의 자기 인계를 읽는다. ZZIK_STARTER 경계만 구현하고 공통 기반·테스트를 보존한다. 브라우저 체험 모드는 이 패키지에서 비활성화되었다. 원본 문서의 완료 기록은 기준본의 기록이다.\n\n' + agents.read_text())
    state['initial_units'] = {u['path']: sha((destination / u['path']).read_bytes()) for u in resolved}
    state['protected'] = {p.relative_to(destination).as_posix(): sha(p.read_bytes()) for p in protected_paths(destination)}
    (destination / STATE).write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
    return state


def status(root, role=None):
    state = json.loads((root / STATE).read_text())
    require(state['version'] == 1, 'Unsupported starter state')
    pending, missing, changed = [], [], []
    for unit in state['units']:
        if role is not None and unit['role'] != role:
            continue
        path = root / safe_path(unit['path'])
        if not path.is_file() or path.is_symlink():
            missing.append(unit['id'])
        elif MARKER + unit['id'] in path.read_text():
            pending.append(unit['id'])
        elif unit['kind'] == 'python' and not set(unit['symbols']) <= set(python_nodes(path.read_text())):
            missing.append(unit['id'])
    for path, expected in state['protected'].items():
        source = root / safe_path(path)
        if not source.is_file() or source.is_symlink() or sha(source.read_bytes()) != expected:
            changed.append(path)
    return {'status': 'implementation_ready_for_tests' if not (pending or missing or changed) else 'incomplete',
            'profile': state['profile'], 'role': role, 'pending_units': pending, 'missing_units': missing,
            'changed_protected_files': changed, 'behavior_tests_required': True, 'aws_verified': False}


def replay_reference(repo, root):
    """Instructor-only mechanical round trip, explicitly NOT a prompt-only reimplementation."""
    state = json.loads((root / STATE).read_text())
    require(state['profile'] == 'all', 'Reference replay requires a freshly exported full starter')
    require(len(status(root)['pending_units']) == len(state['units']), 'Refuse to overwrite learner implementations')
    require(not status(root)['changed_protected_files'], 'Refuse changed protected files')
    for path, expected in state['initial_units'].items():
        target = root / safe_path(path)
        require(target.is_file() and not target.is_symlink() and sha(target.read_bytes()) == expected, 'Refuse to overwrite learner edits')
    trace = []
    for role in (1, 3, 4, 5, 2):
        for unit in state['units']:
            if unit['role'] != role:
                continue
            path = root / unit['path']
            reference = git(repo, 'show', state['reference_commit'] + ':' + unit['path']).decode()
            restored = reference if unit['kind'] == 'file' else edit(path.read_text(), unit, reference)[0]
            path.write_text(restored)
        require(not status(root, role)['pending_units'], 'Role replay incomplete')
        trace.append({'role': role, 'remaining_units': len(status(root)['pending_units'])})
    for path in {u['path'] for u in state['units']}:
        require((root / path).read_bytes() == git(repo, 'show', state['reference_commit'] + ':' + path), 'Round-trip mismatch: ' + path)
    require(status(root)['status'] == 'implementation_ready_for_tests', 'Replay changed protected files')
    return {'scope': 'mechanical_reference_reassembly', 'independent_reimplementation': False, 'trace': trace,
            'all_unit_files_equal_reference': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('export')
    build.add_argument('--ref', default='HEAD')
    build.add_argument('--output', type=Path, required=True)
    build.add_argument('--role', choices=list('12345'))
    check = commands.add_parser('check')
    check.add_argument('--root', type=Path, default=Path('.'))
    check.add_argument('--role', type=int, choices=range(1, 6))
    report = commands.add_parser('status')
    report.add_argument('--root', type=Path, default=Path('.'))
    replay = commands.add_parser('replay-reference')
    replay.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'export':
            require(not (ROOT / STATE).exists(), 'Export from the source/tooling repository, not a learner checkout')
            state = export(ROOT, args.ref, args.output.resolve(), args.role or 'all')
            result = {'status': 'exported', 'source_commit': state['source_commit'], 'profile': state['profile'], 'active_units': len(state['active_units'])}
        elif args.command == 'replay-reference':
            require(not (ROOT / STATE).exists(), 'Reference replay belongs in the instructor/source repository')
            result = replay_reference(ROOT, args.root.resolve())
        else:
            result = status(args.root.resolve(), getattr(args, 'role', None))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return int(args.command == 'check' and result['status'] != 'implementation_ready_for_tests')
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'code': str(exc) if isinstance(exc, ValueError) else type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
