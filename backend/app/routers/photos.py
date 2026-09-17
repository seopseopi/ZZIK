"""Photo upload, filtering, metadata, manual people, and downloads."""
from __future__ import annotations

from .. import storage as storage_backend
from ..config import settings
from ..db import get_db
from ..dependencies import auth
from ..media import stored_file, version_file_response
from ..models import Person, Photo, PhotoPerson
from ..photo_operations import queue_all_photo_files, upload_photo
from ..schemas import PeopleSet, PhotoPatch
from ..services import drain_cleanup, fail, get_photo, get_version, invalidate_photo_reviews, membership, photo_dict
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pathlib import Path
from sqlalchemy import Text, and_, func, or_, select
from sqlalchemy.orm import Session as DBSession
from typing import Literal

router = APIRouter()


@router.post('/api/albums/{album_id}/photos',status_code=201)
def upload(album_id:str,file:UploadFile=File(...),request_id:str=Form(...,min_length=8,max_length=100),user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    p=upload_photo(db,album_id,user,file.file.read(settings.max_upload_bytes+1),file.filename,file.content_type,request_id)
    return photo_dict(db,p)


@router.get('/api/albums/{album_id}/photos')
def list_photos(album_id:str,page:int=Query(1,ge=1),page_size:int=Query(40,ge=1,le=100),
                filter:Literal['all','mine','solo','group','no_faces','review','final']='all',people:str='',
                match:Literal['all','any']='all',tag:str='',q:str='',mine:bool=False,sort:Literal['newest','oldest','captured']='newest',date:str='',
                user=Depends(auth),db:DBSession=Depends(get_db)):
    membership(db,album_id,user)
    query=select(Photo).where(Photo.album_id==album_id)
    included=select(PhotoPerson.photo_id).where(PhotoPerson.excluded==False)
    if filter=='mine' or mine:
        ids=select(Person.id).where(Person.album_id==album_id,Person.user_id==user.id)
        query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id.in_(ids))))
    if filter=='solo': query=query.where(Photo.analysis_status=='completed',Photo.face_count==1)
    elif filter=='group': query=query.where(Photo.analysis_status=='completed',Photo.face_count>=2)
    elif filter=='no_faces': query=query.where(Photo.analysis_status=='completed',Photo.face_count==0)
    elif filter=='review': query=query.where(or_(Photo.analysis_status=='failed',and_(Photo.analysis_status=='completed',Photo.unknown_faces>0)))
    elif filter=='final': query=query.where(Photo.final_version_id.is_not(None))
    person_ids=sorted(set(pid for pid in people.split(',') if pid))
    if len(person_ids)>100: fail(422,'TOO_MANY_PEOPLE','인물 필터를 줄여 주세요.')
    if person_ids:
        valid=set(db.scalars(select(Person.id).where(Person.album_id==album_id,Person.id.in_(person_ids))))
        if valid!=set(person_ids): fail(422,'INVALID_PERSON','이 앨범의 인물만 검색할 수 있어요.')
        if match=='all':
            for pid in person_ids: query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id==pid)))
        else: query=query.where(Photo.id.in_(included.where(PhotoPerson.person_id.in_(person_ids))))
    from sqlalchemy.dialects.postgresql import JSONB
    tag_text=Photo.tags.cast(JSONB).cast(Text) if db.bind.dialect.name=='postgresql' else Photo.tags.cast(Text)
    if tag:
        if db.bind.dialect.name=='postgresql': query=query.where(Photo.tags.cast(JSONB).contains([tag]))
        else: query=query.where(tag_text.ilike('%'+tag.replace('%','\\%').replace('_','\\_')+'%'))
    if q:
        term='%'+q.replace('%','\\%').replace('_','\\_')+'%'
        matching_people=select(Person.id).where(Person.album_id==album_id,Person.name.ilike(term))
        query=query.where(or_(Photo.filename.ilike(term),Photo.note.ilike(term),Photo.location_name.ilike(term),tag_text.ilike(term),Photo.id.in_(included.where(PhotoPerson.person_id.in_(matching_people)))))
    if date:
        from datetime import date as Date
        try: Date.fromisoformat(date)
        except ValueError: fail(422,'INVALID_DATE','날짜 형식을 확인해 주세요.')
        query=query.where(Photo.captured_at.startswith(date))
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    order=Photo.created_at.asc() if sort=='oldest' else Photo.captured_at.desc().nulls_last() if sort=='captured' else Photo.created_at.desc()
    rows=db.scalars(query.order_by(order,Photo.id).offset((page-1)*page_size).limit(page_size)).all()
    stats={status:0 for status in ['pending','processing','completed','failed']}
    stats.update(dict(db.execute(select(Photo.analysis_status,func.count()).where(Photo.album_id==album_id).group_by(Photo.analysis_status)).all()))
    return {'items':[photo_dict(db,p) for p in rows],'total':total,'page':page,'page_size':page_size,'stats':stats}


