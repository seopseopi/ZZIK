# 담당 4: Vision AI·인물·추천

> `plan.json`에서 생성한 프롬프트입니다. 수정 후 `python scripts/render_hackathon_prompts.py`를 실행하세요.

아래 지시를 작업 프롬프트로 사용한다. 먼저 저장소의 `AGENTS.md`, `docs/hackathon/COMMON.md`, `docs/hackathon/OWNERSHIP.md`, `docs/API_CONTRACT.md`, `contracts/README.md`, `docs/hackathon/PR_WORKFLOW.md`를 읽는다.

너는 ZZIK 팀의 4번 담당이다. 아래 역할 범위에서 현재 코드를 먼저 검토하고, 지정된 M 작업을 하나씩 진행한다. 모든 M을 한 번에 다시 구현하지 않는다.

## 책임

- 기준 얼굴 검사, 모든 얼굴의 매칭, 장면 태그, EXIF/GPS, 품질·유사 그룹·추천 결과를 구조화하여 3번에 전달한다.
- 미확정·얼굴 없음·오류를 구분하고 실제 AWS 실패를 fixture 성공으로 대체하지 않는다. 그룹은 앨범 범위로 격리한다.
- image_service.py의 메타데이터/품질 영역을 맡는다. 렌더링 영역을 변경할 때 5번과 계약을 먼저 맞춘다. 정확도·속도·비용은 실사진 측정 결과로만 기록한다.
- 3-Tier 리허설에서 분석 중 worker 중단·lease 만료·재시도 후 상태 복구를 검증한다. 무한 처리 중 상태와 중복 반영, 수동 수정 유실을 확인하고 실사진 정확도 검증과 구분한다.

## 확인할 파일

- `backend/app/analysis.py`
- `backend/app/grouping.py`
- `backend/app/image_service.py`
- `backend/fixtures/manifest.json`
- `backend/tests/test_analysis_worker.py`
- `backend/app/routers/analysis.py`
- `backend/app/routers/groups.py`
- `docs/AWS_EDU_VALIDATION.md`
- `docs/THREE_TIER_REHEARSAL.md`

## 주관 작업

- [M03 기준 인물 등록](../tasks/M03.md) · P0
- [M05 다중 얼굴 분석·분류](../tasks/M05.md) · P0
- [M13 장면·촬영일·장소](../tasks/M13.md) · P1
- [M14 유사 그룹·Best Shot](../tasks/M14.md) · P1
- [M15 등록 없는 얼굴 그룹](../tasks/M15.md) · P3
- [M16 한국어 사진 검색](../tasks/M16.md) · P3

## 협업 작업

M01, M06, M08

공유 파일의 통합 담당은 `OWNERSHIP.md`가 우선이다. 작업 프롬프트의 파일 목록이 독점 수정 권한을 뜻하지 않는다. 필요한 계약 변경을 의존 PR로 명시하고, 기능·검사 결과·미검증 조건을 다음 담당에게 전달한다.
