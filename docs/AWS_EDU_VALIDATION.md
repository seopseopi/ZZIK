# 교육용 AWS 연결 검증 — M01·M03·M05

## 2026-09-17 확인 결과

북버지니아 `us-east-1`의 AWS 콘솔에 제공받은 IAM 사용자로 로그인했다. 계정 비밀번호·세션·실제 계정 ID는 저장소에 보관하지 않는다.

| 항목 | 실제 확인 | 한계 |
|---|---|---|
| `DetectFaces` | 생성한 `reference-a.png`에서 얼굴 하나 검출 | AWS 콘솔 사용자 권한으로 수행. 앱의 EC2 역할 검증 아님 |
| `CompareFaces` | 기준 사진과 `travel-pair.png` 비교에서 일치 1개, 불일치 1개. 콘솔 일치 similarity 표시 99.9% | 유사도 점수이며 인식 정확도 99.9%라는 뜻이 아님 |
| 콘솔 기본 샘플 | 기본 샘플은 `InvalidS3ObjectException`; 직접 생성 사진 업로드는 성공 | 샘플 S3 접근 오류를 Rekognition 권한 거부로 잘못 판단하지 않음 |
| 기존 EC2 | 제공된 사용자 이름으로 모든 속성 검색 시 일치 없음 | 이름·태그가 다른 리소스의 소유권까지 증명하지 않음 |
| 기존 S3 | 사용자 이름 접두사로 버킷 검색 시 0개 | 다른 사람의 버킷을 대신 사용하지 않음 |
| 실행기 | 로컬 입력 검사 및 AWS 모의 응답 검사 통과 | 실제 역할 기반 실행, S3 저장·서명 다운로드는 아직 미검증 |

콘솔 성공은 서비스 연결 가능성을 확인한다. **현재 앱의 설정은 local/fixture를 유지**하며 AWS 기반 서비스 배포가 완료된 상태는 아니다. `DetectLabels`, EC2 역할의 Rekognition 권한, 인물 컬렉션은 별도 검증이 필요하다. 생성 이미지는 여행 실사진의 정확도·성능 평가에 사용하지 않는다.

## 교육 계정에 적용할 조건

사용자가 제공한 교육 안내를 2026-09-17에 읽고 정리한 범위다. 계정별 실제 권한과 수업 공지가 우선한다.

- 리전: `us-east-1`.
- EC2 AMI: `nxtcloud-ami-v`로 시작하는 지정 이미지. 임의 Ubuntu/Amazon Linux AMI로 대체하지 않는다.
- EC2 인스턴스: `t3.nano`~`t3.small`; 기존 `SafeInstanceProfile-<IAM_USERNAME>` 사용.
- Lambda 등 비 EC2: 기존 `SafeRole-<IAM_USERNAME>` 사용. 신규 IAM 역할을 만들지 않는다.
- **액세스 키 발급 금지.** 콘솔 비밀번호는 SDK 자격 증명이 아니다. 이 계정의 검증기는 지정 역할이 붙은 AWS 실행 환경에서 실행한다. 로컬 `aws configure` 또는 GitHub Secrets에 장기 키를 넣는 절차를 안내하지 않는다.
- S3 이름은 자기 IAM 사용자 이름으로 시작해야 한다. Block Public Access를 유지하고 다른 교육생의 리소스를 수정하지 않는다.
- 안내 허용 목록: EC2, Lambda, RDS, DynamoDB, S3, API Gateway, Amplify, SQS, SNS; Bedrock은 안내된 미국 리전 사용. Rekognition은 목록에 없지만 이번 콘솔 `DetectFaces`/`CompareFaces`는 성공했다. EC2 역할에서의 실행 권한은 별도 확인한다.
- ELB/ASG, CloudFront, ACM, Route53, Cognito, 새 private subnet/라우팅 테이블/VPC endpoint 등은 이 교육 환경의 배포 전제로 삼지 않는다.
- AWS 배포용 GitHub Actions/액세스 키는 사용하지 않는다. 저장소의 현재 CI는 AWS 인증 없는 테스트 및 GitHub Pages 체험판 배포다.
- RDS 공개 접근은 안내 표와 상세 목록이 서로 다르므로 아직 생성하지 않았다. 서버→DB 보안 그룹 접근과 최종 교육 지침을 확인한 뒤 구성한다.

원문의 3-Tier 목표는 유지한다. 교육 환경에서 가능한 네트워크/HTTPS 구성이 확정되기 전에는 [일반 배포 가이드](AWS_DEPLOYMENT.md)의 모든 단계를 그대로 적용하거나 운영 3-Tier 완료라고 표시하지 않는다.

## 다음 실행을 위한 자원 계획

이번 단계의 범위는 **새 자원 생성 없이 준비까지**다. 아래 자원은 생성하지 않았고, EC2·RDS·버킷·IAM 정책을 변경하지 않았다. 이후 실제 실행을 진행할 때 비용 한도와 유지 시간을 정한다.