@router.get('/api/photos/{photo_id}')
def photo_detail(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    return photo_dict(db,get_photo(db,photo_id,user),detail=True)


@router.patch('/api/photos/{photo_id}')
def patch_photo(photo_id:str,body:PhotoPatch,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    for key,value in body.model_dump(exclude_unset=True).items():
        if value is not None: setattr(p,key,value)
    db.commit()
    return photo_dict(db,p,detail=True)


@router.delete('/api/photos/{photo_id}')
def delete_photo(photo_id:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    if p.uploader_id!=user.id: membership(db,p.album_id,user,owner=True)
    queue_all_photo_files(db,p)
    db.delete(p)
    db.commit()
    drain_cleanup()
    return {'ok':True}


@router.put('/api/photos/{photo_id}/people')
def set_people(photo_id:str,body:PeopleSet,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user,lock=True)
    wanted=set(body.person_ids)
    valid=set(db.scalars(select(Person.id).where(Person.album_id==p.album_id,Person.id.in_(wanted))))
    if valid!=wanted: fail(422,'INVALID_PERSON','이 앨범의 인물만 연결할 수 있어요.')
    existing={row.person_id:row for row in db.scalars(select(PhotoPerson).where(PhotoPerson.photo_id==p.id))}
    before={pid for pid,row in existing.items() if not row.excluded}
    for pid,row in existing.items():
        row.excluded=pid not in wanted
        row.source='manual'
    for pid in wanted-set(existing): db.add(PhotoPerson(photo_id=p.id,person_id=pid,source='manual',excluded=False))
    if wanted!=before: invalidate_photo_reviews(db,p,'등장 인물이 변경되었어요. 새 보정본에서 승인 대상을 다시 확인해 주세요.')
    db.commit()
    return photo_dict(db,p,detail=True)


@router.get('/api/photos/{photo_id}/file')
def photo_file(photo_id:str,kind:Literal['original','thumbnail','display']='display',download:bool=False,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    key=getattr(p,kind+'_key')
    return stored_file(key,p.mime if kind=='original' else 'image/jpeg',p.filename if download else None)


@router.get('/api/photos/{photo_id}/download')
def photo_download(photo_id:str,version_id:str|None=None,user=Depends(auth),db:DBSession=Depends(get_db)):
    p=get_photo(db,photo_id,user)
    if version_id:
        v,pv=get_version(db,version_id,user)
        if pv.id!=p.id: fail(422,'VERSION_PHOTO_MISMATCH','이 사진의 보정본을 선택해 주세요.')
        return version_file_response(p,v,download=True)
    return stored_file(p.original_key,p.mime,p.filename)


@router.get('/api/albums/{album_id}/download')
def album_download(album_id:str,photo_ids:str,user=Depends(auth),db:DBSession=Depends(get_db)):
    """A spooled ZIP keeps a bounded batch of originals out of browser memory."""
    import tempfile
    import zipfile
    from fastapi.responses import StreamingResponse
    membership(db,album_id,user)
    ids=list(dict.fromkeys(pid for pid in photo_ids.split(',') if pid))
    if not 1<=len(ids)<=100: fail(422,'INVALID_DOWNLOAD_SELECTION','1–100장의 사진을 선택해 주세요.')
    photos=db.scalars(select(Photo).where(Photo.album_id==album_id,Photo.id.in_(ids))).all()
    if len(photos)!=len(ids): fail(404,'PHOTO_NOT_FOUND','선택한 사진 중 접근할 수 없는 사진이 있어요.')
    if sum(p.byte_size for p in photos)>512*1024*1024: fail(413,'DOWNLOAD_TOO_LARGE','한 번에 512MB까지 내려받을 수 있어요. 사진을 나누어 선택해 주세요.')
    output=tempfile.SpooledTemporaryFile(max_size=8*1024*1024)
    try:
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
            for index,p in enumerate(photos,1):
                archive.writestr(f'{index:03d}-{Path(p.filename).name}',storage_backend.get_storage().get(p.original_key))
        output.seek(0)
    except Exception:
        output.close()
        raise
    def chunks():
        try:
            while chunk:=output.read(128*1024): yield chunk
        finally: output.close()
    return StreamingResponse(chunks(),media_type='application/zip',headers={'Content-Disposition':"attachment; filename*=UTF-8''zzik-originals.zip"})
