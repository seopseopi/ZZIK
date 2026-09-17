# 로컬 해커톤 starter 제작 도구

CI를 통과한 `2ffb4a9`를 기준으로 **5개 역할 / M01~M17 / 30개 구현 단위**를 별도 디렉터리에 내보냅니다. 원본 앱은 수정하지 않습니다. 정확한 커밋과 제공 기반은 [manifest.json](manifest.json), 학습자 안내는 [START_HERE.md](START_HERE.md)에 있습니다.

```sh
npm --prefix contracts/codegen ci
python3 scripts/starter.py export --output ../zzik-starter-local-v1
# 특정 담당만 연습: 다른 담당 구현은 참고 의존성으로 제공
python3 scripts/starter.py export --role 4 --output ../zzik-role4
python3 scripts/starter.py check --root ../zzik-starter-local-v1
```

출력 경로는 원본 밖의 새 디렉터리여야 합니다. export는 HEAD의 커밋된 파일만 사용합니다. 미커밋 파일·`.env`·Git 이력·브라우저 단독 완성 데모는 제공하지 않습니다. Python AST/TypeScript AST로 함수 본문만 비우고 시그니처·데코레이터·공통 계약을 유지합니다. 보호 해시는 실수 방지 장치이며 악의적인 상태 파일 조작을 막는 보안 경계가 아닙니다.

각 담당의 인계는 출력의 `starter/roles/01.md`~`05.md`에 생성됩니다. M 주관자와 함수 소유자는 다를 수 있습니다. 예를 들어 M16은 4번 주관이지만 API/화면 구현은 3/2번 소유입니다. `plan.json`의 협업·의존 관계와 `OWNERSHIP.md`를 함께 따릅니다.

## 생성 도구 검증

```sh
# 새 출력 경로, 로컬 전용 TEST_DATABASE_URL / ZZIK_E2E_DATABASE_URL 필요
.venv/bin/python scripts/verify_starter.py --output ../zzik-starter-rehearsal --behavior
```

전체/5개 단독 프로필의 빈 경계와 보호 파일 → 빈 판 계약/빌드 → 1·3·4·5·2 순서로 기준 구현 복원 → 모든 작업 파일 바이트 동일 → 계약/타입/빌드 → 백엔드/실제 API E2E를 검사합니다. 이 복원은 **기계적 왕복 검사**이며 팀원 독립 재구현 리허설이 아닙니다. 독립 재구현은 학습자 판의 실제 PR·테스트로 별도 기록해야 합니다. 원본 CI는 Docker 전체 스택·지속성·백업 복구도 계속 검사합니다.

`replay-reference`는 원본 저장소에서만 실행하는 제작자 도구입니다. 최초 생성 직후의 all 프로필에서만 허용하며 수정된 작업 파일을 덮어쓰지 않습니다. 학습자에게 복원 명령을 완료 방법으로 안내하지 않습니다.

## 배포와 Git 기록

`starter/local-v1`은 생성물만 들어 있는 별도 루트 커밋 브랜치로 배포합니다. clone은 `git clone --single-branch --branch starter/local-v1 https://github.com/seopseopi/ZZIK.git`을 사용합니다. 원본 저장소는 공개되어 있으므로 답안 접근을 차단하는 시험 환경은 아닙니다. 팀별 실제 작업 이력을 남기며 다른 사람이 작성한 것처럼 커밋을 꾸미지 않습니다.

초기 starter의 동작 검사는 실패해야 정상입니다. 학습자 CI는 PR/수동 실행에서 미구현 경계와 기존 동작 검사를 수행합니다. GitHub Pages 체험 사이트는 원래 브랜치의 데모이며 starter와 별개입니다.

## 완료 범위 밖

새 AWS 자원 생성 없이 로컬 연습 준비만 수행합니다. S3/RDS/배포·실사진 정확도·부하·5인 독립 조립, 대회 사전 코드 허용 규정과 팀원 GitHub 계정은 미확정입니다. 최종 AWS 기준 태그와 이 로컬 기준 커밋을 혼동하지 않습니다.

## 3-Tier 준비

조립판은 코드 조립 리허설이며, 그 이후의 [3-Tier 분리 배포·장애 복구](../docs/THREE_TIER_REHEARSAL.md)는 별도 완료 조건이다. 역할별 프롬프트와 M01에 각 담당의 시연 책임을 명시했다. 현재 자원 생성·실배포는 수행하지 않는다.

## 팀 PR 운영

[PR 운영 규칙](../docs/hackathon/PR_WORKFLOW.md)은 Kiro의 단위 선택·구현·검사·Draft/리뷰 준비 판단과 사람의 병합 책임을 정의한다. GitHub 보호 규칙을 자동 설정하는 기능은 아니다.