1. 본인 소유 검증 EC2 한 대: `t3.micro`, 지정 AMI, 기존 `SafeInstanceProfile-<IAM_USERNAME>`, 외부 앱 공개 없이 명령 실행 용도. 생성 전 비용 한도와 사용 시간을 정한다. 사용자 이름 검색에 안 나온 서버를 임의로 재사용하지 않는다.
2. 같은 리전의 `<IAM_USERNAME>-zzik-validation-<고유접미사>` 버킷: 비공개, SSE-S3, **버전 관리를 한 번도 켜지 않은 검증 전용 버킷**. 운영 버킷에는 이 검사를 실행하지 않는다.
3. S3 권한: 해당 버킷의 `GetBucketLocation`, `GetBucketPublicAccessBlock`, `GetBucketVersioning`, `ListBucket`; `zzik-validation/*` 아래 `PutObject`, `GetObject`, `DeleteObject`.
4. Rekognition 권한: `DetectFaces`, `CompareFaces`, `DetectLabels`. 이 검사에는 컬렉션/모델 생성·`ListCollections` 권한이 필요 없다. 기존 역할에 권한이 부족하면 오류를 기록하고 관리자가 허용 여부를 판단한다.

이 단계에서는 RDS·새 IAM 역할·공개 보안 그룹 규칙·로드밸런서를 만들지 않는다. 역할 기반 검사 성공 후 별도 단계에서 전체 서버와 DB를 배치한다.

## 같은 검사를 재현하기

검사기는 [scripts/validate_aws.py](../scripts/validate_aws.py), 합성 사진과 정답표는 [backend/fixtures/aws-validation](../backend/fixtures/aws-validation/README.md)에 있다. 의존성은 기존 `backend/requirements.lock`을 사용한다.

로컬 입력 검사 — AWS 자격 증명을 찾거나 원격 호출하지 않는다:

```sh
.venv/bin/python scripts/validate_aws.py \
  --manifest backend/fixtures/aws-validation/manifest.json \
  --region us-east-1 --max-calls 7
```

지정 역할이 연결된 AWS 실행 환경에서, 실제 검증 버킷 이름을 입력하고 실행한다:

```sh
.venv/bin/python scripts/validate_aws.py \
  --manifest backend/fixtures/aws-validation/manifest.json \
  --region us-east-1 --bucket YOUR_PRIVATE_TEST_BUCKET \
  --max-calls 7 --execute \
  --report data/aws-validation/live-run-01.json
```

`--execute`는 사진 전송과 소량의 과금 가능한 AWS 호출을 수행한다. `--max-calls`는 Rekognition 호출 상한이지 달러 예산이 아니다. 기본 데이터는 기준 사진 1장·분석 사진 2장, 최대 7회다. 얼굴 없는 사진은 비교를 생략하므로 정상 실행은 6회가 예상된다. EC2 실행 시간, S3 요청·저장 비용은 이 수치에 포함되지 않는다.

검사 순서:

1. 파일 수·크기·디코딩·정답표·경로 이탈을 먼저 검사한다. 기준 사진과 평가 사진이 같은 파일이면 거부한다.
2. STS로 실행 자격 증명이 유효한지 확인한다. 계정 ID·ARN은 결과에 기록하지 않는다.
3. 버킷 리전·공개 차단·버전 관리 상태를 확인한다. `zzik-validation/<실행 UUID>/original` 한 개만 쓴다.
4. 실제 `S3Storage`로 원본을 저장·읽고 SHA-256을 비교한다. SigV4 서명 다운로드도 요청하여 바이트와 attachment 헤더를 확인한다.
5. 성공·실패 모두 이번 실행의 정확한 객체 키만 삭제하고 삭제 여부를 확인한다. PUT 시간 초과도 원격 쓰기 가능성이 있어 정리한다. 삭제 실패는 전체 검사를 실패로 표시하고 `remaining_key`를 남긴다. 다른 prefix·기존 객체는 정리하지 않는다.
6. 실제 `analysis.validate_reference`와 `analysis.analyze`로 분석한다. 실패를 fixture 성공으로 대체하지 않고 호출 수·실패 코드를 기록한다. DB·컬렉션·앱 `.env`는 변경하지 않는다.

출력에는 생성 데이터 여부(`dataset_kind`), 사진 단위 등장 인물 precision/recall, 전체 인물 일치율, 얼굴 수 일치율, 미확정 비율, 성공한 사진 처리 시간 p50/p95를 포함한다. 실패 사진도 정확도·재현율의 분모에서 빼지 않는다. 분모가 0인 값은 `null`이다. 기대 결과와 모두 일치해도 이 작은 합성 세트에서의 결과일 뿐이다.

보고서는 새 파일만 만들며 기존 파일을 덮어쓰지 않는다. 서명 URL·원본 파일명·실제 계정 ID·SDK 원문 오류를 출력하지 않는다. 검증 후 결과와 정리 상태를 확인하고 테스트 서버를 중지한다. EC2 중지 뒤에도 EBS 저장 비용은 남으므로 최종 폐기 시 생성한 자원을 정확히 식별해 정리한다.
