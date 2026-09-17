"""Compose feature routers and enforce the shared HTTP safety policy."""
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .image_service import ImageError
from .services import APIError
from .routers import albums, analysis, auth, collaboration, groups, people, photos, system, versions

log = logging.getLogger(__name__)
app = FastAPI(title='ZZIK API', version='1.0.0')
origins = [s.strip() for s in settings.allowed_origins.split(',') if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=['GET','POST','PATCH','PUT','DELETE','OPTIONS'], allow_headers=['Content-Type','X-CSRF-Token'])

@app.middleware('http')
async def request_safety(request: Request, call_next):
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('origin') and request.headers['origin'] not in origins:
        return JSONResponse({'code':'ORIGIN_NOT_ALLOWED','message':'허용되지 않은 사이트의 요청이에요.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(APIError)
async def api_error(_, exc):
    result = {'code':exc.code,'message':exc.message}
    if exc.details is not None: result['details'] = exc.details
    return JSONResponse(jsonable_encoder(result), status_code=exc.status)


@app.exception_handler(ImageError)
async def image_error(_, exc):
    return JSONResponse({'code':exc.code,'message':exc.message},status_code=422)


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc):
    return JSONResponse({'code':'INVALID_REQUEST','message':'입력값을 확인해 주세요.','details':jsonable_encoder(exc.errors(),custom_encoder={ValueError:str})},status_code=422)


@app.exception_handler(Exception)
async def unexpected_error(_, exc):
    log.exception('Request failed',exc_info=exc)
    return JSONResponse({'code':'INTERNAL_ERROR','message':'처리하지 못했어요. 잠시 후 다시 시도해 주세요.'},status_code=500)

for router in (system.router, auth.router, albums.router, people.router, photos.router,
               analysis.router, versions.router, collaboration.router, groups.router):
    app.include_router(router)
