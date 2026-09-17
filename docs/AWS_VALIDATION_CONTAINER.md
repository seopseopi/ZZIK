# M01 · 역할 기반 검증 컨테이너

기존 검증기와 합성 사진을 EC2에서 동일하게 실행하기 위한 키트다. EC2·S3·IAM을 생성하거나 앱·DB를 배포하지 않는다. 실제 AWS 실행 전 조건은 [교육 계정 가이드](AWS_EDU_VALIDATION.md)를 따른다.

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

1. 현재 키트는 교육 계정 검증용으로 `us-east-1`과 Linux EC2 역할 인증을 가정한다. EC2·비공개 검증 버킷을 실제 사용할 때는 그 환경에서 허용된 AMI·인스턴스 유형·기존 프로파일·SG를 확인한다. 전달된 `m5.large` 등은 사용법 교육 당시 값이며 대회 기준이 아니다. [교육 계정 가이드](AWS_EDU_VALIDATION.md). 현재는 신규 자원 생성 보류 상태다.
2. IAM 콘솔에서 해당 인스턴스 프로필에 들어 있는 **실제 역할 이름**을 확인한다. 인스턴스 프로필 이름과 역할 이름은 같다고 가정하지 않는다. 새 역할이나 액세스 키를 만들지 않는다.
3. EC2에서 같은 커밋을 checkout하고 위 `build` 명령을 실행한다. 이 스크립트는 AMI·인스턴스 유형·보안 그룹·예산을 자동 검증하거나 변경하지 않는다.
4. 실제 값을 넣은 뒤 실행한다. 아래 변수에는 비밀키나 콘솔 비밀번호를 넣지 않는다.

```sh
export ZZIK_IAM_USERNAME='YOUR_EDUCATION_USERNAME'
export ZZIK_VALIDATION_BUCKET='YOUR_USERNAME_PREFIXED_TEST_BUCKET'
export ZZIK_EXPECTED_ROLE='ROLE_INSIDE_YOUR_ASSIGNED_INSTANCE_PROFILE'
bash scripts/aws_validation_container.sh execute
```

실행기는 교육 계정 사용자 이름(`kmuct-edu-숫자`)과 그 이름으로 시작하는 버킷만 허용한다. Linux 호스트에서 `us-east-1`, 기존 합성 세트, 최대 7회 호출로 고정한다. 생성되지 않은 버킷은 자동 생성하지 않는다.

이 실행기는 대회 공통 배포기가 아닌 **현재 교육 계정용 검증 키트**다. 대회 계정·리전·권한 체계가 달라지면 해당 제약을 검토하고 테스트와 함께 수정해야 한다. 지금은 불확실한 대회 조건을 예상해 검사를 느슨하게 바꾸지 않는다.

컨테이너에는 호스트의 `.env`, `~/.aws`, 액세스 키 환경변수를 전달하지 않는다. SDK의 파일 기반 자격 증명 경로를 비우고 IMDSv1을 비활성화한다. 검증기는 다음 순서를 따른다.

- SDK 자격 증명 공급자가 `iam-role`인지 검사한다. 환경변수·프로필·정적 키이면 `EC2_INSTANCE_ROLE_REQUIRED`로 중단한다.
- STS의 assumed-role 이름이 `ZZIK_EXPECTED_ROLE`과 같은지 검사한다. 다르면 `EC2_ROLE_MISMATCH`로 중단한다.
- 두 검사를 통과한 뒤에만 기존 S3 검증 및 Rekognition 호출을 진행한다. 결과에는 역할 확인 여부만 추가하며 계정 ID·ARN·키를 기록하지 않는다.

Linux EC2의 검증용 일회성 프로세스에는 host 네트워크를 사용한다. 별도 포트를 열거나 웹 서버를 시작하지 않는다. host 모드는 호스트의 네트워크 공간을 공유하므로 일반 앱 배포에 그대로 적용하지 않는다. [Docker host 네트워크](https://docs.docker.com/engine/network/drivers/host/). EC2의 IMDS 접근이 막혀 있으면 실패로 남기며, 스크립트가 메타데이터 보안 설정을 낮추지 않는다. [AWS IMDS 설정](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html), [Boto3 자격 증명 공급자](https://docs.aws.amazon.com/boto3/latest/guide/credentials.html).

루트 파일시스템은 읽기 전용이며 보고서 폴더만 쓰기 가능하게 마운트한다. 컨테이너는 호출한 호스트 사용자의 UID/GID로 실행하고 capabilities를 제거하며, 메모리 512MB·CPU 1·PID 128로 제한한다. 실행 후 컨테이너는 제거되지만 호스트 EC2와 S3 버킷은 남는다. 사용 종료·정리는 [교육 계정 가이드](AWS_EDU_VALIDATION.md)를 따른다.

## 오류 확인

| 결과 | 다음 확인 |
|---|---|
| Docker 실행/이미지 없음 | Docker Engine 상태와 `build` 완료 여부 |
| `EC2_INSTANCE_ROLE_REQUIRED` | 지정 프로필 연결, IMDSv2 접근, AWS 키를 별도로 넣지 않았는지 |
| `EC2_ROLE_MISMATCH` | 프로필 안의 실제 역할 이름과 입력한 이름 |
| `AWS_AccessDenied` / `AWS_AccessDeniedException` | 기존 역할의 버킷/분석 권한. 자동 확대하지 않음 |
| `UNVERSIONED_TEST_BUCKET_REQUIRED` | 운영 버킷 대신 버전 관리 미사용 검증 전용 버킷 |
| `S3_CLEANUP_FAILED` | 보고서의 정확한 `remaining_key`만 확인하여 정리 |

GitHub CI의 Compose 작업은 검증 이미지를 실제 빌드하고 네트워크 없는 plan을 실행한다. 동시에 기존 Web/API/DB/worker의 E2E·재시작 검사를 계속 수행한다. CI에는 AWS 인증을 추가하지 않았다. 실제 EC2 역할·S3·Rekognition 연결은 별도 증거가 필요하다.
