# 담당 5: 보정·버전·승인

> `plan.json`에서 생성한 프롬프트입니다. 수정 후 `python scripts/render_hackathon_prompts.py`를 실행하세요.

아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, `docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, `docs/API_CONTRACT.md`, `contracts/README.md`, `docs/hackathon/PR_WORKFLOW.md`를 읽는다.

너는 ZZIK 팀의 5번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.

## 책임

- 원본 기반 밝기·채도·비교·이력·다운로드와 버전별 승인·취소·최종본 흐름을 담당한다.
- 서버/model 변경은 3번과, 공통 화면/API 타입은 2번과 통합한다. 화면에 Git 용어 대신 새 보정본·이전 버전·확인 요청을 쓴다.
- 확인된 등장 멤버 전원 승인 규칙과 승인 대상 스냅샷을 유지한다. contrast/crop/warm filter 예시는 현재 미구현이며 별도 범위 확정 없이 완료로 표시하지 않는다.
- 3-Tier App 장애·복구 전후 원본/보정본 해시·버전 설정·전원 승인·최종본 보존을 1/3번과 검증한다.

## 확인할 파일

- `frontend/src/Editor.tsx`
- `frontend/src/Editor.css`
- `backend/app/image_service.py`
- `backend/tests/test_image_rendering.py`
- `backend/app/routers/versions.py`
- `backend/app/routers/collaboration.py`
- `backend/app/media.py`
- `frontend/src/features/collaboration/Board.tsx`
- `docs/THREE_TIER_REHEARSAL.md`

## 주관 작업

- [M09 기본 보정·버전 저장](../tasks/M09.md) · P2
- [M10 버전 이력·비교](../tasks/M10.md) · P2
- [M11 승인·최종본](../tasks/M11.md) · P2
- [M12 보정 이미지 내보내기](../tasks/M12.md) · P2
- [M17 분기·라벨·댓글·보드·알림](../tasks/M17.md) · P3

## 협업 작업

M01, M08

공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, 기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.
