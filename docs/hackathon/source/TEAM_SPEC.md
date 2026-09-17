# AWS 3-Tier 기반 Vision AI 여행 사진 자동 큐레이션 플랫폼

## ZZik

## 1. 한 줄 소개

**“여행 사진 2,000장을 올리면 AI가 누가 나온 사진인지 자동으로 정리하고, 잘 나온 사진까지 추천해주는 공유 앨범.”**

ZZik은 여행 후 발생하는 수천 장의 비정형 이미지 데이터를 AI가 분석해 **인물·단체·장면·장소·사진 품질 기준으로 구조화하는 Vision AI 기반 사진 큐레이션 플랫폼**이다.

핵심 목표는 단순하다.

> **AI가 정리하고, 사람은 고르기만 한다.**

---

# 2. Problem

## 여행은 끝났지만 사진 정리는 이제 시작이다

4명이 여행을 가서 각자 500장씩 촬영하면 약 2,000장의 사진이 생긴다.

현재는 누군가 이 사진을 모두 확인하면서

* 누가 나온 사진인지
* 개인사진인지 단체사진인지
* 누구에게 보내야 하는지
* 비슷한 사진 중 어떤 사진이 잘 나왔는지

직접 판단해야 한다.

그 결과 한 명에게 사진 정리 부담이 집중되고, 사람별로 수백 장을 다시 전송해야 하며, 누락된 사진을 찾고 재전송하는 작업까지 반복된다.

또한 비슷한 연사 사진 중 눈을 감지 않았는지, 흔들리지 않았는지, 밝기가 적절한지를 하나씩 비교해야 한다.

즉 문제의 본질은 단순한 사진 공유가 아니다.

> **수천 장의 비정형 이미지 데이터를 사람이 직접 분류하고 평가해야 하는 문제이다.**

---

# 3. Core Insight

현재 사람이 사진마다 수행하는 작업은 다음과 같다.

**사진 확인**

→ **인물 식별**

→ **단체 여부 판단**

→ **상황·장소 파악**

→ **사진 품질 평가**

→ **분류**

→ **공유**

ZZik은 이 과정 중 반복적인 판단을 Vision AI가 대신 수행한다.

따라서 사용자는 2,000장의 사진을 모두 볼 필요 없이 AI가 구조화한 결과와 추천 사진만 확인하면 된다.

> **“AI가 2,000번 보고, 사람은 20번 고른다.”**

---

# 4. Solution

## AI Smart Curation Engine

사용자는 사진을 정리하지 않고 여행 앨범에 그대로 업로드한다.

이후 시스템이 자동으로 처리한다.

```text
여행 사진 업로드
        ↓
S3 원본 저장
        ↓
AI 이미지 분석
        ↓
얼굴 / 인물 / 장면 / 품질 분석
        ↓
구조화된 Metadata 생성
        ↓
Smart Album 생성
        ↓
AI Best Pick 추천
        ↓
사용자는 원하는 사진만 선택
```

---

# 5. AI Feature 1

## Multi-Face Detection & Matching

Amazon Rekognition을 활용해 사진 속 얼굴을 탐지하고 등록된 여행 멤버와 비교한다.

예를 들어 멤버가 A, B, C, D라면 각 사진을 분석하여

* A가 나온 사진
* B가 나온 사진
* C가 나온 사진
* D가 나온 사진

을 자동으로 연결한다.

### 개인별 Smart Album

사용자는 별도의 사진 전달을 기다리지 않고 자신의 이름을 선택해

**“내가 나온 사진”**

만 바로 확인할 수 있다.

### 단체사진 자동 분류

한 사진에서 감지된 얼굴 수를 기준으로

* 얼굴 없음
* 개인사진
* 2인 이상 단체사진

을 자동 구분한다.

추가적으로 인물 조합을 분석해

* A + B
* A + C
* A + B + C + D

등의 조합도 저장한다.

따라서 **“4명이 모두 나온 사진”** 같은 그룹을 자동 생성할 수 있다.

---

# 6. AI Feature 2

## Scene & Context Recognition

사진 속 객체와 배경 정보를 분석하여 사진의 상황을 구조화한다.

예:

* Beach
* Sea
* Food
* Cafe
* Nature
* Building
* Night
* Outdoor

분석 결과를 기반으로 `#바다`, `#음식`, `#카페`, `#야경` 등의 장면 태그를 생성한다.

추가적으로 EXIF 정보에서 촬영 시간과 GPS 정보를 추출하여 장소 기반 분류로 확장한다.

---

# 7. AI Feature 3

## Best-shot Recommendation

같은 장면에서 촬영된 비슷한 사진을 하나의 후보 그룹으로 묶고 각 사진의 품질을 평가한다.

평가 요소는 다음과 같다.

* Blur
* Sharpness
* Exposure
* Brightness
* 얼굴 상태
* 눈 감음
* 유사 사진 여부

이를 기반으로 같은 사진 그룹 안에서 가장 좋은 사진을 **AI Pick ★**으로 추천한다.

AI가 사진을 삭제하는 것이 아니라 후보를 추천하고 최종 결정은 사람이 한다.

---

# 8. 사진 검색 및 Smart Album

AI 분석 결과는 사진별 Metadata로 저장한다.

```json
{
  "photoId": "photo_001",
  "people": ["person_A", "person_B"],
  "faceCount": 2,
  "photoType": "group",
  "labels": ["Beach", "Outdoor"],
  "location": "Jeju",
  "bestShotScore": 0.91,
  "analysisStatus": "completed"
}
```

이 Metadata를 이용해 자동으로

* 전체 사진
* A의 사진
* B의 사진
* 단체사진
* 얼굴 미검출 사진
* 장소별 사진
* AI 추천 사진

등을 제공한다.

향후에는 **“바다에서 네 명이 같이 찍은 사진”**과 같은 자연어 검색까지 확장한다.

---

# 9. Collaboration Feature

## 사진을 고른 이후의 과정까지 연결

AI가 사진을 정리한 뒤에는 그룹원이 최종 사진을 선택하고 보정하는 과정이 이어진다.

이를 위해 ZZik은 간단한 사진 협업 기능을 제공한다.

### 보정 버전 관리

원본은 항상 유지하고 보정값만 별도 Version으로 저장한다.

```text
Original

 ├─ Version 1
 │   Brightness +10
 │
 ├─ Version 2
 │   Brightness +10
 │   Saturation -5
 │
 └─ Version 3
     Crop
     Warm Filter
```

각 Version에는 작성자, 생성 시각, 이전 Version, 보정값을 저장한다.

---

# 10. Non-destructive Editing

원본 이미지 자체를 계속 수정하지 않는다.

```text
brightness = +10
saturation = -5
contrast = +3
crop = [...]
```

와 같은 Edit Operation을 저장한다.

원본 파일은 S3에 그대로 유지한다.

사용자가 최종 보정본을 다운로드할 때 **원본 + Edit Operation**을 적용하여 결과 이미지를 생성한다.

---

# 11. Approval Workflow

각 보정 Version에는 그룹원이 승인할 수 있다.

```text
Version 1
👍 1

Version 2
👍 4
→ FINAL
```

일정 승인 기준을 충족한 Version을 최종본으로 지정한다.

이를 통해 카카오톡에서 반복되는 보정 피드백을 앱 내부 Workflow로 옮긴다.

---

# 12. AWS 3-Tier Architecture

ZZik은 AWS 기반 **3-Tier Architecture**로 구성한다.

```text
                   User
                    │
                  HTTPS
                    │
                    ▼
┌────────────────────────────────┐
│      Presentation Tier         │
│                                │
│          Web EC2               │
│           Nginx                │
│      React Frontend            │
└──────────────┬─────────────────┘
               │ /api
               ▼
┌────────────────────────────────┐
│      Application Tier          │
│                                │
│          App EC2               │
│         FastAPI                │
│                                │
│  Album / Photo / AI / Edit     │
│      Business Logic            │
└───────┬───────────┬────────────┘
        │           │
        │           ├──────────────→ Amazon Rekognition
        │
        ├──────────────────────────→ Amazon S3
        │
        ▼
┌────────────────────────────────┐
│          Data Tier             │
│                                │
│       RDS PostgreSQL           │
│                                │
│ User / Album / Photo           │
│ Face Mapping / Metadata        │
│ Version / Approval             │
└────────────────────────────────┘
```

