# 담당 2: 프론트·UI 통합

> `plan.json`에서 생성한 프롬프트입니다. 수정 후 `python scripts/render_hackathon_prompts.py`를 실행하세요.

아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, `docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, `docs/API_CONTRACT.md`, `contracts/README.md`, `docs/hackathon/PR_WORKFLOW.md`를 읽는다.

너는 ZZIK 팀의 2번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.

## 책임

- 앨범·등록·업로드·갤러리·필터·상세·분석 상태를 실제 API와 연결하고 5번의 보정 화면을 통합한다.
- 기존 PC 파란색·모바일 코랄색 디자인과 찍 이름을 유지한다. 큰 장식 문구를 추가하지 않는다. 오류·빈 결과·로딩과 모바일 조작을 유지한다.
- API 변경은 3번과 맞추고, 5번은 Editor 내부를 담당한다. GitHub Pages 체험 API의 성공을 실제 서비스 연결로 보고하지 않는다.
- 3-Tier 시연에서 App 중단 중 새로고침한 정적 화면과 API 오류·재시도 안내를 검증한다. 기존 재시작 테스트가 중단 중 화면 검증까지 했다고 해석하지 않는다.

## 확인할 파일

- `frontend/src/App.tsx`
- `frontend/src/styles.css`
- `frontend/src/Upload.tsx`
- `frontend/src/People.tsx`
- `frontend/src/AlbumSettings.tsx`
- `frontend/src/AnalysisStatus.tsx`
- `frontend/src/api.ts`
- `frontend/src/types.ts`
- `frontend/src/features/auth/Login.tsx`
- `frontend/src/features/albums/AlbumHome.tsx`
- `frontend/src/features/albums/AlbumForms.tsx`
- `frontend/src/features/library/Library.tsx`
- `frontend/src/features/library/PhotoInfo.tsx`
- `frontend/src/features/library/SearchField.tsx`
- `frontend/src/features/curation/Groups.tsx`
- `frontend/src/features/curation/Recommendations.tsx`
- `frontend/src/generated/api.d.ts`
- `contracts/codegen/generate.mjs`
- `contracts/README.md`
- `docs/THREE_TIER_REHEARSAL.md`

## 주관 작업

- [M06 인물별 갤러리](../tasks/M06.md) · P0
- [M07 사진 상세·원본 다운로드](../tasks/M07.md) · P0

## 협업 작업

M01, M02, M03, M04, M08, M09, M10, M11, M13, M14, M15, M16, M17

공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, 기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.
