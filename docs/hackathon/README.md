# 찍 · 팀별 구현과 조립

팀원은 **자기 역할 프롬프트 + 이번에 구현할 M 작업 프롬프트**를 함께 사용한다. 공통 계약을 유지하며 기능별 PR을 합치고, 실제 API·worker·DB를 실행하는 통합 검사로 확인한다.

## 지금 진행하는 단계

1. **1단계:** 공통 규칙, 5개 역할·17개 작업 프롬프트, 계약 검사, 독립된 통합 테스트 실행기와 CI.
2. **이번 2단계:** API 9개 라우터·화면 9개 컴포넌트 파일 분리. 독립 실행기의 API/worker 재시작 검사와 GitHub의 Compose 전체 실행·컨테이너 재시작 검사 추가.
3. **서비스 검증:** 실제 S3·Rekognition·AWS 배포, 실사진·여러 기기·복원·처리량 확인.
4. **대회 조립판:** 검증된 기준본을 보존하고 별도 starter를 제작. 팀원이 작업별로 다시 구현·통합하여 같은 검사를 통과하는지 리허설.

현재는 **기존 서비스를 기능별로 나누고 조립·재시작 검사를 연결한 단계**다. 기능 구현을 비워 둔 starter나 AWS 운영 완료본은 아직 아니다. GitHub Pages는 프론트 체험판이다.

## 읽는 순서

1. [팀원 원문](source/TEAM_SPEC.md)과 [범위·판단](SCOPE.md)
2. [공통 프롬프트](COMMON.md)와 [담당 경계](OWNERSHIP.md)
3. 아래 역할과 작업 프롬프트
4. [모듈 지도](MODULES.md)와 [조립·검증 방법](ASSEMBLY.md)

## 5명 역할

| 담당 | 역할 프롬프트 | 주관 작업 |
| --- | --- | --- |
| 1 | [AWS 인프라·배포](roles/01-infra.md) | M01 |
| 2 | [프론트·UI 통합](roles/02-frontend.md) | M06, M07 |
| 3 | [백엔드·DB·통합](roles/03-backend.md) | M02, M04, M08 |
| 4 | [Vision AI](roles/04-vision.md) | M03, M05, M13~M16 |
| 5 | [보정·버전·승인](roles/05-editing.md) | M09~M12, M17 |

주관은 완료 책임이다. UI는 2번, 공유 API·DB는 3번이 통합하므로 다른 주관 작업에도 협업한다. 팀원 GitHub 계정 배정과 CODEOWNERS는 아직 설정하지 않았다.

## 작업 순서

| 우선순위 | 작업 |
| --- | --- |
| P0 기본 흐름 | [M01 인프라](tasks/M01.md) → [M02 앨범](tasks/M02.md) → [M03 기준 인물](tasks/M03.md) → [M04 업로드](tasks/M04.md) → [M05 분석](tasks/M05.md) → [M06 갤러리](tasks/M06.md) → [M07 상세](tasks/M07.md) → [M08 수정](tasks/M08.md) |
| P1 추천 | [M13 장면·위치](tasks/M13.md) → [M14 Best Shot](tasks/M14.md) |
| P2 보정·승인 | [M09 보정](tasks/M09.md) → [M10 이력](tasks/M10.md) → [M11 승인](tasks/M11.md) → [M12 내보내기](tasks/M12.md) |
| P3 확장 | [M15 얼굴 그룹](tasks/M15.md), [M16 검색](tasks/M16.md), [M17 협업](tasks/M17.md) |

번호는 원문을 보존했다. 우선순위대로 M08 이후 M13/14를 먼저 확인하고, 5번은 M09~12를 병행할 수 있다. 정확한 선행 작업은 각 프롬프트와 [plan.json](plan.json)에 있다. M01의 로컬 실행으로 개발을 시작할 수 있지만 P0 완료에는 실제 AWS 검증이 필요하다.

## 프롬프트 유지 관리

`plan.json`이 역할·작업의 원본이다. 내용을 수정한 뒤 실행한다.

```bash
python3 scripts/render_hackathon_prompts.py
.venv/bin/python scripts/check_harness.py
```

계약 검사에서는 작업 의존성·참조 파일·프롬프트 일치·실제 API 구현 파일 대응·중복 경로·API 경로/요청 스키마·Python 매개변수 이름을 확인한다. 실제 응답의 의미와 AWS 연결 품질은 통합 테스트와 실환경 검증이 별도로 필요하다.
