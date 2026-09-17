<p align="center">
  <img src="docs/assets/zzik-mark.svg" alt="찍" width="64" />
</p>

<h1 align="center">찍 · ZZIK</h1>

<p align="center">
  여행 사진을 함께 모으고, 내가 나온 사진을 찾고, 마음에 드는 보정본을 함께 고릅니다.
</p>

<p align="center">
  <a href="https://seopseopi.github.io/ZZIK/"><strong>체험 사이트 열기</strong></a>
  &nbsp;|&nbsp; <a href="docs/DEMO_GUIDE.md">사용 가이드</a>
  &nbsp;|&nbsp; <a href="docs/README.md">문서</a>
  &nbsp;|&nbsp; <a href="https://github.com/seopseopi/ZZIK/issues">문의</a>
</p>

<p align="center">
  <a href="https://github.com/seopseopi/ZZIK/actions/workflows/ci.yml"><img src="https://github.com/seopseopi/ZZIK/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI" /></a>
  <img src="https://img.shields.io/badge/React-19-2864ff?logo=react&amp;logoColor=white" alt="React 19" />
  <img src="https://img.shields.io/badge/TypeScript-7-2864ff?logo=typescript&amp;logoColor=white" alt="TypeScript 7" />
  <img src="https://img.shields.io/badge/FastAPI-Python%203.13-2864ff?logo=fastapi&amp;logoColor=white" alt="FastAPI · Python 3.13" />
  <img src="https://img.shields.io/badge/PostgreSQL-17-2864ff?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 17" />
</p>

---

## 소개

찍은 여러 사람이 찍은 여행 사진을 하나의 앨범에서 정리하는 웹 앱입니다. 같은 사진에 나온 사람은 각자의 **내 사진**에서 찾을 수 있고, 밝기와 채도를 바꾼 보정본을 원본과 비교할 수 있습니다. 사진에 나온 멤버가 모두 승인하면 하나의 최종본으로 정해 내려받습니다.

**앨범 만들기 → 멤버 초대 → 사진 업로드 → 인물별 찾기 → 보정본 저장 → 함께 승인 → 최종본 다운로드**

## 화면

![찍 데스크톱 사진 라이브러리](docs/screenshots/desktop.png)

<p align="center">
  <img src="docs/screenshots/mobile-library.png" alt="모바일 내 사진 · 인물 필터" width="290" />
  &nbsp;&nbsp;
  <img src="docs/screenshots/mobile-approval.png" alt="모바일 보정본 비교 · 두 멤버 승인" width="290" />
</p>

현재 앱에서 직접 캡처한 화면입니다. 사진과 인물은 디자인 확인용 샘플이며, 승인 화면은 두 계정 통합 테스트 결과입니다. [캡처와 샘플 안내](docs/screenshots/README.md)

## 주요 기능

| 화면 | 기능 |
| :--- | :--- |
| **앨범** | 생성·초대코드 참여, 이름·소개·시간대 수정, 멤버 관리 |
| **사진 라이브러리** | 여러 파일 업로드, 인물·혼자/함께·태그·날짜 필터, 검색·정렬, 선택 ZIP 다운로드 |
| **내 사진** | 연결된 내 인물이 나온 사진, 여러 인물 AND/OR 조합 |
| **사진 보정** | 밝기·채도 조절, 원본 비교, 이전 보정본에서 새 버전 저장 |
| **함께 고르기** | 등장 멤버 확인, 버전별 승인·취소, 전원 합의 후 최종본 지정 |
| **사진 정보** | 인물 직접 수정, 촬영 정보·위치·태그, 메모·용도, 사진 삭제 |
| **정리 현황** | 대기·진행·완료·실패 장수, 실패 이유·분석 기록·재시도 |
| **협업** | 보정본 댓글·수정 요청, 진행 보드, 앱 내 알림 |

원본은 보존합니다. 승인을 취소하거나 승인 대상이 바뀌면 해당 최종본 지정을 해제합니다. 앨범에 참여한 계정만 사진과 보정본에 접근할 수 있습니다.

## 팀원 체험