---

# 13. Tier 1 — Presentation Tier

## Web EC2 + Nginx + React

Presentation Tier는 사용자 화면과 API 요청 전달을 담당한다.

Web EC2 내부에 React Frontend Build와 Nginx를 구성한다.

Nginx는 `/` 요청에는 React 화면을 제공하고 `/api/*` 요청은 Application Tier의 FastAPI 서버로 전달한다.

### 주요 화면

* 앨범 목록
* 앨범 생성
* 인물 등록
* 사진 다중 업로드
* 분석 진행 상태
* 사진 갤러리
* 인물별 필터
* 사진 상세
* AI Pick
* 보정
* Version History
* 승인

---

# 14. Tier 2 — Application Tier

## App EC2 + FastAPI

서비스 핵심 Business Logic은 App EC2에서 동작한다.

Backend Framework는 **FastAPI**를 사용한다.

주요 API 영역은 Album, Person, Photo, AI, Version, Approval API로 구성한다.

---

# 15. AI Processing Flow

```text
사진 업로드
   ↓
FastAPI
   ↓
S3 원본 저장
   ↓
Photo ID 생성
   ↓
RDS
status = pending
   ↓
분석 요청
   ↓
status = processing
   ↓
Amazon Rekognition
   ↓
얼굴 탐지 / 비교
   ↓
AI 분석 모듈
   ↓
Metadata 생성
   ↓
RDS 저장
   ↓
status = completed
```

분석 중 문제가 발생하면 `status = failed`와 실패 원인을 저장하여 재분석할 수 있도록 한다.

---

# 16. Tier 3 — Data Tier

## Amazon RDS PostgreSQL

주요 Entity는 다음과 같다.

```text
Album
Person
Photo
PhotoPerson
PhotoMetadata
EditVersion
Approval
```

사진 파일 자체는 DB가 아니라 Amazon S3에 저장한다.

---

# 17. Amazon S3

저장 대상:

* 기준 얼굴 이미지
* 원본 사진
* 보정 결과 이미지

S3 Bucket은 Public으로 공개하지 않는다.

Application Tier를 통해 권한을 확인한 뒤 임시 접근 주소를 생성하는 방식으로 조회 및 다운로드한다.

---

# 18. Security

```text
Internet
   ↓
Web EC2
   ↓
App EC2
   ↓
RDS
```

Web EC2는 외부 HTTPS 접근을 허용하고, App EC2는 Web Tier에서 오는 요청 중심으로 제한한다.

RDS는 App Tier에서만 접근 가능하도록 구성한다.

S3는 Private Bucket으로 운영하고, Rekognition과 S3 접근은 App EC2의 IAM 권한을 이용한다.

---

# 19. 팀 구성

```text
1번 ─ AWS Infra / Deployment
2번 ─ Frontend
3번 ─ Backend / DB
4번 ─ Vision AI
5번 ─ Editing / Version / Approval
```

모든 기능은 개별 개발 완료가 아니라

> **화면 + API + DB + 필요한 AI 기능이 실제 AWS 환경에서 연결된 시점**

을 완료 기준으로 한다.

---

# 20. 1번 담당

## AWS 3-Tier Infrastructure & Deployment

### Presentation Tier

* Web EC2 생성
* Nginx 설치 및 실행
* React Build 배포
* SPA Routing 설정
* `/api` Reverse Proxy 설정
* 사진 업로드 용량 제한 설정
* 도메인·HTTPS·접속 주소 설정

### Application Tier

* App EC2 생성
* Python 및 공통 Backend Dependency 설치
* FastAPI 배포
* 실행 Port 설정
* Backend Process Service 등록
* 환경변수 관리
* Backend Logging 설정

### Data Tier

* RDS PostgreSQL 생성
* DB 계정 및 Connection 설정
* Web → App → RDS Network 구성
* Security Group 구성
* Private S3 Bucket 생성
* S3·Rekognition IAM Permission 구성

### Deployment

