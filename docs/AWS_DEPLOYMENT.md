# 실행·배포·복구

로컬 PostgreSQL·FastAPI·worker·프론트와 GitHub CI의 Docker 이미지 빌드·Compose 전체 E2E·컨테이너 재시작 보존 검사가 통과했다. 2026-09-17에는 AWS 콘솔에서 합성 사진의 얼굴 검출·비교도 확인했다. 앱 역할 기반 S3 저장·Rekognition 연동과 AWS 서버 배포는 아직 미검증이다.

**교육 계정은 먼저 [AWS_EDU_VALIDATION.md](AWS_EDU_VALIDATION.md)를 따른다.** 지정 AMI·역할·리전과 금지 서비스가 있어 아래 일반 운영 구성을 그대로 만들면 안 된다.

## 로컬 Compose

루트의 `.env.example`을 `.env`로 복사하고 Docker Engine과 Compose가 준비된 환경에서 실행한다.

```sh
docker compose config --quiet
docker compose up --build -d
docker compose ps
curl --fail http://localhost:8080/api/health/ready
docker compose logs --tail=100 api worker
```

브라우저 주소는 `http://localhost:8080`이다. `migrate` 서비스가 DB 준비를 기다려 Alembic을 적용한 뒤 API와 worker를 시작한다. 웹은 API 준비 상태를 기다린다. DB와 사진은 각각 `postgres`, `photos` named volume에 보존된다. 프론트의 외부 포트만 기본 공개하며 DB와 API는 Compose 네트워크 내부에서 연결한다.

`DATABASE_URL`은 Compose 안에서 `db:5432`로 설정된다. 호스트 개발용 `.env`의 `127.0.0.1:54329` 주소를 컨테이너에 그대로 전달하지 않는다. 데모 데이터 준비 명령은 [DEMO_GUIDE.md](DEMO_GUIDE.md)를 따른다.

주요 설정은 API와 worker에 동일하게 전달된다.

| 설정 | 로컬 기본값·용도 |
|---|---|
| `STORAGE_BACKEND` | `local`; 실제 S3 연결 시 `s3` |
| `STORAGE_ROOT` | Compose는 `/app/data/storage`로 고정 |
| `FACE_ANALYSIS_PROVIDER` | `fixture`; 실제 AWS는 `rekognition` |
| `FIXTURE_MANIFEST` | Compose는 `/app/backend/fixtures/manifest.json` |
| `WORKER_CONCURRENCY` | 2; 프로세스당 동시 작업 수 |
| `WORKER_MAX_ATTEMPTS`, `WORKER_LEASE_SECONDS` | 기본 3회, 120초; `.env` 값이 있으면 우선 |
| `REKOGNITION_SIMILARITY_THRESHOLD`, `REKOGNITION_CANDIDATE_MARGIN` | 90, 5; 정확도 보장값 아님 |
| `S3_BUCKET`, `S3_PREFIX`, `AWS_REGION` | 버킷, 기본 `moacut/`, 기본 `ap-northeast-2` |
| `ALLOWED_ORIGINS`, `COOKIE_SECURE` | 브라우저 주소 목록, HTTPS에서는 `true` |
| `GEOCODING_URL` | 비어 있으면 장소명 조회를 하지 않음 |

이 설정만 바꿔도 기존 파일이 다른 저장소로 자동 이관되지는 않는다. local↔S3 또는 버킷·prefix 변경 전에는 기존 객체 키를 그대로 유지해 파일을 이관하고 다운로드를 점검해야 한다.

## AWS 구성

기본 배치는 **HTTPS 진입점 → Web EC2/Nginx → private App EC2/FastAPI·worker → private RDS PostgreSQL + 비공개 S3**다. AWS 리소스·도메인·HTTPS 인증서·네트워크는 별도로 준비해야 한다. 이 저장소는 자동으로 EC2/RDS/버킷을 생성하는 IaC를 포함하지 않는다.

- Web EC2는 HTTPS 진입점에서 오는 웹 트래픽만 받는다. API 포트 8000은 Web EC2 보안 그룹에서만 접근하게 한다.
- RDS 5432는 App EC2 보안 그룹에서만 접근하도록 하고 public access를 끈다.
- S3 Block Public Access를 유지한다. 서버 역할에 필요한 prefix 접근만 허용한다. 서명 URL 만료는 기본 120초다.
- App EC2 인스턴스 역할의 표준 AWS 자격 증명 체인을 사용한다. 액세스 키를 프론트 번들에 넣지 않는다.
- Docker 안에서 EC2 역할을 사용하는 경우 IMDSv2와 컨테이너의 응답 hop limit을 점검한다. AWS는 컨테이너 환경의 hop limit 2를 안내한다. [EC2 메타데이터 설정](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-IMDS-new-instances.html).

