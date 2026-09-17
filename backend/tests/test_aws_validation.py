"""AWS validation safeguards: no network in plan mode and exact-object cleanup."""
import io
import json
from contextlib import closing
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.exceptions import ClientError
from PIL import Image

from backend.app import analysis, storage
from scripts import validate_aws as check


@pytest.fixture
def dataset(tmp_path):
    for name, color in [('ref.png', 'red'), ('photo.png', 'blue')]:
        Image.new('RGB', (100, 100), color).save(tmp_path / name)
    doc = {'version': 1, 'references': [{'id': 'person_a', 'file': 'ref.png'}],
           'photos': [{'id': 'photo_a', 'file': 'photo.png', 'expected_people': ['person_a'], 'expected_face_count': 1}]}
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(doc))
    return path, doc


def test_plan_validates_dataset_without_aws(dataset, monkeypatch, capsys):
    monkeypatch.setattr(boto3, 'Session', lambda **_: pytest.fail('Plan made AWS session'))
    monkeypatch.setattr(boto3, 'client', lambda *a, **k: pytest.fail('Plan made AWS client'))
    path, _ = dataset
    assert check.main(['--manifest', str(path), '--region', 'us-east-1', '--max-calls', '4']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['status'] == 'planned' and report['rekognition_calls'] == 0
    assert report['plan']['rekognition_calls_upper_bound'] == 4
    assert not report['photo_analysis_verified']
    assert check.main(['--manifest', str(path), '--max-calls', '3']) == 1
    assert json.loads(capsys.readouterr().out)['code'] == 'CALL_BUDGET_EXCEEDED'


@pytest.mark.parametrize('case,code', [('duplicate', 'DUPLICATE_IMAGE_OR_REFERENCE_LEAKAGE'),
    ('outside', 'IMAGE_PATH_OUTSIDE_DATASET'), ('unknown', 'EXPECTED_PEOPLE_INVALID'),
    ('boolean', 'EXPECTED_FACE_COUNT_INVALID')])
def test_dataset_rejects_leakage_escape_and_bad_labels(dataset, case, code):
    path, doc = dataset
    if case == 'duplicate':
        doc['photos'][0]['file'] = 'ref.png'
    elif case == 'outside':
        (path.parent / 'escape.png').symlink_to(path.parent.parent / 'outside.png')
        doc['photos'][0]['file'] = 'escape.png'
    elif case == 'unknown':
        doc['photos'][0]['expected_people'] = ['not_registered']
    else:
        doc['photos'][0]['expected_face_count'] = True
    path.write_text(json.dumps(doc))
    with pytest.raises(check.ValidationError) as exc:
        check.load_dataset(path)
    assert exc.value.code == code


def test_report_never_overwrites_input_and_redacts_errors(dataset, monkeypatch, capsys):
    path, _ = dataset
    original = path.read_bytes()
    def fail(*args):
        raise RuntimeError('SECRET_PASSWORD https://signed.example/?SECRET_TOKEN')
    monkeypatch.setattr(check, 'execute', fail)
    assert check.main(['--manifest', str(path), '--execute', '--bucket', 'test-private', '--report', str(path)]) == 1
    output = capsys.readouterr().out
    assert 'SECRET_' not in output and 'signed.example' not in output
    assert json.loads(output)['code'] == 'REPORT_WRITE_FAILED'
    assert path.read_bytes() == original


def test_metrics_keep_failed_photos_in_denominator():
    metrics = check.summarize([
        {'status': 'completed', 'expected_people': ['a'], 'predicted_people': ['a', 'b'],
         'face_count': 3, 'expected_face_count': 3, 'unknown_faces': 1, 'elapsed_ms': 10},
        {'status': 'failed', 'expected_people': ['a'], 'expected_face_count': 1},
        {'status': 'completed', 'expected_people': [], 'predicted_people': [],
         'face_count': 0, 'expected_face_count': 0, 'unknown_faces': 0, 'elapsed_ms': 30}])
    assert metrics['person_presence'] == {'tp': 1, 'fp': 1, 'fn': 1, 'precision': .5, 'recall': .5}
    assert metrics['exact_people_accuracy'] == .333333
    assert metrics['face_count_accuracy'] == .666667
    assert metrics['unknown_face_fraction'] == .333333
    assert metrics['successful_photo_elapsed_ms'] == {'p50': 10, 'p95': 30}
    assert check.summarize([])['person_presence']['precision'] is None


class FakeS3:
    def __init__(self, *, put_failure=False, versioning=None, delete_failure=False):
        self.objects, self.events = {}, []
        self.put_failure, self.versioning, self.delete_failure = put_failure, versioning, delete_failure
    def get_bucket_location(self, **kw):
        return {'LocationConstraint': None}
    def get_public_access_block(self, **kw):
        return {'PublicAccessBlockConfiguration': dict.fromkeys(
            ['BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'], True)}
    def get_bucket_versioning(self, **kw):
        return {'Status': self.versioning} if self.versioning else {}
    def head_object(self, **kw):
        if kw['Key'] not in self.objects:
            raise ClientError({'Error': {'Code': '404'}}, 'HeadObject')
        return {}
    def put_object(self, **kw):
        self.events.append(('put', kw['Key']))
        assert kw['ServerSideEncryption'] == 'AES256'
        self.objects[kw['Key']] = kw['Body']
        if self.put_failure:
            raise RuntimeError('Ambiguous timeout with SECRET')
    def get_object(self, **kw):
        return {'Body': io.BytesIO(self.objects[kw['Key']])}
    def delete_object(self, **kw):
        self.events.append(('delete', kw['Key']))
        if self.delete_failure:
            raise RuntimeError('SECRET')
        self.objects.pop(kw['Key'], None)
    def generate_presigned_url(self, *a, **kw):
        return 'https://example.invalid/?SECRET_SIGNATURE'


def test_storage_probe_verifies_original_and_removes_only_own_object(monkeypatch):
    import httpx
    class HTTP:
        def __init__(self, **kw):
            assert kw == {'timeout': 30, 'follow_redirects': False, 'trust_env': False}
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url):
            return SimpleNamespace(status_code=200, content=b'original', headers={'content-disposition': 'attachment'})
    monkeypatch.setattr(httpx, 'Client', HTTP)
    client = FakeS3()
    client.objects['existing-original'] = b'preserve'
    result = check.storage_probe(client, 'private', 'us-east-1', {'data': b'original', 'mime': 'image/png'}, 'unique-run')
    assert result == {'status': 'passed', 'cleanup': 'passed', 'original_hash_verified': True, 'signed_download_verified': True}
    assert client.objects == {'existing-original': b'preserve'}
    assert client.events == [('put', 'zzik-validation/unique-run/original'), ('delete', 'zzik-validation/unique-run/original')]


