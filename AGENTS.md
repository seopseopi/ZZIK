# ZZIK 작업 규칙

## 먼저 읽기

- 사용자 최신 지시 → 이 파일 → `docs/hackathon/README.md` → 맡은 역할·M 작업 순서로 읽는다.
- 팀 원문은 `docs/hackathon/source/TEAM_SPEC.md`, 차이와 현재 판단은 `docs/hackathon/SCOPE.md`에 있다.
- 서비스 이름은 **찍 / ZZIK**. 이전 계정 주소·DB 식별자는 호환을 위해 남아 있다.

## 실행과 완료 기준

- 일반 서버 실행: `bash scripts/dev.sh`.
- 정적 체험 실행: `npm --prefix frontend run dev:demo`. 이 모드는 실제 서버/AI/다중 사용자 검증을 대신하지 않는다.
- 계약·작업 구조 검사: `.venv/bin/python scripts/check_harness.py`.
- 백엔드: 전용 `_test` DB의 `TEST_DATABASE_URL`을 설정한 후 `.venv/bin/python -m pytest -q backend/tests`.
- 프론트: `npm --prefix frontend run build`.
- 실제 서버 E2E: 로컬 전용 `_e2e` DB의 `ZZIK_E2E_DATABASE_URL`을 설정한 후 `.venv/bin/python scripts/run_integration.py`.
- 체험 E2E: `npm --prefix frontend run build:demo -- --base=/ZZIK/` 후 `npm --prefix frontend run test:demo`.
- 변경 범위에 필요한 검사를 실행한다. 문서만 수정할 때 전체 앱 테스트를 반복하지 않는다.

## 팀 경계

1. 인프라 담당: AWS/Web/App/RDS/S3/IAM/배포/운영 검증.
2. 프론트 담당: 공통 UI·앨범·업로드·갤러리, 5번 화면 통합.
3. 백엔드 담당: 인증·API·DB·마이그레이션·작업/저장, 4/5번 서버 통합.
4. AI 담당: 기준 얼굴·분석·인물 그룹·장면/품질·추천.
5. 보정 담당: 원본 기반 렌더링·버전·비교·승인·협업.

API는 `backend/app/routers/`의 9개 기능별 모듈에 둔다. `main.py`는 라우터 등록·미들웨어·오류 처리만 맡는다. 공통 `models.py`, `schemas.py`, `services.py`와 마이그레이션은 3번이 통합한다. 라우터끼리 직접 import하지 않고 공통 처리는 `dependencies.py`, `photo_operations.py`, `media.py`를 사용한다. `frontend/src/App.tsx`, `types.ts`, `api.ts`, 공통 CSS는 2번이 통합한다. `frontend/src/features/`에 로그인·앨범·갤러리·추천·그룹·보드를 분리했다. 5번은 versions/collaboration 라우터와 보정·보드 화면을 작업하고, 공유 API/model 변경은 3번과 맞춘다. 마이그레이션 번호와 부모 revision은 3번이 조정한다. 구체적인 범위는 `docs/hackathon/OWNERSHIP.md`를 따른다.

## 계약과 데이터

- `/api`·요청 필드·오류 코드를 바꾸면 `docs/API_CONTRACT.md`, `contracts/openapi.json`, 프론트 타입과 영향받는 테스트를 함께 검토한다.
- OpenAPI 갱신은 `.venv/bin/python scripts/check_harness.py --write-contract`로 수행한다. 스냅샷만 갱신해 불일치를 숨기지 않는다.
- 승인 정책은 확인된 등장 멤버 전원 승인이다. 좋아요 수로 바꾸지 않는다. 인물/계정/멤버 변경과 승인 취소의 최종본 해제 규칙을 보존한다.
- 원본은 보존하고 저장된 전체 설정을 원본에 적용한다. 현재 보정 범위는 밝기·채도다.
- 샘플·실제 AWS·브라우저 체험 결과를 구분한다. 실제 분석 실패를 샘플 성공으로 바꾸지 않는다.
- 비밀키·`.env`·DB/업로드/세션/로그를 커밋하지 않는다. 운영 데이터에서 테스트·초기화를 실행하지 않는다.

## Git과 작업 보고

- 기존 완료 코드를 먼저 읽고 해당 M의 부족한 부분을 구현·검증한다. 이미 있는 기능을 지우고 다시 쓰지 않는다.
- `feat/mXX-설명`, `fix/mXX-설명`, `refactor/설명` 브랜치와 기능 단위 커밋·PR을 사용한다.
- PR에 M 번호, 의존 PR, 바뀐 동작, 검사 결과, 공유 계약/DB 변경을 적는다.
- AWS 완료는 실제 환경의 증거가 있을 때만 표시한다. 로컬 통과는 별도 상태다.
- 실행하지 않은 검사와 외부 조건은 명확히 기록한다. 숫자 2,000장·20번 선택·정확도를 측정한 성과처럼 쓰지 않는다.
