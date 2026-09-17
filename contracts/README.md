# 조립 계약

- `openapi.json`: 현재 FastAPI `/api` 경로·요청 필드·정적 응답 선언의 스냅샷. DB 연결이나 AWS 호출 없이 생성한다.
- `python-interfaces.json`: 3번↔4번↔5번에서 사용하는 Python 함수 이름과 매개변수 순서.
- [응답·상태·권한 규칙](../docs/API_CONTRACT.md): 실제 JSON 응답과 공유 정책.
- [실행 가능한 실제 흐름](../frontend/e2e/desktop.spec.ts): 서로 다른 계정의 업로드→보정→승인→다운로드→승인 취소.

검사: `.venv/bin/python scripts/check_harness.py`.

API를 의도적으로 변경할 때는 소비하는 프론트 타입과 테스트를 먼저 검토하고 `.venv/bin/python scripts/check_harness.py --write-contract`로 갱신한다. 변경 PR에 호환 여부·영향받는 M 작업을 적는다.

현재 API 중 일부는 명시적 response model이 없어 OpenAPI의 응답 스키마가 비어 있다. 따라서 이 스냅샷만으로 프론트와 모든 JSON 응답의 타입 일치가 보장되지는 않는다. 응답 모델 추가와 타입 자동 생성은 후속 구조 정리 작업이며, 그 전에는 응답 계약 문서·프론트 타입·DB/API/E2E 검사를 함께 사용한다.

샘플 모드와 실제 AWS 모드는 같은 서버 API를 사용한다. GitHub Pages의 `frontend/src/demo/`는 브라우저 체험용 별도 구현이며 이 서버 계약의 완료 증거가 아니다.
