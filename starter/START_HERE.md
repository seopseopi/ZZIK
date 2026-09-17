# 찍 / ZZIK 조립 연습 시작

이 checkout은 **기능 구현이 비어 있는 로컬 연습판**입니다. `.starter-state.json`에 기준 커밋·프로필·30개 작업 단위·보호 파일 해시가 기록되어 있습니다. AWS 서비스 완료본이나 대회 공식 지급 코드가 아닙니다.

## 시작 순서

1. `AGENTS.md`, `starter/roles/01.md`~`05.md` 중 자신의 인계, 연결된 역할/M 프롬프트를 읽습니다.
2. `python3 scripts/starter.py status`로 남은 작업을 확인합니다. `all`은 5명이 함께 조립하는 판입니다. 숫자 프로필은 그 역할만 비워 두며, **다른 역할의 구현은 제공된 참고 의존성**입니다.
3. `docs/hackathon/ASSEMBLY.md` 순서대로 구현합니다. 공통 기반 → 1/3번 API·저장 → 4번 분석 → 5번 보정·승인 → 2번 화면 통합입니다. 공유 파일은 인계 문서에 적힌 자기 함수만 수정합니다.
4. 역할별 브랜치와 실제 작업 커밋으로 PR을 만듭니다. `python3 scripts/starter.py check --role 3`처럼 자신의 미구현 경계를 확인하고, 역할 인계의 동작 검사를 실행합니다.
5. 전원 통합 후 `python3 scripts/starter.py check`, 아래 전체 검사를 모두 실행합니다. PR의 Starter acceptance 4개 작업도 통과해야 합니다.

## 제공 기반과 과제

5개 역할·M01~M17이 30개 구현 단위에 연결됩니다. 인증/CSRF/멤버십, DB 스키마·마이그레이션, API 요청/응답 계약, 저장소 어댑터, 워커 lease, 기본 스타일·레이아웃·이미지, fixture·기존 테스트는 제공됩니다. 세부 목록은 `starter/manifest.json`을 봅니다. 이 판은 전체를 무에서 만드는 과제가 아닙니다.

기능 본문은 `ZZIK_STARTER:` 예외, Compose/Nginx는 미구현 템플릿입니다. 브라우저 단독 체험 구현과 Pages 배포는 제거했습니다. 문서에 남은 데모 명령·완료 기록은 **기준본 설명**이며 현재 연습판에서는 적용되지 않습니다. 먼저 로컬 실제 API 모드로 연결합니다.

## 환경과 완료 검사

Python 3.13, Node 24, PostgreSQL 17을 준비합니다. 저장소의 `.env.example`과 `docs/DEVELOPMENT.md`를 참고합니다. 아래 DB URL은 자신이 만든 로컬 전용 DB로 설정합니다. `_test`, `_e2e` DB만 사용합니다.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm --prefix frontend ci
npm --prefix contracts/codegen ci
.venv/bin/python scripts/starter.py check
.venv/bin/python scripts/check_harness.py
npm --prefix frontend run types:check
npm --prefix frontend run build
# TEST_DATABASE_URL=로컬_전용_test_DB
.venv/bin/python -m pytest -q backend/tests
# ZZIK_E2E_DATABASE_URL=로컬_전용_e2e_DB
.venv/bin/python scripts/run_integration.py
.venv/bin/python scripts/verify_backup_restore.py
```

실제 환경변수는 shell에서 `export`한 뒤 검사합니다. Playwright Chromium 설치는 frontend에서 `npx playwright install chromium`으로 합니다. Docker 전체 스택·재시작 지속성은 `.github/workflows/starter.yml`의 compose 작업과 `docs/DEVELOPMENT.md`를 따릅니다. 초기 acceptance 실패는 정상입니다. `check` 통과는 검사 시작 자격이며, 기능 통과나 AWS 완료 판정이 아닙니다. 상태 파일·테스트·계약을 고쳐 검사를 우회하지 않습니다.

## 남은 외부 조건

AWS S3/RDS/배포·실환경 재시작/복구·다중 사용자/실사진 정확도·부하 측정은 별도 검증입니다. 자원 생성은 승인되지 않았습니다. 대회 사전 작성 코드 반입 규정과 실제 팀원 계정/담당은 확인 후 적용합니다. 기존 코드를 복원하는 기계적 검사는 독립적인 프롬프트 재구현이나 5인 협업 완료 증거가 아닙니다.

## 조립 후 3-Tier 리허설

코드 조립 완료 다음에는 `docs/THREE_TIER_REHEARSAL.md`를 따라 Web EC2/Nginx → App EC2/FastAPI·worker → RDS PostgreSQL과 비공개 S3를 연결하는 별도 배포 리허설을 준비한다. App 중단 중 화면·오류 안내·데이터 보존과 복구 후 기존/신규 기능을 확인하고 발표한다. 현재 AWS 자원 생성은 보류이며 실제 배포·중단 시연은 미검증이다. 교육 예시를 대회 규정으로 해석하지 않는다.

## Kiro의 PR 판단 규칙

`docs/hackathon/PR_WORKFLOW.md`를 반드시 읽힌다. 첫 작업은 자기 구현 단위 하나이며 Kiro가 검사·Draft PR 생성/갱신·리뷰 준비 판정을 수행한다. 3번은 통합 담당, 3번 PR은 1번이 병합하며 작성자 외 사람 리뷰가 필요하다. 팀원용 시작 프롬프트와 종료 보고 양식도 해당 문서에 있다. 단위 하나 완료와 역할 전체 check 통과를 혼동하지 않는다.
