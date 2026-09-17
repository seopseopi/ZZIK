# M01 · 역할 기반 검증 컨테이너

기존 검증기와 합성 사진을 EC2에서 동일하게 실행하기 위한 키트다. 교육 계정의 제한을 유지하는 `education` 설정과 계정·리전을 지정하는 `custom` 설정을 분리했다. EC2·S3·IAM을 생성하거나 앱·DB를 배포하지 않는다. 교육 계정의 실행 조건은 [교육 계정 가이드](AWS_EDU_VALIDATION.md), 다른 환경은 해당 환경의 안내를 따른다.

| 명령 | AWS 접근 | 증명하는 범위 |
|---|---|---|
| `build` | 없음; Docker 이미지/의존성 다운로드는 필요 | 실행 이미지 빌드 |
| `plan` | 없음; 컨테이너 네트워크 차단 | 합성 이미지 입력·호출 상한 |
| `preflight` | STS와 S3 설정 조회 | 인증·역할·버킷 리전/공개 차단/버전 관리, 지정 시 계정·버킷 소유자 |
| `execute` | 임시 객체 쓰기·읽기·삭제 및 Rekognition 이미지 전송 | 실제 저장·다운로드·정리·합성 세트 분석 |

`preflight_passed`는 저장·얼굴 분석 성공을 뜻하지 않는다. S3 객체 작업, Rekognition 권한/분석, 컬렉션, DB, 전체 앱 연결은 검사하지 않는다. 두 원격 명령 모두 기존 EC2의 역할 인증이 필요하다. 조회 요청도 AWS에 접근하므로 `plan`과 구분한다.

## 로컬/CI 사전 검사

저장소 루트에서 Docker Engine이 준비된 상태로 실행한다.

```sh
bash scripts/aws_validation_container.sh build
bash scripts/aws_validation_container.sh plan
```

첫 명령은 `infra/backend.Dockerfile`의 `aws-validation` target을 빌드한다. Python 의존성은 앱 이미지와 같은 잠금 파일을 사용한다. 검증기·앱의 분석/저장 코드·합성 PNG 3장을 포함한다. 마지막 기본 target은 `runtime`으로 유지해 기존 Compose의 API/worker 실행을 보존했다.

두 번째 명령은 `--network none`으로 실행하므로 AWS에 연결할 수 없다. 기준 사진 1장·분석 사진 2장을 읽고 `status=planned`, `aws_requested=false`, 호출 상한 7을 반환해야 한다. 이번 실행의 JSON 보고서는 `data/aws-validation/reports/<UTC 시각>-<프로세스 번호>.json`에 남는다. 계획 결과는 실제 저장/분석 성공을 의미하지 않는다.

이미지 이름은 `ZZIK_VALIDATION_IMAGE`로 바꿀 수 있다. 실행 명령은 로컬에 빌드된 이미지만 사용하며, 같은 이름의 원격 이미지를 자동으로 가져오지 않는다. 이미지에는 빌드한 checkout의 HEAD를 `org.opencontainers.image.revision` 라벨로 기록한다. 재현 시 깨끗한 checkout에서 빌드하고 HEAD와 변경 유무를 함께 확인한다.

## 지정 EC2에서 실제 실행할 때

아래는 **향후 실행 명령**이다. 현재 단계에서는 신규 자원 생성과 실제 컨테이너 AWS 호출을 실행하지 않았다.

1. Linux EC2 역할 인증과 비공개 검증 버킷이 필요하다. 기본 `education` 설정은 `us-east-1`이다. 실제 사용할 때는 그 환경에서 허용된 AMI·인스턴스 유형·기존 프로파일·SG를 확인한다. 전달된 `m5.large` 등은 사용법 교육 당시 값이며 대회 기준이 아니다. [교육 계정 가이드](AWS_EDU_VALIDATION.md). 현재는 신규 자원 생성 보류 상태다.
2. IAM 콘솔에서 해당 인스턴스 프로필에 들어 있는 **실제 역할 이름**을 확인한다. 인스턴스 프로필 이름과 역할 이름은 같다고 가정하지 않는다. 새 역할이나 액세스 키를 만들지 않는다.
3. EC2에서 같은 커밋을 checkout하고 위 `build` 명령을 실행한다. 이 스크립트는 AMI·인스턴스 유형·보안 그룹·예산을 자동 검증하거나 변경하지 않는다.
4. 실제 값을 넣은 뒤 실행한다. 아래 변수에는 비밀키나 콘솔 비밀번호를 넣지 않는다.

```sh
export ZZIK_IAM_USERNAME='YOUR_EDUCATION_USERNAME'
export ZZIK_VALIDATION_BUCKET='YOUR_USERNAME_PREFIXED_TEST_BUCKET'
export ZZIK_EXPECTED_ROLE='ROLE_INSIDE_YOUR_ASSIGNED_INSTANCE_PROFILE'
bash scripts/aws_validation_container.sh preflight
# 조회 결과를 확인하고 실제 사진 전송 검증을 실행할 때:
bash scripts/aws_validation_container.sh execute
```

기본 `ZZIK_VALIDATION_SCOPE=education`은 교육 계정 사용자 이름(`kmuct-edu-숫자`)과 그 이름으로 시작하는 버킷만 허용한다. 리전은 `us-east-1`이며 다른 값을 넣으면 거부한다. 두 설정 모두 Linux EC2·기존 합성 세트·최대 7회 Rekognition 호출을 유지한다. 생성되지 않은 버킷은 자동 생성하지 않는다.

## 다른 계정·리전으로 옮길 때

현재 대회 환경을 정한 것은 아니다. 실제 환경이 제공되면 `custom`을 명시하고 아래 자리표시자를 그 환경의 값으로 바꾼다. 교육용 계정에서 `custom`을 골랐다고 교육 규칙이 면제되는 것은 아니다.

