"""Private storage adapters. Keys never expose local paths to clients."""
from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from .config import settings


def safe_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key or "\x00" in key:
        raise ValueError("Invalid storage key")
    return str(path)


class LocalStorage:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or settings.storage_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / safe_key(key)).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Invalid storage key")
        return path

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".upload-", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return key

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str):
        self._path(key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3Storage:
    def __init__(self, bucket: str | None = None, client=None, *, prefix: str | None = None):
        self.bucket = bucket or settings.s3_bucket
        if not self.bucket:
            raise ValueError("S3_BUCKET is required in S3 mode")
        if client is None:
            import boto3
            from botocore.config import Config
            client = boto3.client("s3", region_name=settings.aws_region,
                                  config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=30, retries={"mode": "standard", "total_max_attempts": 3}))
        self.client = client
        self.prefix = (settings.s3_prefix if prefix is None else prefix).strip("/")
        if self.prefix:
            self.prefix = safe_key(self.prefix)

    def _key(self, key):
        key = safe_key(key)
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream"):
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data,
                               ContentType=content_type, ServerSideEncryption="AES256")
        return key

    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=self._key(key))
        with response["Body"] as body:
            return body.read()

    def delete(self, key: str):
        self.client.delete_object(Bucket=self.bucket, Key=self._key(key))

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(key))
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def signed_url(self, key: str, expires_in: int = 120, filename: str | None = None) -> str:
        params = {"Bucket": self.bucket, "Key": self._key(key)}
        if filename:
            from urllib.parse import quote
            params["ResponseContentDisposition"] = "attachment; filename*=UTF-8''" + quote(filename)
        return self.client.generate_presigned_url("get_object", Params=params,
                                                  ExpiresIn=min(max(expires_in, 1), 300))


@lru_cache(maxsize=1)
def get_storage():
    backend = settings.storage_backend.lower()
    if backend == "local":
        return LocalStorage()
    if backend == "s3":
        return S3Storage()
    raise ValueError("STORAGE_BACKEND must be local or s3")