S3는 SSE-S3로 저장한다. 애플리케이션에 필요한 권한 예시는 다음과 같다. `REGION`, `ACCOUNT_ID`, `BUCKET`은 실제 값으로 바꾸며, collection prefix를 바꾸면 ARN 범위도 함께 바꾼다. 정책은 실제 계정에서 검증하지 않았다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::BUCKET"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::BUCKET/moacut/*"
    },
    {
      "Effect": "Allow",
      "Action": ["rekognition:DetectFaces", "rekognition:CompareFaces", "rekognition:DetectLabels", "rekognition:CreateCollection"],
      "Resource": "*",
      "Condition": {"StringEquals": {"aws:RequestedRegion": "REGION"}}
    },
    {
      "Effect": "Allow",
      "Action": ["rekognition:DescribeCollection", "rekognition:IndexFaces", "rekognition:SearchFaces", "rekognition:DeleteFaces", "rekognition:DeleteCollection"],
      "Resource": "arn:aws:rekognition:REGION:ACCOUNT_ID:collection/moacut-*"
    }
  ]
}
```

기준 사진 비교만 쓸 경우 컬렉션 관련 권한은 필요 없다. 등록 없는 인물 묶기를 요청하면 앱이 앨범별 컬렉션을 생성하고 인덱싱한다. 실제 호출과 저장에는 비용이 발생할 수 있으므로 계정별 할당량과 운영 예산을 설정한 후 켠다. [Rekognition API·리전·할당량](https://docs.aws.amazon.com/general/latest/gr/rekognition.html).

## 기존 EC2에 앱 배치

다음은 이미 준비된 EC2·RDS·S3를 사용하는 수동 배치 예다. 이미지 레지스트리 push는 수행하지 않았으며, 두 EC2에서 같은 소스를 빌드하거나 별도의 승인된 이미지 배포 경로를 사용한다. 공개 웹 이미지에 포함된 데모 사진의 재배포 권리는 [ASSETS.md](ASSETS.md)에 설명한 대로 먼저 확인하거나 자산을 교체한다.

```sh
docker build -f infra/backend.Dockerfile -t moacut-backend:release-1 .
docker build -f infra/frontend.Dockerfile -t moacut-web:release-1 .
```

App EC2의 `/etc/moacut/runtime.env`에 다음 형태로 설정한다. 비밀번호는 URL에 맞게 인코딩한다. 이 파일은 저장소 밖에서 관리하며 운영자만 읽을 수 있도록 설정한다.

```dotenv
DATABASE_URL=postgresql+psycopg://APP_USER:URL_ENCODED_PASSWORD@RDS_ENDPOINT:5432/moacut?sslmode=verify-full&sslrootcert=/run/certs/global-bundle.pem
STORAGE_BACKEND=s3
S3_BUCKET=PRIVATE_BUCKET
S3_PREFIX=moacut/
AWS_REGION=us-east-1
FACE_ANALYSIS_PROVIDER=rekognition
REKOGNITION_COLLECTION_PREFIX=moacut-
DEMO_ENABLED=false
COOKIE_SECURE=true
ALLOWED_ORIGINS=https://YOUR_DOMAIN
WORKER_CONCURRENCY=2
WORKER_MAX_ATTEMPTS=3
WORKER_LEASE_SECONDS=300
AWS_TIMEOUT_SECONDS=20
```

RDS CA bundle을 AWS truststore에서 받아 읽기 전용으로 마운트한다. `verify-full`은 CA와 서버 호스트 이름을 검증한다. [RDS PostgreSQL TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html), [공식 CA bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html).

```sh
sudo mkdir -p /etc/moacut
sudo curl --fail --location https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -o /etc/moacut/global-bundle.pem
sudo chmod 600 /etc/moacut/runtime.env
sudo chmod 644 /etc/moacut/global-bundle.pem
docker run --rm --env-file /etc/moacut/runtime.env -v /etc/moacut/global-bundle.pem:/run/certs/global-bundle.pem:ro moacut-backend:release-1 alembic -c backend/alembic.ini upgrade head
docker run -d --name moacut-api --restart unless-stopped --env-file /etc/moacut/runtime.env -v /etc/moacut/global-bundle.pem:/run/certs/global-bundle.pem:ro -p 8000:8000 moacut-backend:release-1
docker run -d --name moacut-worker --restart unless-stopped --env-file /etc/moacut/runtime.env -v /etc/moacut/global-bundle.pem:/run/certs/global-bundle.pem:ro moacut-backend:release-1 python -m app.worker
```

Web EC2에서는 `APP_PRIVATE_IP`를 실제 App EC2 사설 IP로 바꿔 실행한다. Nginx 구성의 `api` 호스트가 이 주소로 연결된다. 외부 HTTPS는 앞단 진입점에서 종료하고 Web EC2의 80번 포트 접근 범위를 제한한다.

```sh
docker run -d --name moacut-web --restart unless-stopped --add-host api:APP_PRIVATE_IP -p 80:80 moacut-web:release-1
curl --fail https://YOUR_DOMAIN/api/health/ready
```

회원가입·로그인·기준 인물 등록·원본 업로드·분석·승인·다운로드·삭제를 검증한다. readiness는 DB 연결과 스키마 접근만 확인하며 AWS 권한이나 worker 정상 처리까지 증명하지 않는다. [AI_VALIDATION.md](AI_VALIDATION.md)의 실사진 검증을 별도로 수행한다.

## 백업과 롤백

로컬 DB 백업은 비밀번호를 명령행에 노출하지 않고 컨테이너 내부 인증을 사용한다. 사진 볼륨과 DB는 같은 시점의 스냅샷으로 보관해야 참조가 일치한다. 일관된 수동 백업을 위해 쓰기와 worker를 잠시 멈춘다.

```sh
mkdir -p backups
docker compose stop api worker
docker compose exec -T db pg_dump -U moacut -d moacut -Fc > backups/moacut.dump
docker run --rm -v moacut_photos:/source:ro -v "$PWD/backups":/backup alpine:3.22 tar -czf /backup/photos.tar.gz -C /source .
docker compose start api worker
```

`moacut_photos`는 기본 프로젝트 이름 기준이다. 다른 이름으로 시작했다면 `docker volume ls`로 실제 이름을 확인한다. 운영은 RDS 스냅샷·PITR와 S3 버전 보존 정책을 별도로 구성한다.

이미지 롤백은 이전 이미지가 남아 있고 해당 DB 스키마와 호환될 때만 한다. 예를 들어 배포 시 `MOACUT_IMAGE_TAG=release-2`로 빌드했다면 이전 태그로 앱만 되돌릴 수 있다.

```sh
MOACUT_IMAGE_TAG=release-1 docker compose up -d --no-build --no-deps api worker web
```

현재 스키마는 `0002`까지 있으며 `0002`는 지연 정리 의도의 `not_before` 열을 추가한다. 현재 앱은 이 열을 사용한다. 스키마를 되돌릴 때는 쓰기를 멈추고 백업 후, 이전 앱 버전과 함께 검토한 migration만 적용한다.

```sh
docker compose stop api worker
docker compose run --rm --no-deps migrate alembic -c backend/alembic.ini current
# 이전 코드와의 호환성 및 백업을 확인한 경우에만:
docker compose run --rm --no-deps migrate alembic -c backend/alembic.ini downgrade 0001
```

위 downgrade 뒤 현재 앱을 그대로 시작하면 안 된다. 초기 migration의 `downgrade base`는 테이블을 제거하므로 일반적인 앱 롤백 절차로 사용하지 않는다. RDS에서는 새 DB로 백업을 복구해 검증한 뒤 연결을 전환하는 방법도 가능하다.

## 정리와 장애 확인

사용자가 앱에서 앨범·사진·인물을 삭제하면 파일과 해당 인덱스 정리가 DB outbox에 등록된다. 재시도는 worker가 약 30초마다 처리한다. 수동으로 한 번 실행하려면 다음을 사용한다.

```sh
docker compose exec api python -c 'from app.services import drain_cleanup; drain_cleanup()'
docker compose exec -T db psql -U moacut -d moacut -c 'SELECT status, count(*) FROM analysis_jobs GROUP BY status;'
docker compose exec -T db psql -U moacut -d moacut -c 'SELECT count(*) AS pending_cleanup FROM file_cleanup;'
docker compose logs --tail=200 worker
```

Rekognition 인덱싱 직후 프로세스가 중단되면 DB에 연결되지 않은 얼굴 인덱스가 남을 수 있다. 재시도는 같은 이미지·외부 ID로 중복 인덱싱을 피하고, 앨범 삭제는 컬렉션 전체를 정리한다. 장기 운영에서는 원격 컬렉션과 DB를 대조해야 하며 현재 자동 대조 도구는 없다. 계정에서 컬렉션을 조회하거나 폐기할 때는 정확한 ID를 확인한다.

```sh
aws rekognition list-collections --region us-east-1
# 앱에서 삭제한 앨범의 잔여 컬렉션임을 확인한 뒤에만:
aws rekognition delete-collection --region us-east-1 --collection-id EXACT_COLLECTION_ID
```

`docker compose down`은 컨테이너와 네트워크를 정리하고 DB·사진 볼륨은 보존한다. 백업이 있고 로컬 데모 데이터를 완전히 폐기하려는 경우에만 `docker compose down --volumes`를 사용한다. AWS 리소스 종료와 버킷·RDS 삭제는 앱 삭제와 별개이며, 실행한 리소스 목록과 백업을 확인한 뒤 운영자가 수행해야 한다.
