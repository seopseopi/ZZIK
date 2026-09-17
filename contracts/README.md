# 조립 계약

- `openapi.json`: `/api` 51개 동작의 요청과 응답 스냅샷. JSON 성공 45개는 `backend/app/responses.py` 모델로 검증하며 파일 6개는 이미지/ZIP MIME과 필요한 S3 307 응답을 명시한다.
- `frontend/src/generated/api.d.ts`: OpenAPI에서 생성하는 요청·응답·경로 TypeScript 타입. `frontend/src/types.ts`는 화면이 사용하는 이름을 이 타입에 연결한다.
- `python-interfaces.json`: 분석·저장·worker 등 Python 함수 매개변수 변경 검사.
- [응답·상태·권한 규칙](../docs/API_CONTRACT.md), [실제 흐름 검사](../frontend/e2e/desktop.spec.ts).

## 규격을 변경할 때

3번이 서버 모델과 라우터를 변경하고 2번이 소비 화면과 데모 데이터를 함께 맞춘다. 생성 파일만 수정하지 않는다.

```sh
# 최초 한 번: 타입 생성 도구 설치 (런타임 의존성 아님)
npm --prefix contracts/codegen ci

# API 변경과 소비자 영향을 검토한 뒤 스냅샷·타입 갱신
.venv/bin/python scripts/check_harness.py --write-contract
npm --prefix frontend run types:generate

# 일반 검사: 오래된 스냅샷·생성 타입이면 실패
.venv/bin/python scripts/check_harness.py
npm --prefix frontend run types:check
npm --prefix frontend run build
```

`openapi-typescript` 7.13.0의 TypeScript 5 peer 요구를 별도 `contracts/codegen` 패키지에 격리했다. 프론트 TypeScript 7과 런타임 의존성은 유지한다. CI는 백엔드에서 OpenAPI 일치·응답 선언을, 프론트에서 생성 타입 일치와 빌드를 검사한다. [생성 도구](https://openapi-ts.dev/introduction).

## nullable·상세 응답

- 값이 없음을 뜻하는 `user_id`, `cover_url`, `captured_at`, `parent_id`, `final_version_id` 등은 필드가 존재하고 값이 `null`이다. `?`로 누락 가능성을 표현하는 것과 구분한다.
- `PhotoResponse`는 목록/업로드 응답이고 `PhotoDetailResponse`는 `faces`·`versions`가 반드시 있는 상세 응답이다. 추천 사진에는 `faces`가 있고 상세 버전 목록은 없다.
- 작성자/댓글 작성자는 `{id,name}`이고 로그인 사용자/앨범 멤버의 `email`을 요구하지 않는다.
- `PersonResponse.source`는 사진-인물 연결에만 포함될 수 있다. `response_model_exclude_unset=True`로 기본값 필드를 새로 끼워 넣지 않는다. 날짜는 기존 ISO 문자열 표현을 유지한다.
- `analysis_metadata`, `quality`, 얼굴 상세는 공급자·처리 단계에 따라 키가 달라지는 JSON 확장 영역이다. 생성 타입의 동적 값은 `unknown`이며 소비할 때 좁혀 사용한다.
- JSON 응답 모델은 예상 밖 최상위 필드를 거부한다. 응답 검증 오류는 내부 값·세션 토큰을 기록하지 않고 일반 500 오류로 처리한다. [FastAPI 응답 모델](https://fastapi.tiangolo.com/tutorial/response-model/).

## 검사 범위

정적 타입은 HTTP에서 받아온 JSON을 브라우저에서 런타임 검증하는 기능이 아니다. 현재 `api<T>` 호출자가 선택한 타입과 URL의 대응까지 자동 추론하는 SDK도 아니다. 서버 응답 모델, 요청별 OpenAPI 선언, 타입 생성 일치, UI 컴파일과 실제 API/DB/E2E 검사를 함께 사용한다. 오류는 `{code,message,details?}`로 문서화하지만 `JSONResponse` 예외 처리기는 응답 모델의 자동 검증 경로를 지나지 않으므로 별도 테스트한다.

체험판의 IndexedDB 자료는 기존 사진·앨범을 유지하면서 새 nullable 필드 기본값을 보충한다. 체험판은 실제 AWS·원격 협업의 검증을 대신하지 않는다. 의미·권한·승인 상태의 정확성도 스키마만으로 증명하지 않는다.
