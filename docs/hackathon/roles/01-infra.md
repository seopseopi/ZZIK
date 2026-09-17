# 담당 1: AWS 인프라·배포

> `plan.json`에서 생성한 프롬프트입니다. 수정 후 `python scripts/render_hackathon_prompts.py`를 실행하세요.

아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, `docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, `docs/API_CONTRACT.md`, `contracts/README.md`를 읽는다.

너는 ZZIK 팀의 1번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.

## 책임

- Web→App→RDS 연결과 private S3·IAM 역할·HTTPS를 담당한다. API와 worker를 각각 실행하고 동일 배포 버전·환경을 적용한다.
- 계정·리전·기존 리소스·예산이 확정되기 전에는 배포 파일과 검증 절차까지만 작성한다. 실제 AWS 호출·생성 결과를 로컬 실행으로 대체하지 않는다.
- 반영한 커밋, 마이그레이션 revision, 헬스 체크, 업로드·분석·다운로드 결과, 복구·정리 방법을 2/3번에게 전달한다.
- 3-Tier를 설계·검증·발표 핵심으로 준비한다. docs/THREE_TIER_REHEARSAL.md의 Web/App/RDS 분리 배치와 App 장애·복구 시연을 주관한다. 자원 생성 보류를 유지하고 실제 실행 증거 전에는 완료로 표시하지 않는다.

## 확인할 파일

- `infra/nginx.conf`
- `infra/backend.Dockerfile`
- `infra/frontend.Dockerfile`
- `compose.yaml`
- `docs/AWS_DEPLOYMENT.md`
- `docs/AWS_EDU_VALIDATION.md`
- `scripts/aws_validation_container.sh`
- `docs/AWS_VALIDATION_CONTAINER.md`
- `scripts/backup_local.py`
- `scripts/verify_backup_restore.py`
- `docs/BACKUP_RESTORE.md`
- `docs/THREE_TIER_REHEARSAL.md`

## 주관 작업

- [M01 3-Tier 기본 연결](../tasks/M01.md) · P0

## 협업 작업

M04, M07, M12

공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, 기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.
