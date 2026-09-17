# 분석 검증 기록

## 현재 AWS 확인 범위

2026-09-17 `us-east-1` AWS 콘솔에서 생성 사진의 `DetectFaces`와 `CompareFaces` 호출에 성공했다. 기준 인물 1명 일치·다른 인물 1명 불일치를 확인했다. **콘솔 검사이며 앱의 EC2 역할·S3 연결 성공을 의미하지 않는다.** 자동 검증기와 제한 조건은 [AWS_EDU_VALIDATION.md](AWS_EDU_VALIDATION.md), 데이터와 생성 프롬프트는 [합성 검증 사진](../backend/fixtures/aws-validation/README.md)에 있다.

## 기존 로컬 검증 범위

2026-09-16 기준 로컬 테스트는 분석 계약·DB 상태·재시도·보존 규칙을 확인했다. 실제 AWS 계정, S3 버킷, 역지오코딩 서비스에는 연결하지 않았다. 실제 사진 데이터셋에 대한 얼굴 인식 정확도·처리량·비용 측정은 하지 않았다.

```sh
.venv/bin/python -m pytest backend/tests/test_analysis_worker.py -q
```

현재 이 파일의 테스트 10개가 통과한다.

| 검증 | 확인한 결과 |
|---|---|
| fixture 파일 해시 | 등록 파일만 지정 결과를 반환; 해시 위조·알 수 없는 사진은 실패 |
| 기준 얼굴 등록 | 얼굴 없음과 얼굴 여러 개를 다른 오류로 처리 |
| 샘플 신원 연결 | 기준 이미지의 fixture 신원과 등록 프로필을 연결; 표시 이름만으로 연결하지 않음 |
| 파일 보존 | 분석 실패 후 원본 파일·사진 행 유지 |
| 수동 수정 | 재분석과 그룹 재연결 이후 수동 추가·제외 유지 |
| worker 회복 | lease 만료 작업 회수, 이전 토큰의 저장 차단, 제한된 재시도 |
| 실제 모드 오류 | AWS 인증 실패를 fixture 성공으로 바꾸지 않음 |
| 실제 어댑터 단위 검증 | 모의 AWS 응답으로 얼굴 위치 연결·후보 점수 차이·장면 라벨 확인 |
| 인물 그룹 | 모의 AWS 응답으로 모든 FaceId 검색, 앨범 격리, 기존 배치 보존 |
| 유사 사진 | 촬영 시간이 없을 때 다른 원본을 임의로 같은 순간으로 묶지 않음 |

모의 AWS 응답을 이용한 검사는 호출 구성과 후처리를 확인할 뿐, AWS 서비스가 실제 사진을 얼마나 잘 인식하는지는 검증하지 않는다. fixture 사진의 예시 얼굴 위치와 점수도 정확도 평가에 사용하지 않는다. 자산 출처는 [ASSETS.md](ASSETS.md)를 참고한다.

## 실제 분석 방식과 한계

`FACE_ANALYSIS_PROVIDER=rekognition`은 정규화한 JPEG로 `DetectFaces`를 먼저 호출한다. 얼굴이 있으면 같은 앨범의 기준 사진마다 `CompareFaces`를 호출하고 얼굴 위치를 대응시킨다. 기본 임계값은 90, 상위 두 후보의 최소 점수 차이는 5다. 환경변수로 변경할 수 있으며, 이 수치는 이번 데이터로 최적화하거나 정확도를 보장한 값이 아니다.

등록 인물이 N명이면 정상적인 얼굴 있는 사진은 대체로 `DetectFaces` 1회 + `CompareFaces` N회 + `DetectLabels` 1회다. 얼굴 없는 사진은 비교 호출을 생략한다. 작업별 호출 수와 시간이 기록되며, 그룹 묶기를 요청하면 컬렉션 조회·인덱싱·얼굴별 검색 호출이 추가된다.

장면 태그는 실제 `DetectLabels` 라벨 중 지원하는 항목만 변환한다. 특정 해변·식당 이름을 이미지에서 지어내지 않는다. 장소명은 GPS와 설정된 외부 역지오코딩의 결과만 사용한다.

AWS 입력은 JPEG/PNG raw bytes 최대 5MB, 가로·세로 각각 최소 80픽셀 제한을 반영한다. 축소로 작은 얼굴이 사라질 수 있고, `CompareFaces`는 대상의 최대 100개 얼굴을 비교한다. 고밀도 단체사진·가림·측면·흔들림·저해상도에 대한 정확도는 별도 검증이 필요하다. [AWS 이미지 제한](https://docs.aws.amazon.com/rekognition/latest/dg/limits.html), [CompareFaces 명세](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_CompareFaces.html).

등록 없는 그룹은 모든 얼굴을 `IndexFaces`로 인덱싱한 뒤 각각 `SearchFaces`로 검색한다. 입력 이미지의 가장 큰 얼굴 하나만 검색하는 `SearchFacesByImage`를 단체사진 전체 결과로 취급하지 않는다. [IndexFaces 명세](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_IndexFaces.html), [SearchFaces 명세](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_SearchFaces.html), [SearchFacesByImage 명세](https://docs.aws.amazon.com/rekognition/latest/APIReference/API_SearchFacesByImage.html).

## 실제 계정 연결 후 검증 절차

1. 재사용과 얼굴 분석에 동의한 사진으로 별도 검증 앨범을 만든다. 사람마다 얼굴 하나인 기준 사진을 등록한다.
2. 얼굴 없음, 1인, 2인 이상, 등록되지 않은 사람, 가림·측면·어두운 장면, EXIF 회전 사진을 각각 업로드한다.
3. 사람이 확인한 얼굴 수와 실제 등장 인물을 정답표에 기록하고 자동 결과와 비교한다. 미확정은 정답으로 간주하지 않는다.
4. 사람 단위 정밀도·재현율, 미확정 비율, 사진별 전체 정답률을 표본 수와 함께 계산한다. 임계값을 조정한 세트와 최종 평가 세트를 분리한다.
5. 처리 시간의 중앙값·상위 95%·실패 수·호출 수를 기록한다. 처리량과 비용은 실제 리전·계정 할당량·샘플 크기를 명시한다.
6. 그룹 이름 변경·연결·분리·병합 후 사진 필터와 승인 재검토를 확인한다. 앨범·인물을 삭제하고 DB outbox, S3 객체, 컬렉션 삭제를 확인한다.

인식 결과는 등장 인물 확인을 돕는다. 승인 요청 전에 사람이 대상을 확인하며, AI 매칭이나 그룹 생성 자체를 게시 동의·승인으로 취급하지 않는다.
