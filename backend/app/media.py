"""Serve protected originals and render cached version downloads."""
from __future__ import annotations

from . import storage as storage_backend
from .config import settings
from .image_service import render_cache_key, render_image
from .services import fail
from fastapi import Response
from fastapi.responses import RedirectResponse
from pathlib import Path
from urllib.parse import quote


def stored_file(key,mime,filename=None):
    storage=storage_backend.get_storage()
    if settings.storage_backend=='s3': return RedirectResponse(storage.signed_url(key,filename=filename),status_code=307)
    try: data=storage.get(key)
    except FileNotFoundError: fail(404,'FILE_NOT_FOUND','파일을 찾을 수 없어요.')
    headers={'Content-Disposition':"attachment; filename*=UTF-8''"+quote(filename)} if filename else {}
    return Response(data,media_type=mime,headers=headers)


def version_file_response(photo,version,download=False,preview=False):
    size=1600 if preview and not download else None
    key=render_cache_key(photo.original_hash,version.brightness,version.saturation,size)
    storage=storage_backend.get_storage()
    if not storage.exists(key): storage.put(key,render_image(storage.get(photo.original_key),version.brightness,version.saturation,max_size=size),'image/jpeg')
    filename=f'{Path(photo.filename).stem}-v{version.number}.jpg' if download else None
    return stored_file(key,'image/jpeg',filename)
