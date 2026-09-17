"""Explicit, idempotent local demo setup. Never runs during app startup."""
from pathlib import Path
from datetime import timedelta
import hashlib
from sqlalchemy import select, text
from .config import settings
from .db import SessionLocal
from .models import Album, AlbumMember, ApprovalTarget, Person, Photo, User, Version, now
from .services import hash_password, effective_people
from .storage import get_storage
from .photo_operations import upload_photo
from .worker import process_one


def main():
    if not settings.demo_enabled or settings.face_analysis_provider != 'fixture':
        raise SystemExit('Demo seeding requires DEMO_ENABLED=true and FACE_ANALYSIS_PROVIDER=fixture.')
    assets = Path(__file__).resolve().parents[2] / 'frontend/public/demo'
    if not (assets / 'photo-01.jpg').exists():
        raise SystemExit('Missing bundled demo assets; run scripts/prepare_demo_assets.py first.')
    with SessionLocal() as db:
        if db.bind.dialect.name == 'postgresql':
            # Session lock prevents concurrent seed invocations without changing existing user data.
            db.execute(text('SELECT pg_advisory_lock(76766288)'))
        members=[]
        for slug,name in [('jisu','지수'),('minji','민지'),('seoyeon','서연'),('yujin','유진')]:
            user=db.scalar(select(User).where(User.email==f'{slug}@moacut.local'))
            if not user:
                user=User(email=f'{slug}@moacut.local',name=name,password_hash=hash_password('MoacutDemo123!'))
                db.add(user);db.flush()
            members.append((slug,user))
        db.commit()
        for index,(name,description,photo_numbers) in enumerate([
            ('제주 여행','푸른 바다와 우리, 오래 기억할 제주에서의 순간들.',list(range(1,13))),
            ('부산 주말','주말의 느긋한 산책과 함께한 사람들 · 샘플 앨범',[11,5,9,12]),
            ('우리의 작은 순간','일상 속에서 발견한 소중한 장면들 · 샘플 앨범',[8,10,4]),
        ]):
            album=db.scalar(select(Album).where(Album.owner_id==members[0][1].id,Album.name==name))
            if not album:
                album=Album(name=name,description=description,owner_id=members[0][1].id,timezone='Asia/Seoul',invite_code=f'MOACUT-DEMO-{index+1}',created_at=now()-timedelta(days=index))
                db.add(album);db.flush()
                for slug,user in members:
                    db.add(AlbumMember(album_id=album.id,user_id=user.id,role='owner' if slug=='jisu' else 'member'))
                    data=(assets/f'avatar-{slug}.jpg').read_bytes()
                    key=f'albums/{album.id}/references/demo-{slug}.jpg'
                    get_storage().put(key,data,'image/jpeg')
                    db.add(Person(album_id=album.id,name=user.name,user_id=user.id,reference_key=key,reference_hash=hashlib.sha256(data).hexdigest()))
                db.commit()
            for order,num in enumerate(photo_numbers):
                request_id=f'demo-{index}-{num}'
                existing=db.scalar(select(Photo).where(Photo.album_id==album.id,Photo.request_id==request_id))
                if existing:continue
                data=(assets/f'photo-{num:02}.jpg').read_bytes()
                photo=upload_photo(db,album.id,members[0][1],data,f'JEJU_{num:04}.jpg','image/jpeg',request_id)
                photo.created_at=now()-timedelta(days=2+index,hours=-order)
                photo.selected=index==0 and num in [3,5,8]
                photo.note='디자인 참고 이미지에서 추출한 체험용 샘플 사진입니다.'
                db.commit()
        if db.bind.dialect.name == 'postgresql':db.execute(text('SELECT pg_advisory_unlock(76766288)'))
        db.commit()
    while process_one():pass
    with SessionLocal() as db:
        album=db.scalar(select(Album).where(Album.invite_code=='MOACUT-DEMO-1'))
        if album:
            first=db.scalar(select(Photo).where(Photo.album_id==album.id,Photo.request_id=='demo-0-1'))
            if first and not db.scalar(select(Version).where(Version.photo_id==first.id)):
                v1=Version(photo_id=first.id,author_id=first.uploader_id,number=1,name='햇살을 조금 더',brightness=1.1,saturation=1.08)
                db.add(v1);db.flush()
                v2=Version(photo_id=first.id,author_id=first.uploader_id,number=2,name='자연스러운 제주',parent_id=v1.id,brightness=1.04,saturation=.95,review_requested=True,target_person_ids=[p.id for p in effective_people(db,first.id)])
                db.add(v2);db.flush()
                for user_id in {p.user_id for p in effective_people(db,first.id) if p.user_id}:
                    db.add(ApprovalTarget(version_id=v2.id,user_id=user_id))
                db.commit()
    print('Demo ready. jisu@moacut.local / minji@moacut.local — password: MoacutDemo123!')

if __name__=='__main__':main()