@pytest.mark.parametrize('delete_failure', [False, True])
def test_ambiguous_put_is_cleaned_up_or_reports_exact_remaining_key(delete_failure):
    client = FakeS3(put_failure=True, delete_failure=delete_failure)
    result = check.storage_probe(client, 'private', 'us-east-1', {'data': b'original', 'mime': 'image/png'}, 'unique-run')
    assert result['status'] == 'failed'
    assert result['cleanup'] == ('failed' if delete_failure else 'passed')
    assert 'SECRET' not in json.dumps(result)
    if delete_failure:
        assert result['remaining_key'] == 'zzik-validation/unique-run/original'
    else:
        assert not client.objects


@pytest.mark.parametrize('versioning', ['Enabled', 'Suspended'])
def test_versioned_bucket_is_rejected_before_write(versioning):
    client = FakeS3(versioning=versioning)
    result = check.storage_probe(client, 'private', 'us-east-1', {'data': b'x', 'mime': 'image/png'}, 'run')
    assert result['code'] == 'UNVERSIONED_TEST_BUCKET_REQUIRED'
    assert not client.events


def test_default_s3_adapter_uses_v4_and_caps_download_expiry(monkeypatch):
    real_client = boto3.client
    def client(service, **kwargs):
        assert kwargs['config'].signature_version == 's3v4'
        return real_client(service, aws_access_key_id='TEST_ONLY', aws_secret_access_key='TEST_ONLY', **kwargs)
    monkeypatch.setattr(boto3, 'client', client)
    with closing(storage.S3Storage('example-bucket', prefix='validation').client) as sdk:
        adapter = storage.S3Storage('example-bucket', client=sdk, prefix='validation')
        query = parse_qs(urlparse(adapter.signed_url('original', expires_in=900, filename='photo.png')).query)
        assert query['X-Amz-Algorithm'] == ['AWS4-HMAC-SHA256']
        assert query['X-Amz-Expires'] == ['300']
        assert query['response-content-disposition'] == ["attachment; filename*=UTF-8''photo.png"]
    with pytest.raises(ValueError):
        storage.S3Storage('bucket', client=object(), prefix='../bad')


