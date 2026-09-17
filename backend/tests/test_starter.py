"""Safety boundaries of the commit-only exercise generator (no cloud calls)."""
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('zzik_starter', ROOT / 'scripts/starter.py')
starter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(starter)


def test_python_round_trip_preserves_unicode_signatures_and_other_role():
    source = '@decorate("찍")\nasync def first(x: str = "여행") -> str:\n    """사진"""\n    return x + "😀"\n\ndef other(): return 42\n'
    unit = {'id': 'one', 'symbols': ['first']}
    masked, names = starter.python_edit(source, unit)
    assert names == ['first']
    assert '"""사진"""' in masked
    assert 'def other(): return 42' in masked
    assert 'ZZIK_STARTER:one:first' in masked
    assert starter.python_edit(masked, unit, source)[0] == source
    one_line = {'id': 'two', 'symbols': ['other']}
    masked2, _ = starter.python_edit(masked, one_line)
    assert starter.python_edit(starter.python_edit(masked2, one_line, source)[0], unit, source)[0] == source


@pytest.mark.parametrize('path', ['.', '', '../secret', '/secret', 'a/../../b', 'a\\b', 'a\x00b'])
def test_reject_unsafe_paths(path):
    with pytest.raises(ValueError):
        starter.safe_path(path)


def repository(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True)
    git('init')
    git('config', 'user.name', 'Starter test')
    git('config', 'user.email', 'starter@example.invalid')
    (root / 'public.txt').write_text('committed')
    git('add', '.')
    git('commit', '-m', 'fixture')
    return root, git


def test_export_reads_commit_not_worktree_or_untracked_secrets(tmp_path):
    root, _ = repository(tmp_path)
    (root / 'public.txt').write_text('dirty')
    (root / '.env').write_text('private fixture')
    out = tmp_path / 'export'
    starter.extract_commit(root, 'HEAD', out)
    assert (out / 'public.txt').read_text() == 'committed'
    assert not (out / '.env').exists()
    assert not (out / '.git').exists()
    with pytest.raises(ValueError, match='new directory'):
        starter.extract_commit(root, 'HEAD', out)
    with pytest.raises(ValueError, match='outside'):
        starter.extract_commit(root, 'HEAD', root / 'child')


@pytest.mark.parametrize('kind', ['secret', 'symlink'])
def test_reject_entire_archive_before_writing(tmp_path, kind):
    root, git = repository(tmp_path)
    if kind == 'secret':
        (root / '.env').write_text('fixture')
    else:
        (root / 'link').symlink_to('public.txt')
    git('add', '.')
    git('commit', '-m', 'unsafe fixture')
    out = tmp_path / 'export'
    with pytest.raises(ValueError):
        starter.extract_commit(root, 'HEAD', out)
    assert not out.exists()


def test_manifest_all_roles_tasks_and_no_shared_function_overlap():
    manifest = json.loads((ROOT / 'starter/manifest.json').read_text())
    plan = json.loads((ROOT / 'docs/hackathon/plan.json').read_text())
    starter.validate_manifest(manifest, plan)
    manifest['units'].append({**manifest['units'][0], 'id': 'duplicate-boundary'})
    with pytest.raises(ValueError, match='Overlapping'):
        starter.validate_manifest(manifest, plan)


def test_status_checks_missing_functions_and_protected_files(tmp_path):
    (tmp_path / 'a.py').write_text('def task():\n    raise NotImplementedError("ZZIK_STARTER:a:task")\n')
    (tmp_path / 'contract').write_text('fixed')
    state = {'version': 1, 'profile': 'all', 'units': [{'id': 'a', 'role': 1, 'path': 'a.py', 'kind': 'python', 'symbols': ['task']}],
             'protected': {'contract': starter.sha(b'fixed')}, 'initial_units': {'a.py': starter.sha((tmp_path / 'a.py').read_bytes())}}
    (tmp_path / starter.STATE).write_text(json.dumps(state))
    assert starter.status(tmp_path)['pending_units'] == ['a']
    # Even if the marker is retained, an instructor replay cannot overwrite a learner's edits.
    (tmp_path / 'a.py').write_text((tmp_path / 'a.py').read_text() + '# learner work\n')
    with pytest.raises(ValueError, match='learner edits'):
        starter.replay_reference(ROOT, tmp_path)
    (tmp_path / 'a.py').write_text('def wrong(): pass\n')
    assert starter.status(tmp_path)['missing_units'] == ['a']
    (tmp_path / 'a.py').write_text('def task(): pass\n')
    assert starter.status(tmp_path)['status'] == 'implementation_ready_for_tests'
    (tmp_path / 'contract').write_text('changed')
    assert starter.status(tmp_path)['changed_protected_files'] == ['contract']
