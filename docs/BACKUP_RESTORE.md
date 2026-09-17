# PostgreSQL·사진 백업과 복원 검증

## 범위

`backup_local.py`는 **쓰기 중단 상태의 로컬 PostgreSQL과 로컬 사진 폴더**를 한 백업으로 보관한다. DB는 `pg_dump` custom 형식, 사진은 상대 경로를 유지한 파일 복사, `manifest.json`은 DB 덤프·사진 SHA-256과 크기·테이블 행 수·Alembic revision·PostgreSQL major 버전을 기록한다. 연결 주소·비밀번호는 manifest에 쓰지 않는다.

`pg_dump` 자체는 DB의 일관된 스냅샷을 만들지만 외부 사진 폴더까지 같은 시점으로 묶지는 않는다. 따라서 API·worker·수동 DB/파일 쓰기를 모두 중단해야 한다. 이 도구는 중단 확인 플래그와 다른 DB 클라이언트 유무를 검사하고 복사 전후 파일 해시·DB 메타데이터를 비교한다. 외부 프로세스가 검사 사이에 접속·수정하는 것까지 잠그는 기능은 아니다. [PostgreSQL pg_dump 설명](https://www.postgresql.org/docs/17/app-pgdump.html).

복원 대상은 항상 새 `zzik_restore_<UUID>_e2e` DB와 새 사진 폴더다. 기존 DB 덮어쓰기, 원본 DB 삭제, 운영 연결 자동 전환은 제공하지 않는다. `pg_restore --single-transaction --exit-on-error`를 사용하며 역할·권한은 복사하지 않고 복원 사용자 소유로 생성한다. 같은 PostgreSQL major와 앱 revision 기준의 복원 검사다. [pg_restore 설명](https://www.postgresql.org/docs/17/app-pgrestore.html).

## 자동 리허설

PostgreSQL 17 서버, 같은 major의 `pg_dump`·`pg_restore`, 프로젝트 Python 의존성이 필요하다. 전용 로컬 `_e2e` DB에 연결하는 사용자는 임시 DB 생성·삭제 권한이 필요하다. 현재 서비스 `.env`의 DB와 사진 폴더는 읽거나 초기화하지 않는다.

```sh
# 저장소의 로컬 PostgreSQL을 사용하는 개발 환경 예시
export ZZIK_E2E_DATABASE_URL='postgresql+psycopg://moacut:moacut-local-only@127.0.0.1:54329/zzik_e2e'
.venv/bin/python scripts/verify_backup_restore.py
```

실행 순서:

1. 무작위 이름의 소스 DB·임시 사진 폴더를 만들고 마이그레이션·fixture seed 실행.
2. 실제 API·worker로 로그인 → 앨범 → 원본 업로드 → 분석 → 보정본 → 승인 → 최종본 생성.
3. API·worker 중단 후 DB와 사진을 백업.
4. **자신이 만든 소스 DB와 사진 폴더를 제거**해 백업본만 남김.
5. 새 DB·사진 폴더에 복원하고 모든 사진 해시·테이블 행 수·schema revision 확인.
6. 복원된 API에서 이전 세션·원본/보정본 다운로드 해시·보정값·승인·최종본 확인.
7. 새 사진 업로드와 worker 분석을 다시 수행해 읽기와 쓰기를 모두 확인.
8. 자신이 만든 DB·임시 사진·백업만 정리. 실패 진단 로그는 무시되는 `logs/recovery/`에 유지.

2026-09-17 로컬 PostgreSQL 17.11에서 **18개 테이블, 73개 사진 파일, revision 0002**로 통과했다. 실제 사용자 자료와 AWS는 사용하지 않았다. GitHub `integration` CI에도 같은 리허설을 추가했다. CI의 확정 결과는 해당 PR Checks에 기록한다.

## 백업본을 남기는 수동 실행

1. `scripts/dev.sh`로 실행했다면 해당 터미널의 Ctrl+C로 API·worker를 종료하고, 다른 writer도 종료한다. DB 서버는 유지한다.
2. `ZZIK_BACKUP_DATABASE_URL`에 대상 **로컬 PostgreSQL URL**을 설정한다. 사진은 이 DB와 짝인 폴더를 지정한다. 도구는 `.env`를 자동으로 읽지 않는다.
3. 매번 새 출력 경로로 실행하고 종료 코드와 `backup_complete`를 확인한다.

```sh
.venv/bin/python scripts/backup_local.py backup \
  --storage data/storage --output backups/run-001 --writes-stopped
.venv/bin/python scripts/backup_local.py verify --backup backups/run-001
```

실패한 백업에는 완료 manifest가 없다. 실패 경로를 덮어쓰지 말고 원인을 확인한 후 새 경로로 다시 실행한다. 백업 성공 또는 실패를 확인한 뒤 원래 서비스를 다시 시작한다.

백업에는 계정 해시·세션·원본 사진이 포함된다. 디렉터리 0700/파일 0600으로 저장하고 `backups/`를 Git에서 제외한다. SHA-256은 손상 검사이며 암호화나 출처 인증이 아니다. **신뢰하는 직접 생성 백업만 복원**한다. PostgreSQL 덤프 복원은 SQL을 실행하므로 외부에서 받은 파일의 해시 일치만으로 안전성을 보증하지 않는다.

## 새 로컬 DB로 수동 복원

`ZZIK_RESTORE_ADMIN_URL`에 전용 로컬 `_e2e` DB의 URL을 설정한다. 해당 사용자가 새 DB를 만들 수 있어야 한다.

```sh
.venv/bin/python scripts/backup_local.py restore-drill \
  --backup backups/run-001 --storage data/restored-run-001
```

실행 결과의 `database`가 새 DB명이다. 성공하면 DB와 사진 폴더를 유지하므로 이 DB와 폴더를 지정한 별도 API/worker를 실행해 인수 검사를 진행한다. 실패하면 이번 실행이 만든 DB·사진 폴더만 정리한다. 복원 중 다른 프로세스가 만든 동명 사진 폴더는 삭제하지 않는다. 검사 후에는 출력된 임시 DB와 지정한 복원 폴더만 정리한다.

손상된 덤프·누락/추가/변경 사진·심볼릭 링크는 DB 생성 전에 거부한다. 기존 사진 폴더, 백업 폴더 안의 복원 경로, 로컬 이외 DB 주소, 연결 옵션을 통한 우회도 거부한다. 서버 업그레이드·마이그레이션을 겸하는 복원은 이 도구의 범위가 아니다.

## 남은 운영 검증

- RDS snapshot/PITR, S3 버전·객체 복구, 다른 서버/계정으로의 복원.
- 정기 백업·보존 기간·암호화·외부 보관과 실제 복구 목표 시간/손실 허용 범위.
- Docker 볼륨 백업을 이 manifest 형식으로 통합하는 자동화. 현재 CI 복원은 PostgreSQL 서비스와 Python API/worker를 직접 실행한다.
- 코드 이미지 롤백과 DB migration 호환성. [배포 문서](AWS_DEPLOYMENT.md)의 롤백 조건을 따른다.

작은 fixture 리허설 통과는 운영 데이터의 복구 시간, AWS 복구, 재해 복구 완료를 의미하지 않는다.