**[체험 사이트 열기 →](https://seopseopi.github.io/ZZIK/)**

설치나 로그인 없이 바로 둘러볼 수 있습니다. 상단에서 지수·민지·서연·유진을 바꿔 사진 필터, 보정본 저장, 승인과 최종본 다운로드를 체험하세요. 변경사항은 **각자의 브라우저에만 저장**되며 팀원 사이에 동기화되지 않습니다. 업로드한 사진도 서버로 전송하지 않습니다. 처음 상태로 돌아가려면 상단의 **체험 초기화**를 누르세요.

체험 사이트는 GitHub Pages에서 실행되는 별도 브라우저 모드입니다. 실제 회원가입·초대 전달·얼굴 자동 분석은 실행하지 않습니다. 운영 서버 코드는 이 저장소에 포함되어 있으며 아래 방법으로 별도로 실행합니다. [체험 배포 구조](docs/DEMO_DEPLOYMENT.md)

### 실제 서버로 로컬 실행할 때

로컬 실행 후 **샘플 앨범 둘러보기**를 누르면 지수 계정으로 들어갑니다. 다른 브라우저나 시크릿 창에서 민지로 로그인하면 두 사람의 승인 흐름을 확인할 수 있습니다.

| 샘플 계정 | 이메일 |
| :--- | :--- |
| 지수 | `jisu@moacut.local` |
| 민지 | `minji@moacut.local` |
| 서연 | `seoyeon@moacut.local` |
| 유진 | `yujin@moacut.local` |

샘플 비밀번호는 `MoacutDemo123!`입니다. 기존 데이터와의 호환을 위해 개발용 계정 주소는 유지했습니다. 팀에서 실제로 사용할 때는 회원가입 후 별도 앨범을 만들고 초대코드를 공유하세요. [두 계정으로 시연하기](docs/DEMO_GUIDE.md)

> **자동 분석 범위:** 기본 실행은 지정된 샘플의 파일 해시를 확인하는 fixture 모드입니다. 새 사진의 업로드·보정·수동 인물 지정·승인은 가능하지만 실제 얼굴 자동 분석은 AWS Rekognition 연결이 필요합니다. 샘플 결과를 실제 AI 정확도로 표시하지 않습니다.

## 바로 실행

### macOS

**Node.js 24 이상 · Python 3.13 · PostgreSQL 17**이 필요합니다.

```bash
git clone https://github.com/seopseopi/ZZIK.git
cd ZZIK
brew install postgresql@17  # 미설치 시 한 번
bash scripts/dev.sh
```

**http://127.0.0.1:5173** 에 접속합니다. 의존성 설치, 로컬 DB, 마이그레이션, 샘플 데이터, API·분석 worker·프론트를 함께 준비합니다. 종료해도 로컬 데이터는 남습니다.

### Docker

```bash
git clone https://github.com/seopseopi/ZZIK.git
cd ZZIK
cp .env.example .env
docker compose up --build -d
docker compose exec api python -m app.seed
```

**http://localhost:8080** 에 접속합니다. `docker compose down`은 DB와 사진 볼륨을 보존합니다. Docker 구성의 실행 검증 여부는 [구현 상태](docs/IMPLEMENTATION_STATUS.md)에 기록합니다.

## 개발

React·TypeScript·Vite 프론트, FastAPI API, 별도 분석 worker, PostgreSQL로 구성되어 있습니다. 사진은 기본적으로 로컬 파일에 저장하며 비공개 S3 어댑터도 포함합니다.

```text
ZZIK/
├── frontend/        # React 화면 · Playwright 통합 테스트 · 샘플 이미지
├── backend/         # API · DB 모델 · 분석 worker · 보정 렌더러 · 테스트
├── infra/           # Dockerfile · Nginx
├── scripts/         # 로컬 실행 · 연결 점검 · 재시작 검증
└── docs/            # 사용법 · API · 설계 · 배포 · 검증 기록
```

| 명령 | 역할 |
| :--- | :--- |
| `npm --prefix frontend run build` | TypeScript 검사와 프론트 빌드 |
| `npm --prefix frontend run test:e2e` | 실행 중인 앱에서 두 계정·모바일 통합 검증 |
| `.venv/bin/python -m pytest -q backend/tests` | 백엔드 검사. DB 테스트에는 전용 `TEST_DATABASE_URL` 필요 |
| `.venv/bin/python scripts/check_harness.py` | 역할·작업 의존성·API 계약 검사 |
| `.venv/bin/python scripts/run_integration.py` | 독립 DB·API·worker·web E2E. `ZZIK_E2E_DATABASE_URL` 필요 |
| `.venv/bin/python scripts/check_connections.py` | DB·스키마·저장·샘플 설정 점검 |

로컬 검증: **백엔드 46개, 브라우저 통합 3개 통과**, 프론트 빌드 성공. 브라우저 검증은 실제 업로드 → 보정 → 모바일 승인 → PC 최종본 지정 → 다운로드 → 승인 취소를 포함합니다. [검증 결과와 재현 조건](docs/IMPLEMENTATION_STATUS.md)

`.env`, 비밀키, 로컬 DB, 실제 업로드 파일, 로그인 세션과 로그는 저장소에 포함하지 않습니다. AWS 실연동·정확도·부하 검증은 별도이며, 현재 상태는 문서에 구분해 기록했습니다.

## 팀별 개발

[해커톤 조립 가이드](docs/hackathon/README.md)에 인프라·프론트·백엔드·AI·보정의 **5개 역할 프롬프트와 M01~M17 작업 프롬프트**를 정리했습니다. 역할과 이번 M 작업을 함께 읽고 기능별 PR로 통합합니다. 계약 검사와 실제 서버 E2E를 CI에서 실행하며, AWS 검증과 별도 starter 제작은 후속 단계입니다.

## 문서

| 가이드 | 내용 |
| :--- | :--- |
| [사용 가이드](docs/DEMO_GUIDE.md) | 샘플 계정과 두 사람의 보정·승인 흐름 |
| [개발 환경](docs/DEVELOPMENT.md) | 개별 프로세스 실행·환경변수·테스트 |
| [설계](docs/ARCHITECTURE.md) | 데이터 구조·인물 분석·보정·합의 정책 |
| [API 계약](docs/API_CONTRACT.md) | 인증·앨범·사진·버전·승인 API |
| [체험 사이트 배포](docs/DEMO_DEPLOYMENT.md) | GitHub Pages·브라우저 저장·인물 전환 |
| [실제 서버 배포](docs/AWS_DEPLOYMENT.md) | AWS 구성·HTTPS·운영 설정·롤백 |
| [구현 상태](docs/IMPLEMENTATION_STATUS.md) | 실제 통과한 검증과 남은 조건 |
| [연결 점검](docs/CONNECTIONS.md) | 실제 연결과 샘플 모드의 경계 |
| [자산 안내](docs/ASSETS.md) | 사용자 제공 참고 이미지·샘플 출처 |

오류와 개선 의견은 [Issues](https://github.com/seopseopi/ZZIK/issues)에 남겨 주세요. 공개 이슈에는 비밀번호나 실제 여행 사진 대신 재현 순서와 가상의 예시를 사용해 주세요.