def test_s3_forbidden_is_not_misreported_as_missing():
    class Denied:
        def head_object(self, **kw):
            raise ClientError({'Error': {'Code': '403'}}, 'HeadObject')
    with pytest.raises(ClientError):
        storage.S3Storage('private', client=Denied()).exists('original')


@pytest.mark.parametrize('count,code', [(0, 'NO_FACE'), (2, 'MULTIPLE_FACES')])
def test_invalid_live_reference_still_counts_paid_call(dataset, monkeypatch, count, code):
    monkeypatch.setattr(analysis, 'rekognition_client', lambda: SimpleNamespace(detect_faces=lambda **kw: {'FaceDetails': [{}] * count}))
    with check.live_settings('us-east-1'):
        with pytest.raises(analysis.AnalysisError) as exc:
            analysis.validate_reference((dataset[0].parent / 'ref.png').read_bytes())
    assert exc.value.code == code and exc.value.calls == 1


@pytest.mark.parametrize('failure', [None, 'reference', 'photo'])
def test_live_runner_uses_real_adapter_contract_without_context_manager_clients(dataset, monkeypatch, capsys, failure):
    closed = []
    class Client:
        def __init__(self, service): self.service = service
        def get_caller_identity(self): return {'Account': 'SECRET_ACCOUNT'}
        def close(self): closed.append(self.service)
    monkeypatch.setattr(boto3, 'Session', lambda **kw: SimpleNamespace(client=lambda service, **kw: Client(service)))
    monkeypatch.setattr(check, 'storage_probe', lambda *a: {'status': 'passed', 'cleanup': 'passed'})
    def reference(*a):
        assert analysis.settings.face_analysis_provider == 'rekognition'
        assert analysis.settings.aws_region == 'us-east-1'
        if failure == 'reference':
            raise analysis.AnalysisError('AWS_AccessDeniedException', 'SECRET_ARN', calls=1)
        return {'calls': 1}
    def analyze(*a):
        if failure == 'photo':
            raise analysis.AnalysisError('AWS_AccessDeniedException', 'SECRET_ARN', calls=1)
        return {'provider': 'rekognition', 'mode': 'live', 'calls': 3, 'faces': [{'person_id': 'person_a'}],
                'face_count': 1, 'unknown_faces': 0, 'elapsed_ms': 10}
    monkeypatch.setattr(analysis, 'validate_reference', reference)
    monkeypatch.setattr(analysis, 'analyze', analyze)
    before = analysis.settings.face_analysis_provider, analysis.settings.aws_region
    result = check.main(['--manifest', str(dataset[0]), '--execute', '--bucket', 'private', '--region', 'us-east-1'])
    output = capsys.readouterr().out
    report = json.loads(output)
    assert 'SECRET_' not in output
    assert closed == ['sts', 's3']
    assert (analysis.settings.face_analysis_provider, analysis.settings.aws_region) == before
    assert result == (1 if failure else 0)
    if failure == 'reference':
        assert report['rekognition_calls'] == 1 and report['status'] == 'blocked'
        assert report['reference_failure']['code'] == 'AWS_AccessDeniedException'
    elif failure == 'photo':
        assert report['rekognition_calls'] == 2 and report['status'] == 'failed'
        assert report['metrics']['person_presence']['fn'] == 1
        assert not report['photo_analysis_verified']
    else:
        assert report['rekognition_calls'] == 4 and report['status'] == 'passed'
        assert report['photo_analysis_verified']
