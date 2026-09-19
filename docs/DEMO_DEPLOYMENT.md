# 팀원 공유용 체험 사이트

- GitHub: https://github.com/seopseopi/ZZIK
- 체험 주소: https://seopseopi.github.io/ZZIK/

팀원이 프론트와 사용 흐름을 확인하는 용도다. Python·DB·AWS 서버가 배포된 서비스가 아니며, 체험 데이터를 다른 사람과 공유하지 않는다.

## 체험할 수 있는 것

샘플 앨범과 인물 필터, 사진 업로드·선택, 밝기·채도 보정, 버전 저장·비교, 인물 전환·승인·취소·최종본 지정, 사진·ZIP 다운로드, 메모·댓글, 앨범 관리와 초기화를 제공한다. 상단의 인물 선택은 실제 로그인이나 다른 사람의 승인 획득이 아니라 한 브라우저에서 협업 화면을 시연하는 기능이다.

상단 **체험 · 이 브라우저에만 저장**을 누르면 안내를 볼 수 있다. 변경사항과 업로드 파일은 IndexedDB의 `zzik-browser-demo-v1`에 저장한다. 비밀번호는 저장하지 않는다. 새로고침해도 같은 브라우저에서 유지되며, 브라우저 데이터 삭제·체험 초기화 시 사라진다. 업로드는 JPEG/PNG, 파일당 8MB·1,600만 화소 이하로 제한한다.

얼굴 자동 분석·추천·자동 그룹은 실제 서비스에 요청하지 않는다. 새 사진의 분석 상태는 확인 필요로 표시하고 인물을 직접 지정하게 한다. 보정은 브라우저 픽셀 연산으로 계산하므로 Pillow 서버 결과와 픽셀 단위로 동일하다고 보증하지 않는다. 기본 샘플 파일은 공개 정적 자산이다. [자산 안내](ASSETS.md)

## 로컬 확인

왼쪽 메뉴의 **휴지통**에서 현재 앨범의 버린 사진을 확인하고 크게 볼 수 있다. 사진 정보의 **휴지통으로 이동**은 원본과 보정 기록을 보관하며, 사진을 올린 인물 또는 앨범 소유자가 **복원**할 수 있다. 휴지통 상태도 같은 브라우저에 저장되며 새로고침 후 유지된다. 모바일에서는 하단 메뉴로 휴지통을 연다.

```bash
npm --prefix frontend ci
npm --prefix frontend run dev:demo
# http://127.0.0.1:5174
```

GitHub Pages와 동일한 경로에서 빌드·검사:

```bash
npm --prefix frontend run build:demo -- --base=/ZZIK/
npm --prefix frontend run test:demo
```

`frontend/src/demo/`는 `mode=demo` 빌드에서만 API를 대체한다. 일반 `npm run dev`·`npm run build`는 기존 FastAPI `/api` 연결을 사용한다. 개발 중 체험 주소와 서버 주소는 서로 다른 포트를 사용해 저장 상태를 분리한다.

## 배포

GitHub Pages의 Source는 **GitHub Actions**다. `.github/workflows/ci.yml`은 `main` push 시 다음을 실행한다.

1. 전용 PostgreSQL에서 백엔드 테스트.
2. 실제 서버용 프론트 빌드, 체험 빌드, 브라우저 체험 테스트.
3. 검증을 통과한 정적 파일만 Pages에 배포.

[GitHub Actions](https://github.com/seopseopi/ZZIK/actions/workflows/ci.yml)에서 성공 여부와 배포 URL을 확인한다. 이전 상태로 되돌리려면 해당 변경을 `git revert`한 뒤 `main`에 push한다. 로컬 `.env`, DB·사진 폴더, 로그인 세션, 로그를 배포하지 않는다.

GitHub 공식 문서: [사용자 정의 Pages 워크플로](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
