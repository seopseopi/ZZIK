"""Account registration, session login, and logout."""
from __future__ import annotations

from .. import responses as out

import secrets
from ..config import settings
from ..db import get_db
from ..models import Session, User, now
from ..schemas import Login, Register
from ..services import current_user, digest, fail, hash_password, user_dict, verify_password
from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

router = APIRouter()


def login_session(db, user, request, response):
    previous = request.cookies.get(settings.session_cookie)
    if previous:
        db.execute(delete(Session).where(Session.token_hash==digest(previous)))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(Session(token_hash=digest(token),user_id=user.id,csrf_token=csrf,expires_at=now()+timedelta(days=settings.session_days)))
    db.commit()
    response.set_cookie(settings.session_cookie,token,max_age=settings.session_days*86400,httponly=True,
                        secure=settings.cookie_secure,samesite='lax',path='/')
    return {'user':user_dict(user),'csrf_token':csrf}


@router.post('/api/auth/register',status_code=201, response_model=out.SessionResponse, response_model_exclude_unset=True)
def register(body:Register,request:Request,response:Response,db:DBSession=Depends(get_db)):
    user = User(name=body.name,email=body.email,password_hash=hash_password(body.password))
    db.add(user)
    try: db.flush()
    except IntegrityError:
        db.rollback()
        fail(409,'EMAIL_EXISTS','이미 가입한 이메일이에요.')
    return login_session(db,user,request,response)


@router.post('/api/auth/login', response_model=out.SessionResponse, response_model_exclude_unset=True)
def login(body:Login,request:Request,response:Response,db:DBSession=Depends(get_db)):
    user = db.scalar(select(User).where(User.email==body.email.strip().lower()))
    if not user or not verify_password(body.password,user.password_hash):
        fail(401,'INVALID_CREDENTIALS','이메일 또는 비밀번호를 확인해 주세요.')
    return login_session(db,user,request,response)


@router.get('/api/auth/me', response_model=out.SessionResponse, response_model_exclude_unset=True)
def me(request:Request,db:DBSession=Depends(get_db)):
    user, session = current_user(request,db)
    return {'user':user_dict(user),'csrf_token':session.csrf_token}


@router.post('/api/auth/logout', response_model=out.OkResponse, response_model_exclude_unset=True)
def logout(request:Request,response:Response,db:DBSession=Depends(get_db)):
    _,session=current_user(request,db)
    db.delete(session)
    db.commit()
    response.delete_cookie(settings.session_cookie,path='/',secure=settings.cookie_secure,httponly=True,samesite='lax')
    return {'ok':True}