```sh
export ZZIK_VALIDATION_SCOPE=custom
export ZZIK_VALIDATION_REGION=ap-northeast-2  # 예시; 실제 제공 리전으로 변경
export ZZIK_EXPECTED_ACCOUNT='YOUR_12_DIGIT_ACCOUNT_ID'
export ZZIK_EXPECTED_ROLE='YOUR_EC2_ROLE_NAME'
export ZZIK_VALIDATION_BUCKET='YOUR_EXISTING_PRIVATE_TEST_BUCKET'
bash scripts/aws_validation_container.sh plan
# 지정 EC2에서 연결 설정만 조회할 때:
bash scripts/aws_validation_container.sh preflight
```

`custom`의 원격 명령은 리전·12자리 계정 ID·역할·버킷이 모두 있어야 한다. 역할 이름이 같아도 STS 계정이 다르면 S3에 접근하기 전에 중단한다. S3 설정 조회의 `ExpectedBucketOwner`에도 같은 계정 ID를 전달한다. 따라서 다른 계정 소유의 공유 버킷은 이 키트에서 허용하지 않는다. [STS 계정 확인](https://docs.aws.amazon.com/boto3/latest/reference/services/sts/client/get_caller_identity.html), [S3 소유자 확인](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_bucket_location.html).

인증 없이 다른 리전의 입력만 확인하려면 `ZZIK_VALIDATION_SCOPE=custom ZZIK_VALIDATION_REGION=ap-northeast-2 bash scripts/aws_validation_container.sh plan`을 사용한다. 이때 계정·역할·버킷은 생략할 수 있다.

지원 범위는 일반 AWS 파티션의 Linux EC2 역할 인증이다. ECS·SSO·GovCloud·중국 리전은 이 컨테이너 실행기의 검증 대상이 아니다. 버킷 이름은 영문 소문자·숫자·하이픈만 허용하며 기존의 비공개·버전 관리 미사용 검증 전용 버킷 조건을 유지한다. `custom`이 대회 공통 배포기나 운영 버킷 검증기는 아니다.

## 인증과 실행 격리

컨테이너에는 호스트의 `.env`, `~/.aws`, 액세스 키 환경변수를 전달하지 않는다. SDK의 파일 기반 자격 증명 경로를 비우고 IMDSv1을 비활성화한다. 검증기는 다음 순서를 따른다.

- SDK 자격 증명 공급자가 `iam-role`인지 검사한다. 환경변수·프로필·정적 키이면 `EC2_INSTANCE_ROLE_REQUIRED`로 중단한다.
- STS의 assumed-role 이름이 `ZZIK_EXPECTED_ROLE`과 같은지 검사한다. 다르면 `EC2_ROLE_MISMATCH`로 중단한다.
- 계정 ID를 지정하면 STS 계정 일치도 검사한다. `preflight`는 그 뒤 S3 설정만 조회하고 끝낸다. `execute`만 객체 작업과 Rekognition 호출을 진행한다. 결과에는 확인 여부만 추가하며 계정 ID·ARN·키를 기록하지 않는다.

Linux EC2의 검증용 일회성 프로세스에는 host 네트워크를 사용한다. 별도 포트를 열거나 웹 서버를 시작하지 않는다. host 모드는 호스트의 네트워크 공간을 공유하므로 일반 앱 배포에 그대로 적용하지 않는다. [Docker host 네트워크](https://docs.docker.com/engine/network/drivers/host/). EC2의 IMDS 접근이 막혀 있으면 실패로 남기며, 스크립트가 메타데이터 보안 설정을 낮추지 않는다. [AWS IMDS 설정](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html), [Boto3 자격 증명 공급자](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).

루트 파일시스템은 읽기 전용이며 보고서 폴더만 쓰기 가능하게 마운트한다. 컨테이너는 호출한 호스트 사용자의 UID/GID로 실행하고 capabilities를 제거하며, 메모리 512MB·CPU 1·PID 128로 제한한다. 실행 후 컨테이너는 제거되지만 호스트 EC2와 S3 버킷은 남는다. 사용 종료·정리는 [교육 계정 가이드](AWS_EDU_VALIDATION.md)를 따른다.

## 오류 확인

| 결과 | 다음 확인 |
|---|---|
| Docker 실행/이미지 없음 | Docker Engine 상태와 `build` 완료 여부 |
| `EC2_INSTANCE_ROLE_REQUIRED` | 지정 프로필 연결, IMDSv2 접근, AWS 키를 별도로 넣지 않았는지 |
| `EC2_ROLE_MISMATCH` | 프로필 안의 실제 역할 이름과 입력한 이름 |
| `AWS_ACCOUNT_MISMATCH` | 지정 계정 ID와 실행 EC2의 계정이 일치하는지 |
| `AWS_AccessDenied` / `AWS_AccessDeniedException` | 기존 역할의 버킷/분석 권한. 자동 확대하지 않음 |
| `UNVERSIONED_TEST_BUCKET_REQUIRED` | 운영 버킷 대신 버전 관리 미사용 검증 전용 버킷 |
| `S3_CLEANUP_FAILED` | 보고서의 정확한 `remaining_key`만 확인하여 정리 |

GitHub CI의 Compose 작업은 검증 이미지를 실제 빌드하고 교육 리전과 다른 리전의 네트워크 없는 plan을 실행한다. 동시에 기존 Web/API/DB/worker의 E2E·재시작 검사를 계속 수행한다. 조회 명령은 모의 AWS 응답으로 허용된 API·소유자 매개변수·오류 시 중단을 검사한다. CI에는 AWS 인증을 추가하지 않았다. 실제 EC2 역할·S3·Rekognition 연결은 별도 증거가 필요하다.
