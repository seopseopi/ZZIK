# 담당 경계와 통합

| 담당 | 직접 책임 | 공유 변경 인계 |
| --- | --- | --- |
| 1 인프라 | infra/, compose.yaml, 배포·복구 절차, CI 실행 환경 | 환경변수/포트/스토리지/IAM을 3번, 브라우저 주소·프록시를 2번과 맞춤 |
| 2 프론트 | App.tsx(통합), features/auth·albums·library·curation, Upload.tsx, People.tsx, api.ts, types.ts, 공통 CSS | 5번 Editor UI를 앱에 연결. 응답 변경은 3번과 계약 확인 |
| 3 백엔드 | main.py(등록·HTTP 정책), routers/auth·albums·people·photos·system, dependencies.py, photo_operations.py, 공유 모델·DB·저장·worker·마이그레이션·seed | 4번 AI 함수와 5번 보정·승인 로직을 API/트랜잭션에 연결 |
| 4 AI | analysis.py, grouping.py, fixture 명세, image_service.py의 메타데이터/품질/유사도 함수 | routers/analysis.py·groups.py 연결은 3번과 통합. 작업 상태·저장은 3번 worker, 인물·태그 화면은 2번에 인계 |
| 5 보정 | Editor.tsx/Editor.css, features/collaboration/Board.tsx, routers/versions.py·collaboration.py, media.py, 렌더링·버전·승인 정책 | 공유 API/model/services는 3번 통합, 공통 화면은 2번 통합 |

`image_service.py`는 아직 물리적으로 나뉘지 않았다. 같은 파일을 동시에 편집하기 전에 담당 함수와 변경 PR을 공유한다. `prepare_image`·`thumbnail_image` 등 공통 전처리 변경은 4/5번이 출력 규칙을 함께 확인한다. AI 모듈이 DB를 직접 쓰는 기존 부분은 3번이 마이그레이션·트랜잭션을 검토한다.

`main.py`의 기능을 9개 라우터와 공통 처리 모듈로, `App.tsx` 내부의 화면 기능을 9개 컴포넌트 파일로 분리했다. 실제 경로는 [모듈 지도](MODULES.md)와 각 M 프롬프트를 따른다. 공유 모델·services·이미지 전처리는 아직 공통 영역이며 독립 패키지/starter 분리까지 완료한 것은 아니다.

## 공통 변경 절차

1. 변경할 요청/응답/오류/상태를 M 이슈·PR에 먼저 명시한다.
2. 공유 파일 통합 담당을 지정한다. 두 PR이 같은 파일을 수정하면 선행 PR부터 합치고 후행 PR을 갱신한다.
3. DB 변경은 3번이 Alembic 부모 revision과 데이터 이전·복구 방법을 결정한다.
4. API 변경은 계약 문서·OpenAPI·프론트 타입·영향받는 검사를 함께 검토한다.
5. 병합 결과에서 계약 검사와 실제 서버 통합 검사를 통과시킨다.

역할 번호는 실제 팀원에게 배정할 자리다. GitHub 사용자명이 없으므로 가짜 계정의 CODEOWNERS나 리뷰 규칙을 만들지 않는다.
