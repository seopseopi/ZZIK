# 조립과 검증

## 환경 준비

Python 3.13, Node 24, PostgreSQL 17과 저장소 checkout이 필요하다. 자세한 설치는 [개발 환경](../DEVELOPMENT.md)을 따른다. macOS 로컬 DB는 아래 스크립트가 개발용·단위 테스트용·E2E용 DB를 구분해 만든다.

```bash
python3.13 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm --prefix frontend ci
cd frontend
npx playwright install chromium
cd ..
bash scripts/postgres-local.sh
```

Linux/CI에서는 별도 PostgreSQL을 준비하고 빈 `zzik_e2e` DB를 만든다. 테스트 계정에 해당 DB의 스키마 생성 권한이 필요하다. 실제 데이터가 있는 DB나 운영 계정을 사용하지 않는다.

## 변경 후 검사

```bash
.venv/bin/python scripts/check_harness.py
npm --prefix frontend run build
TEST_DATABASE_URL=postgresql+psycopg://moacut:moacut-local-only@127.0.0.1:54329/moacut_test .venv/bin/python -m pytest -q backend/tests
ZZIK_E2E_DATABASE_URL=postgresql+psycopg://moacut:moacut-local-only@127.0.0.1:54329/zzik_e2e .venv/bin/python scripts/run_integration.py
```

위 비밀번호는 이 저장소의 로컬 개발용 값이다. 각자 서버 설정에 맞게 환경변수로 바꾸고 실제 비밀값은 커밋하지 않는다.

통합 실행기는 루프백 주소와 `_e2e` 접미사를 검사한 뒤 무작위 전용 스키마·임시 사진 폴더·API/web 포트를 생성한다. 마이그레이션 → 스키마 검사 → seed → API·worker·web → 실제 서버 E2E 순으로 실행한다. 종료 시 자신이 만든 프로세스·스키마·사진 폴더만 정리한다. 기존 `.env`의 DB·사진 저장 위치는 사용하지 않는다. 분석은 명시적으로 fixture 모드다.

실패 로그는 `logs/integration/<실행 ID>/`에 남는다. 강제 종료(SIGKILL)나 DB 단절은 자동 정리를 막을 수 있다. 남은 스키마를 지울 때는 실행 ID와 테스트 DB를 확인한다. 전체 DB를 초기화하지 않는다. 동시에 같은 checkout에서 여러 테스트를 실행하면 Playwright 결과 폴더가 겹칠 수 있으므로 별도 checkout을 사용한다.

## 합치는 순서

1. 공통 계약과 로컬 M01 실행 경로를 확정한다. 실제 AWS 검증은 P0 최종 통과 조건으로 남긴다.
2. M02~M08을 의존 순서대로 통합한다. UI/AI/보정 담당은 계약과 기존 구현을 보고 자신의 기능 작업을 병행한다.
3. M08 이후 AI 담당은 M13→M14, 보정 담당은 M09→M10→M11→M12를 진행한다. 공유 파일은 통합 담당이 조정한다.
4. P0/P1이 검증된 다음 M15~17 확장을 마무리한다. M16은 M06/M13, M17은 M10/M11이 선행한다.
5. 실제 AWS 검증을 포함한 기준본을 보존하고 starter를 별도 제작한다. 빈 경계에서 다시 조립한 결과도 동일한 테스트를 통과해야 한다.

## 기능별 인계 예시

- 4번: 분석 함수 입력·출력·실패 코드와 fixture/실사진 결과를 3번에 전달한다.
- 3번: API·DB·작업 상태와 응답 예시를 2번에 전달한다.
- 5번: 보정 설정·버전·승인 정책을 3번 API, 2번 화면과 연결한다.
- 1번: 배포 커밋·환경·마이그레이션·HTTPS·재시작 결과를 공유한다.

PR마다 M 번호, 의존 PR, 변경 동작, 계약/DB 변경, 검사 결과, 외부 검증이 남은 조건을 작성한다. 실제 팀원 계정이 정해지면 CODEOWNERS와 main 필수 리뷰·CI 규칙을 설정한다. 초기 커밋을 다시 나누어 만든 개발 이력은 사용하지 않는다.

## 전체 통합의 통과 기준

두 계정이 앨범 참여 → 기준 인물 → 업로드 → 분석 완료/실패 표시 → 인물 필터 → 수동 수정 → 보정 버전 → 승인 → 최종본 → 다운로드 → 승인 취소를 수행한다. 원본 보존, 권한 없는 계정 차단, 재시작 후 데이터 유지도 확인한다. 자동 E2E가 다루지 않는 AWS·장애 복구·성능 항목은 별도 증거를 남긴다. 현재 자동화 범위는 [검증 상태](../IMPLEMENTATION_STATUS.md)와 테스트 코드를 기준으로 한다.
