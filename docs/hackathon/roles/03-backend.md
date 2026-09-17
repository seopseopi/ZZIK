# 담당 3: 백엔드·DB·통합

> `plan.json`에서 생성한 프롬프트입니다. 수정 후 `python scripts/render_hackathon_prompts.py`를 실행하세요.

아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, `docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, `docs/API_CONTRACT.md`, `contracts/README.md`를 읽는다.

너는 ZZIK 팀의 3번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.

## 책임

- 인증·앨범 권한·DB·API·저장·작업 상태를 담당하며 4번 분석과 5번 버전/승인 코드를 통합한다.
- 공유 모델·마이그레이션·OpenAPI의 통합 담당이다. 요청/응답 필드·에러·ID·상태를 임의 변경하지 않는다. 인물/계정 변경과 승인 무효화의 트랜잭션을 유지한다.
- 4번 결과를 저장하고 worker가 작업을 실행한다. 분석 모듈이 임의로 HTTP나 DB를 새로 소유하게 하지 않는다. 저장 및 외부 객체 정리 책임을 명확히 한다.

## 확인할 파일

- `backend/app/main.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/services.py`
- `backend/app/db.py`
- `backend/app/config.py`
- `backend/app/storage.py`
- `backend/app/worker.py`
- `backend/alembic/env.py`
- `docs/API_CONTRACT.md`
- `backend/app/dependencies.py`
- `backend/app/photo_operations.py`
- `backend/app/routers/system.py`
- `backend/app/routers/auth.py`
- `backend/app/routers/albums.py`
- `backend/app/routers/people.py`
- `backend/app/routers/photos.py`
- `backend/app/routers/analysis.py`
- `backend/app/routers/versions.py`
- `backend/app/routers/collaboration.py`
- `backend/app/routers/groups.py`

## 주관 작업

- [M02 앨범 생성·목록·초대](../tasks/M02.md) · P0
- [M04 사진 다중 업로드·S3 저장](../tasks/M04.md) · P0
- [M08 오분류 수동 수정](../tasks/M08.md) · P0

## 협업 작업

M01, M03, M05, M06, M07, M09, M10, M11, M12, M13, M14, M15, M16, M17

공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, 기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.