* Frontend 배포
* Backend 배포
* DB Migration 적용
* 기능 Merge 후 실제 AWS 환경 검증
* Rollback 절차 준비
* AWS Resource 정리 절차 작성

---

# 21. 2번 담당

## Frontend / Album / Upload / Gallery

주요 업무:

* React 프로젝트 구조
* 공통 UI
* 앨범 생성 및 목록
* 인물 등록
* 다중 사진 업로드
* 파일별 업로드 상태
* 분석 진행 상태
* 전체 사진 Grid
* 인물별 Filter
* 단체사진 Filter
* 얼굴 미검출 Filter
* 사진 상세
* 원본 다운로드
* 오분류 수동 수정
* Scene Tag
* 장소 필터
* AI Pick
* 자연어 검색 UI

---

# 22. 3번 담당

## Backend / DB / API Integration

주요 업무:

* FastAPI Application 및 Router 구조
* Health Check
* DB Connection
* Error Response
* DB Model
* Migration
* Album API
* Person API
* Photo API
* S3 저장
* 분석 상태 관리
* AI Module 통합
* Metadata 저장
* Gallery API
* 다운로드 API
* 오분류 수정 API
* 4번 AI Module 통합
* 5번 Version·Approval API 및 Model 통합

3번은 **전체 Backend 통합의 중심 담당자**이다.

---

# 23. 4번 담당

## Vision AI / Face Analysis / Recommendation

주요 업무:

* 기준 얼굴 검사
* Face Detection
* Face Count
* Face Matching
* Similarity 계산
* Multi-person Matching
* `no_face / solo / group` 구분
* 미등록 얼굴 처리
* AI 오류 및 Timeout 처리
* 자동 얼굴 Clustering
* Scene Tag
* EXIF / GPS
* 유사 사진 Group
* Blur / Exposure 평가
* Eye Detection
* Best Shot
* 자연어 검색용 AI 기능

AI 결과는 Backend에서 사용할 수 있는 구조화된 값으로 3번에게 전달한다.

---

# 24. 5번 담당

## Editing / Version / Approval

주요 업무:

* 밝기·채도 보정
* Preview
* Reset
* 원본 비교
* Version 저장
* Version History
* 이전 Version 불러오기
* Diff Slider
* 승인
* 승인 취소
* 중복 승인 방지
* 최종본 확정
* 보정 결과 이미지 Export
* Branch
* Label
* Comment
* 수정 요청
* Kanban
* Notification 확장

화면 코드는 2번 Frontend에 통합하고 API와 Model은 3번 Backend에 통합한다.

---

# 25. 팀 간 연결 구조

```text
             [ 1번 ]
       AWS / Deployment
              │
    ┌─────────┼──────────┐
    │         │          │
    ▼         ▼          ▼
 [2번]      [3번]      AWS
Frontend   Backend      Infra
              │
       ┌──────┴──────┐
       │             │
       ▼             ▼
    [4번]          [5번]
      AI        Version/API
```

```text
Frontend Integration → 2번
Backend Integration  → 3번
AWS Deployment       → 1번
AI Module            → 4번
Editing Feature      → 5번
```

---

# 26. 기능별 Merge 순서

## Phase 1 — 기본 3-Tier

### M01

3-Tier 기본 연결

```text
Web
 ↓
FastAPI
 ↓
RDS
```

### M02

앨범 생성 및 목록

### M03

기준 인물 등록

---

# 27. Phase 2 — 핵심 MVP

### M04

사진 다중 업로드

### M05

AI 얼굴 분석

### M06

인물별 Gallery

### M07

사진 상세 및 원본 다운로드

### M08

오분류 수동 수정

여기까지 완성하면 ZZik의 핵심 문제인

> **“누가 나온 사진인지 자동으로 나눠준다.”**

를 시연할 수 있다.

---

# 28. Phase 3 — 협업 기능

### M09

기본 보정 및 Version 저장

### M10

Version History 및 비교

### M11

승인 및 최종본

### M12

보정 이미지 Export

여기까지 구현하면

> **정리 → 선택 → 보정 → 합의**

라는 전체 서비스 Workflow가 완성된다.

---

# 29. Phase 4 — AI 확장

### M13

Scene / Location

### M14

Best Shot

### M15

