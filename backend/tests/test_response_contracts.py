"""Contract failures must be caught without changing successful wire payloads."""
from copy import deepcopy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.exceptions import ResponseValidationError
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.app.main import app, invalid_response
from backend.app.responses import PersonResponse, SessionResponse, VersionResponse
from scripts.check_harness import validate_response_contracts


def test_every_api_success_and_error_is_described():
    schema = app.openapi()
    validate_response_contracts(schema)
    for path in ('/api/photos/{photo_id}/file', '/api/people/{person_id}/reference', '/api/versions/{version_id}/file'):
        responses = schema['paths'][path]['get']['responses']
        assert 'application/json' not in responses['200']['content']
        assert 'image/jpeg' in responses['200']['content'] and '307' in responses
    assert 'application/zip' in schema['paths']['/api/albums/{album_id}/download']['get']['responses']['200']['content']
    assert schema['paths']['/api/photos/{photo_id}']['get']['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/PhotoDetailResponse')


def test_contract_check_rejects_untyped_route():
    schema = deepcopy(app.openapi())
    schema['paths']['/api/auth/me']['get']['responses']['200']['content']['application/json']['schema'] = {}
    with pytest.raises(ValueError, match='Untyped response'):
        validate_response_contracts(schema)


def test_contract_check_rejects_inaccurate_error_shape():
    schema = deepcopy(app.openapi())
    schema['paths']['/api/auth/me']['get']['responses']['422'] = {'description': 'validation error'}
    with pytest.raises(ValueError, match='Error envelope mismatch'):
        validate_response_contracts(schema)


def test_nullable_is_required_and_omitted_photo_source_stays_omitted():
    data = dict(id='p', name='Person', user_id=None, proposed_user_id=None, reference_url=None, link_status='unlinked')
    assert PersonResponse.model_validate(data).model_dump(mode='json', exclude_unset=True) == data
    with pytest.raises(ValidationError):
        PersonResponse.model_validate({k: v for k, v in data.items() if k != 'user_id'})
    with pytest.raises(ValidationError):
        PersonResponse.model_validate(dict(data, private_reference_key='private'))


def test_author_does_not_require_email_and_dates_keep_wire_format():
    data = dict(id='v', photo_id='p', number=1, name='edit', parent_id=None, author={'id': 'u', 'name': 'Author'},
                created_at=datetime(2026, 9, 17, tzinfo=timezone.utc), brightness=1.0, saturation=1.0,
                renderer_version='v1', preview_url='/api/versions/v/file', review_requested=False, needs_review=False,
                review_reason=None, targets=[], approval_count=0, target_count=0, consensus=False, is_final=False, comments=[])
    encoded = VersionResponse.model_validate(data).model_dump(mode='json', exclude_unset=True)
    assert encoded == dict(data, created_at='2026-09-17T00:00:00+00:00')
    assert 'email' not in encoded['author']


def test_invalid_response_returns_generic_500_without_logging_secret_values(caplog):
    sample = FastAPI()
    sample.add_exception_handler(ResponseValidationError, invalid_response)
    @sample.get('/broken', response_model=SessionResponse)
    def broken():
        return {'user': {'id': 'u'}, 'csrf_token': 'do-not-log-this-session-secret'}
    with TestClient(sample) as client:
        response = client.get('/broken')
    assert response.status_code == 500
    assert response.json()['code'] == 'INTERNAL_ERROR'
    assert 'do-not-log-this-session-secret' not in caplog.text + response.text
    assert 'Response contract violation' in caplog.text
