# 합성 AWS 연결 검증 사진

2026-09-17 내장 `imagegen`으로 생성한 가상 성인 사진과 풍경이다. 실제 사용자 사진이나 신원 자료가 아니다. `manifest.json`의 기대값은 생성 의도와 눈으로 확인한 구성을 기록했다. 테스트 대상 사진은 기준 사진을 그대로 재사용하지 않는다.

| 파일 | 용도 | 기대값 |
|---|---|---|
| `reference-a.png` | 가상 인물 A의 기준 사진 | 얼굴 1개 |
| `travel-pair.png` | A와 등록하지 않은 다른 가상 인물 | 얼굴 2개, 등록 인물 A만 일치 |
| `no-faces.png` | 인물 없는 바다 | 얼굴 0개 |

콘솔에서 기준 사진의 얼굴 검출과 여행 사진의 비교를 확인했다. 풍경 사진 분석 및 앱 역할의 SDK 전체 실행은 아직 검증하지 않았다. 이 세트는 연결 smoke test용이며 실제 여행 사진의 정확도 평가나 모델 학습용 데이터셋이 아니다. `fixture` 제공자의 성공 해시 목록에 추가하지 않았다.

실행 명령과 결과 해석: [AWS_EDU_VALIDATION.md](../../../docs/AWS_EDU_VALIDATION.md).

## 생성 프롬프트

사용 도구: 내장 `image_gen.imagegen`. CLI/API 키 방식은 사용하지 않았다. PNG 원본을 수정하지 않고 복사했다.

### reference-a.png

```text
Use case: photorealistic-natural. Asset: synthetic reference portrait for a travel-photo application's face matching integration test. Generate a single natural realistic chest-up portrait of one entirely fictional Korean adult woman, age 28, short straight black bob hair, oval face, warm brown eyes, a small mole below her left eye, wearing a plain navy cotton shirt. She faces the camera directly with eyes open and neutral relaxed expression, evenly lit by soft daylight. Plain light gray background. Only one person, no other faces, no posters, no mirrors, no lettering, no watermark, no collage. Face occupies about 40 percent of image width with complete forehead and chin visible. Natural skin detail, ordinary candid phone-camera photo, square composition.
```

### travel-pair.png

참조 이미지: `reference-a.png`.

```text
Use case: identity-preserve. Asset: synthetic travel photo for face matching integration test. Use the supplied portrait as the identity reference for the woman only: preserve her facial structure, eyes, nose, short straight black bob, skin tone, and mole below her left eye. Make a NEW realistic travel photograph at a sunny seaside promenade showing exactly TWO fictional adults from waist up. The reference woman stands on the left in a cream cardigan, facing nearly directly toward camera, smiling gently. On the right stands a different fictional adult man age 32 with short curly dark hair, brown eyes, lightly tanned skin, broad jaw and subtle beard, blue casual shirt, also facing camera with eyes open. Faces fully visible and separated, each at least 200 pixels wide. Natural morning light, quiet blue sea and railing behind, no other people, no posters, no reflections, no text, no watermark, no collage. Ordinary authentic phone travel photo. Keep the woman's identity as close as possible to the reference but change composition, expression, lighting, outfit and background.
```

### no-faces.png

```text
Use case: photorealistic-natural. Asset: synthetic negative test image for a travel-photo face detection integration check. Generate one realistic landscape photo of a deserted sandy beach with gentle turquoise surf, rocky coastline, clear pale blue sky, warm morning sunlight. Absolutely NO people, NO faces, NO animals, NO figures, NO statues, NO text, NO watermark, NO collage. Ordinary travel phone photo with natural detail, square composition.
```