사전 등록 없는 얼굴 Clustering

### M16

자연어 검색

### M17

Branch / Label / Comment / Kanban / Notification

---

# 30. MVP Priority

## P0 — 반드시 완성

* AWS 3-Tier 연결
* 앨범 생성
* 인물 등록
* 다중 사진 업로드
* S3 원본 저장
* Rekognition Face Analysis
* 인물별 자동 분류
* 단체사진 분류
* Gallery
* 원본 다운로드

## P1 — 해커톤 AI 어필

* 유사 사진 그룹
* Blur / Quality 분석
* Best Shot 추천
* Scene Tag

## P2 — 서비스 차별화

* 보정
* Version History
* Diff
* Approval
* Final Photo

## P3 — 확장

* 자연어 검색
* 자동 얼굴 Clustering
* Branch
* Label
* Comment
* Kanban
* Notification

---

# 31. 핵심 Demo Scenario

### STEP 1

여행 앨범 생성

**“제주도 3박 4일”**

### STEP 2

여행 멤버 등록

```text
지수
민지
수진
예진
```

### STEP 3

여행 사진 100장을 한 번에 업로드한다.

### STEP 4

AI 분석 상태 표시

```text
분석 중 73 / 100
```

### STEP 5

분석 완료

```text
전체             100

지수              32
민지              41
수진              37
예진              35

단체사진           18
얼굴 미검출         7
```

### STEP 6

“지수” 선택

→ 지수가 등장하는 사진만 자동 표시

### STEP 7

“단체사진” 선택

→ 여러 명이 등장하는 사진만 표시

### STEP 8

AI Pick

→ 유사 사진 중 추천 사진 표시

### STEP 9

단체사진 보정 및 새 Version 저장

### STEP 10

그룹원 승인

```text
Version 2

👍 4

FINAL
```

---

# 32. Before → After

## Before

```text
2,000장 촬영
 ↓
2,000장 직접 확인
 ↓
인물별 분류
 ↓
갠톡으로 전달
 ↓
누락 확인
 ↓
비슷한 사진 비교
 ↓
단체사진 선정
 ↓
보정
 ↓
카톡 피드백
 ↓
재보정
```

## After

```text
사진 업로드
 ↓
AWS 저장
 ↓
Vision AI 분석
 ↓
인물별 자동 분류
 ↓
AI Best Pick
 ↓
그룹 선택
 ↓
Version 관리
 ↓
승인
 ↓
최종 사진
```

---

# 33. 기술적 차별점

ZZik의 핵심은 단순히 Rekognition API 한 번을 호출하는 것이 아니다.

```text
Unstructured Image
        ↓
Vision AI
        ↓
Structured Metadata
        ↓
Database
        ↓
Smart Album
        ↓
Recommendation
        ↓
Collaboration
```

Vision AI가 이미지 데이터를 서비스에서 사용할 수 있는 구조화된 정보로 변환한다.

---

# 34. 서비스 차별점

기존 사진 서비스는 보통 사용자가 원하는 사진을 **검색**하도록 돕는다.

ZZik은 검색 이전에 AI가 먼저 사진을 분석한다.

기존 방식:

> “내 사진 어디 있지?”

사용자가 직접 찾는다.

ZZik:

> “지수 사진 128장”

> “4명 단체사진 47장”

> “AI 추천 12장”

을 미리 만들어준다.

따라서 ZZik은

> **Search 중심 서비스가 아니라 Curation 중심 서비스이다.**

---

# 35. 최종 Pitch Message

여행에서 사진을 찍는 것은 즐겁다.

하지만 여행 후 2,000장의 사진을 정리하는 순간부터 사진은 추억이 아니라 일이 된다.

ZZik은 사람이 사진을 하나하나 확인하며 수행하던

**인물 식별, 분류, 품질 평가**

를 Vision AI가 대신한다.

그리고 AWS 3-Tier Architecture를 기반으로

**업로드 → AI 분석 → 자동 분류 → 추천 → 보정 → 승인**

까지 하나의 서비스로 연결한다.

> **“AI가 2,000번 보고, 사람은 20번 고른다.”**

이것이 ZZik이 해결하려는 문제이다.
