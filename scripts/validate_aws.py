#!/usr/bin/env python3
"""Plan locally or explicitly validate existing S3/Rekognition with a small dataset.

No DB, fixture fallback, resource provisioning, or collection creation. The live
run uses an existing private unversioned test bucket and removes only its own key.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app import analysis
from backend.app.config import settings
from backend.app.image_service import ImageError, inspect_image
from backend.app.storage import S3Storage


class ValidationError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise ValidationError(code)


def load_dataset(manifest: Path):
    """Read bounded local files before any SDK client or remote call exists."""
    require(manifest.stat().st_size <= 128 * 1024, 'MANIFEST_TOO_LARGE')
    doc = json.loads(manifest.read_text())
    require(isinstance(doc, dict) and doc.get('version') == 1, 'MANIFEST_VERSION_INVALID')
    kind = doc.get('dataset_kind', 'unspecified')
    require(kind in ('synthetic', 'real', 'unspecified'), 'DATASET_KIND_INVALID')
    root = manifest.resolve().parent
    refs, photos = doc.get('references'), doc.get('photos')
    require(isinstance(refs, list) and 1 <= len(refs) <= 8, 'REFERENCE_COUNT_INVALID')
    require(isinstance(photos, list) and 1 <= len(photos) <= 20, 'PHOTO_COUNT_INVALID')
    ids, hashes, loaded = set(), set(), []
    total_bytes = 0
    for item in [*refs, *photos]:
        require(isinstance(item, dict), 'MANIFEST_ITEM_INVALID')
        identifier = item.get('id')
        require(isinstance(identifier, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,39}', identifier), 'ITEM_ID_INVALID')
        require(identifier not in ids, 'DUPLICATE_ID')
        ids.add(identifier)
        value = item.get('file')
        require(isinstance(value, str) and value and not Path(value).is_absolute(), 'IMAGE_PATH_INVALID')
        path = (root / value).resolve()
        require(path.is_relative_to(root), 'IMAGE_PATH_OUTSIDE_DATASET')
        size = path.stat().st_size
        require(0 < size <= settings.max_upload_bytes, 'IMAGE_SIZE_LIMIT')
        total_bytes += size
        require(total_bytes <= 100 * 1024 * 1024, 'DATASET_SIZE_LIMIT')
        data = path.read_bytes()
        meta = inspect_image(data)
        # Also validates normalized AWS size limits without sending image bytes.
        analysis.analysis_bytes(data)
        require(meta['sha256'] not in hashes, 'DUPLICATE_IMAGE_OR_REFERENCE_LEAKAGE')
        hashes.add(meta['sha256'])
        loaded.append({'id': identifier, 'data': data, 'mime': meta['mime']})
    ref_ids = {row['id'] for row in loaded[:len(refs)]}
    for item, row in zip(photos, loaded[len(refs):]):
        people, count = item.get('expected_people'), item.get('expected_face_count')
        require(isinstance(people, list) and all(isinstance(p, str) for p in people), 'EXPECTED_PEOPLE_INVALID')
        require(len(people) == len(set(people)) and set(people) <= ref_ids, 'EXPECTED_PEOPLE_INVALID')
        require(type(count) is int and len(people) <= count <= 100, 'EXPECTED_FACE_COUNT_INVALID')
        row.update(expected_people=people, expected_face_count=count)
    return loaded[:len(refs)], loaded[len(refs):], kind


@contextmanager
def live_settings(region):
    previous = settings.face_analysis_provider, settings.aws_region
    settings.face_analysis_provider, settings.aws_region = 'rekognition', region
    try:
        yield
    finally:
        settings.face_analysis_provider, settings.aws_region = previous


def error_code(exc):
    # Never expose provider messages, URLs, credentials, filenames, or raw IDs.
    if isinstance(exc, (ValidationError, ImageError)):
        return exc.code
    if isinstance(exc, analysis.AnalysisError):
        if exc.code in {'NO_FACE', 'MULTIPLE_FACES', 'IMAGE_TOO_SMALL', 'ANALYSIS_IMAGE_TOO_LARGE'}:
            return exc.code
        provider_code = exc.code.removeprefix('AWS_')
        return safe_aws_code(provider_code, 'AWS_ANALYSIS_FAILED')
    provider_code = getattr(exc, 'response', {}).get('Error', {}).get('Code', type(exc).__name__)
    return safe_aws_code(provider_code, 'AWS_OR_LOCAL_OPERATION_FAILED')


def safe_aws_code(code, fallback):
    # Allowlisted machine codes are useful for permissions troubleshooting;
    # arbitrary SDK messages and exception names must never reach reports.
    if code in {'AccessDenied', 'AccessDeniedException', 'NoCredentialsError',
                'ExpiredToken', 'ExpiredTokenException', 'NoSuchBucket',
                'ThrottlingException', 'EndpointConnectionError', 'ReadTimeoutError'}:
        return 'AWS_' + code
    return fallback


def check_bucket(client, bucket, region, expected_account=None):
    """Read bucket configuration only; no object access or mutation."""
    params = {'Bucket': bucket}
    if expected_account:
        params['ExpectedBucketOwner'] = expected_account
    location = client.get_bucket_location(**params).get('LocationConstraint')
    actual_region = {'EU': 'eu-west-1', None: 'us-east-1'}.get(location, location)
    require(actual_region == region, 'BUCKET_REGION_MISMATCH')
    public = client.get_public_access_block(**params)['PublicAccessBlockConfiguration']
    require(all(public.get(name) is True for name in (
        'BlockPublicAcls', 'IgnorePublicAcls', 'BlockPublicPolicy', 'RestrictPublicBuckets'
    )), 'BUCKET_PUBLIC_ACCESS_BLOCK_REQUIRED')
    versioning = client.get_bucket_versioning(**params)
    require(not versioning.get('Status'), 'UNVERSIONED_TEST_BUCKET_REQUIRED')
    return {'status': 'passed', 'region_verified': True, 'public_access_block_verified': True,
            'unversioned_verified': True, 'owner_verified': bool(expected_account)}


def storage_probe(client, bucket, region, photo, run_id, *, expected_account=None):
    """Verify one original through the production adapter; never sweep a prefix."""
    import httpx

    result = {'status': 'failed', 'cleanup': 'not_needed'}
    store = S3Storage(bucket, client=client, prefix=f'zzik-validation/{run_id}')
    key, attempted = 'original', False
    try:
        check_bucket(client, bucket, region, expected_account)
        require(not store.exists(key), 'VALIDATION_KEY_ALREADY_EXISTS')
        attempted = True  # A timed-out PUT may still have created the object.
        store.put(key, photo['data'], photo['mime'])
        digest = hashlib.sha256(photo['data']).digest()
        require(hashlib.sha256(store.get(key)).digest() == digest, 'S3_ORIGINAL_HASH_MISMATCH')
        url = store.signed_url(key, filename='zzik-validation-original')
        # Do not log this bearer URL or follow a redirect to a different endpoint.
        with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as http:
            response = http.get(url)
            require(response.status_code == 200, 'SIGNED_DOWNLOAD_FAILED')
            require(hashlib.sha256(response.content).digest() == digest, 'SIGNED_DOWNLOAD_HASH_MISMATCH')
            require('attachment' in response.headers.get('content-disposition', ''), 'DOWNLOAD_HEADER_MISSING')
        result.update(status='passed', original_hash_verified=True, signed_download_verified=True)
    except Exception as exc:
        result['code'] = error_code(exc)
    finally:
        if attempted:
            try:
                store.delete(key)
                require(not store.exists(key), 'S3_CLEANUP_INCOMPLETE')
                result['cleanup'] = 'passed'
            except Exception:
                result.update(status='failed', cleanup='failed', code='S3_CLEANUP_FAILED')
                # Recovery identifies this run's exact object without disclosing the bucket.
                result['remaining_key'] = f'zzik-validation/{run_id}/{key}'
    return result


def summarize(rows):
    tp = fp = fn = exact = faces_correct = detected = unknown = 0
    elapsed = []
    for row in rows:
        expected = set(row['expected_people'])
        actual = set(row.get('predicted_people', []))
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
        if row['status'] == 'completed':
            exact += actual == expected
            faces_correct += row['face_count'] == row['expected_face_count']
            detected += row['face_count']
            unknown += row['unknown_faces']
            elapsed.append(row['elapsed_ms'])
    def ratio(n, d):
        return round(n / d, 6) if d else None
    def percentile(fraction):
        return sorted(elapsed)[max(0, math.ceil(len(elapsed) * fraction) - 1)] if elapsed else None
    return {
        'photos': len(rows), 'completed': len(elapsed), 'failed': len(rows) - len(elapsed),
        'person_presence': {'tp': tp, 'fp': fp, 'fn': fn, 'precision': ratio(tp, tp + fp), 'recall': ratio(tp, tp + fn)},
        'exact_people_accuracy': ratio(exact, len(rows)), 'face_count_accuracy': ratio(faces_correct, len(rows)),
        'unknown_face_fraction': ratio(unknown, detected),
        'successful_photo_elapsed_ms': {'p50': percentile(.5), 'p95': percentile(.95)},
    }


def execute(refs, photos, bucket, region, report, *, expected_role=None, expected_account=None,
            preflight=False, analysis_only=False):
    import boto3
    from botocore.config import Config

    session = boto3.Session(region_name=region)
    if expected_role:
        credentials = session.get_credentials()
        require(credentials is not None and credentials.method == 'iam-role', 'EC2_INSTANCE_ROLE_REQUIRED')
    config = Config(connect_timeout=5, read_timeout=30,
                    retries={'mode': 'standard', 'total_max_attempts': 1})
    # This does not require ListCollections, which is unrelated to reference matching.
    with closing(session.client('sts', config=config)) as identity:
        caller = identity.get_caller_identity()
    if expected_account:
        require(caller.get('Account') == expected_account, 'AWS_ACCOUNT_MISMATCH')
        report['account_verified'] = True
    if expected_role:
        arn = caller.get('Arn', '').split(':', 5)
        resource = arn[5].split('/') if len(arn) == 6 else []
        require(len(arn) == 6 and arn[:3] == ['arn', 'aws', 'sts']
                and len(resource) == 3 and resource[0] == 'assumed-role'
                and resource[1] == expected_role and bool(resource[2]), 'EC2_ROLE_MISMATCH')
        report['instance_role_verified'] = True
    report['identity_verified'] = True
    if analysis_only:
        report['storage'] = {'status': 'not_tested', 'reason': 'analysis_only', 'cleanup': 'not_needed'}
        analyze_dataset(refs, photos, region, report)
        if report['status'] == 'passed':
            report['status'] = 'analysis_passed'
        return
    with closing(session.client('s3', config=config.merge(Config(signature_version='s3v4')))) as client:
        if preflight:
            report['bucket_configuration'] = check_bucket(client, bucket, region, expected_account)
            report.update(status='preflight_passed', storage={'status': 'not_tested', 'cleanup': 'not_needed'})
            return
        report['storage'] = storage_probe(client, bucket, region, photos[0], report['run_id'],
                                          expected_account=expected_account)
    if report['storage']['status'] != 'passed':
        return
    analyze_dataset(refs, photos, region, report)


def analyze_dataset(refs, photos, region, report):
    """Run the production analysis functions; no bucket, collection or DB writes."""
    with live_settings(region):
        for ref in refs:
            try:
                result = analysis.validate_reference(ref['data'])
                report['rekognition_calls'] += result['calls']
            except analysis.AnalysisError as exc:
                report['rekognition_calls'] += exc.calls
                report['reference_failure'] = {'id': ref['id'], 'code': error_code(exc)}
                return
        for photo in photos:
            row = {key: photo[key] for key in ('id', 'expected_people', 'expected_face_count')}
            try:
                result = analysis.analyze(photo['data'], refs)
                require(result['provider'] == 'rekognition' and result['mode'] == 'live', 'LIVE_PROVIDER_REQUIRED')
                report['rekognition_calls'] += result['calls']
                row.update(status='completed', predicted_people=sorted({face['person_id'] for face in result['faces'] if face['person_id']}),
                           face_count=result['face_count'], unknown_faces=result['unknown_faces'], elapsed_ms=result['elapsed_ms'],
                           tags=result.get('tags', []))
            except analysis.AnalysisError as exc:
                report['rekognition_calls'] += exc.calls
                row.update(status='failed', code=error_code(exc))
            except Exception as exc:
                row.update(status='failed', code=error_code(exc))
            report['photos'].append(row)
    report['metrics'] = summarize(report['photos'])
    metrics = report['metrics']
    report['photo_analysis_verified'] = metrics['failed'] == 0
    report['dataset_expectations_matched'] = metrics['exact_people_accuracy'] == 1 and metrics['face_count_accuracy'] == 1
    report['status'] = 'passed' if report['photo_analysis_verified'] and report['dataset_expectations_matched'] else 'failed'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--execute', action='store_true', help='Send dataset images to existing AWS services; default only checks local inputs.')
    mode.add_argument('--preflight', action='store_true', help='Read identity and bucket configuration only; no uploads or Rekognition calls.')
    parser.add_argument('--analysis-only', action='store_true',
                        help='Explicitly skip all S3 checks; --execute sends images to Rekognition. Requires --expected-account for live runs.')
    parser.add_argument('--bucket', default=settings.s3_bucket)
    parser.add_argument('--region', default=settings.aws_region)
    parser.add_argument('--max-calls', type=int, default=200, help='Maximum planned Rekognition calls, not a dollar budget.')
    parser.add_argument('--report', type=Path, help='Optional local report; never contains signed URLs or credential values.')
    parser.add_argument('--expected-role', help='Require EC2 metadata credentials and this STS role name before any S3/analysis calls.')
    parser.add_argument('--expected-account', help='Require this 12-digit AWS account and bucket owner before storage/analysis.')
    args = parser.parse_args(argv)
    report = None
    try:
        with ExitStack() as outputs:
            destination = None
            if args.report:
                args.report.parent.mkdir(parents=True, exist_ok=True)
                # Reserve the destination before any paid calls or remote writes.
                # O_EXCL also rejects existing files and dangling symlinks.
                fd = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                destination = outputs.enter_context(os.fdopen(fd, 'w'))
            report = run_validation(args)
            rendered = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
            if destination:
                destination.write(rendered)
                destination.flush()
    except OSError:
        failure = {'status': 'failed', 'code': 'REPORT_WRITE_FAILED'}
        if report is not None:
            failure['result'] = report
        print(json.dumps(failure, ensure_ascii=False))
        return 1
    print(rendered, end='')
    return 0 if report['status'] in {'planned', 'preflight_passed', 'analysis_passed', 'passed'} else 1


def run_validation(args):
    report = {'schema_version': 1, 'run_id': uuid.uuid4().hex, 'created_at': datetime.now(timezone.utc).isoformat(),
              'status': 'blocked', 'mode': 'live' if args.execute else 'preflight' if args.preflight else 'plan',
              'aws_requested': args.execute or args.preflight,
              'scope': 'analysis_only' if args.analysis_only else 'storage_and_analysis',
              'photo_analysis_verified': False, 'rekognition_calls': 0, 'photos': []}
    try:
        require(not (args.analysis_only and args.preflight), 'ANALYSIS_ONLY_PREFLIGHT_UNSUPPORTED')
        if args.expected_role is not None:
            require(bool(re.fullmatch(r'[A-Za-z0-9+=,.@_-]{1,64}', args.expected_role)), 'EXPECTED_ROLE_INVALID')
        if args.expected_account is not None:
            require(bool(re.fullmatch(r'[0-9]{12}', args.expected_account)), 'EXPECTED_ACCOUNT_INVALID')
        refs, photos, kind = load_dataset(args.manifest)
        report['dataset_kind'] = kind
        planned_calls = len(refs) + len(photos) * (2 + len(refs))
        require(1 <= args.max_calls <= 1000 and planned_calls <= args.max_calls, 'CALL_BUDGET_EXCEEDED')
        require(bool(re.fullmatch(r'[a-z]{2}(?:-[a-z]+)+-\d+', args.region)), 'AWS_REGION_INVALID')
        report['plan'] = {'references': len(refs), 'photos': len(photos), 'rekognition_calls_upper_bound': planned_calls,
                          's3_objects': 0 if args.analysis_only else 1, 'region': args.region, 'bucket_configured': bool(args.bucket)}
        if args.execute or args.preflight:
            if args.analysis_only:
                require(bool(args.expected_account), 'EXPECTED_ACCOUNT_REQUIRED')
            else:
                require(bool(args.bucket), 'S3_BUCKET_REQUIRED')
            execute(refs, photos, args.bucket, args.region, report, expected_role=args.expected_role,
                    expected_account=args.expected_account, preflight=args.preflight, analysis_only=args.analysis_only)
        else:
            report['status'] = 'planned'
    except Exception as exc:
        report['code'] = error_code(exc)
    return report


if __name__ == '__main__':
    sys.exit(main())
