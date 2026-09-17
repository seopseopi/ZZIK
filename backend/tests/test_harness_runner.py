"""Reject unsafe integration-test targets before any connection or cleanup."""
import pytest

from scripts.run_integration import local_database


@pytest.mark.parametrize('value', [
    '',
    'not-a-url',
    'sqlite:///zzik_e2e',
    'postgresql+psycopg://test:test@example.com/zzik_e2e',
    'postgresql+psycopg://test:test@127.0.0.1/production',
    'postgresql+psycopg://test:test@127.0.0.1/zzik_e2e?host=example.com',
    'postgresql+psycopg://test:test@127.0.0.1/zzik_e2e?options=-csearch_path=public',
])
def test_rejects_unsafe_target(value):
    with pytest.raises(ValueError):
        local_database(value)


@pytest.mark.parametrize('host', ['127.0.0.1', 'localhost', '[::1]'])
def test_accepts_explicit_local_test_database(host):
    assert local_database(f'postgresql+psycopg://test:test@{host}/zzik_e2e').database == 'zzik_e2e'
