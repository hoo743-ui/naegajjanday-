# 43. 사진 데이터 전략 — 무료 비용 기준

> 2026-09-24. docs/39(실제 사진 → 예시 사진 → 브랜드 그림)를 이어받아 **데이터 모델 · 출처 저장 · 무료 이미지 API · 표시 규칙**을 한 벌로 정한다.
> 목표는 "실제 사진 100%"가 아니라 **사진이 없어도 빈약해 보이지 않고, 실제 사진이 아닌 것을 실제처럼 보이게 하지 않는 것**.

## 1. 우선순위 (카드 하나 = 그림 한 장)

| 순서 | image_type | 무엇 | 대상 | 비용 |
|---|---|---|---|---|
| 1 | `actual` | 그 장소의 사진 — 한국관광공사 TourAPI · 운영자 업로드 | 관광지 · 공원 · 축제 · 전시 · 문화공간 (TourAPI 에 있는 곳) | 무료 (공공데이터포털 키) |
| 2 | `category` | 같은 종류의 **분위기 이미지** — Wikimedia Commons · Openverse · Pexels · Unsplash | 식당 · 카페 · 놀거리 · 술집 (TourAPI 에 없는 곳 대부분) | 무료 (Pexels · Unsplash 는 무료 키) |
| 3 | `branded-placeholder` | 내가짠데이 그림 — 식사 · 카페 · 산책 · 놀거리는 장면이 다르다 | 위 둘 다 없을 때 · 사진 주소가 깨졌을 때 | 0 |

순서는 서버가 정한다(`app/domain/image_ref.py › resolve_image`). 웹은 받은 `image` 를 그대로 그린다(`components/brand/PlacePhoto.tsx`). 서버가 `image` 를 주지 않는 곳(목 데이터 · 이벤트 띠)만 웹이 같은 순서로 고른다(`lib/place-image.ts`).

**2026-09-24 실제 DB**: TourAPI 사진 26,530장. 공공누리 **제3유형(출처표시 · 변경금지) 19,169장** · 제1유형(출처표시) 7,360장 · 유형 칸 없음 1장.

## 2. 이미지 데이터 모델

API 응답의 `image` (코스 장소 `PlaceBrief` · 둘러보기 `AttractionItem` · 인기 장소 `HotPlace`). 요청하신 이름과 대응:

| 요청 | API 필드 (snake_case) | 비고 |
|---|---|---|
| imageUrl | `image_url` | placeholder 면 null |
| thumbnailUrl | `thumbnail_url` | 따로 없으면 image_url |
| source | `source` | `tourapi · upload · wikimedia · openverse · pexels · unsplash · naegajjanday` |
| sourceUrl | `source_url` | 원본 페이지 (작가 · 라이선스 확인) |
| photographer | `photographer` | TourAPI 는 "한국관광공사" |
| license | `license` | "공공누리 제3유형 (출처표시·변경금지)", "CC BY-SA 2.0", "Pexels License" … |
| attributionText | `attribution_text` | 화면에 그대로 적는 한 줄. 분위기 이미지는 "분위기 이미지 · © 작가 · 라이선스 · 출처" |
| isActualPlacePhoto | `is_actual_place_photo` | |
| isFallbackImage | `is_fallback_image` | category · placeholder 는 true |
| imageType | `image_type` | `actual · category · branded-placeholder` |
| (추가) | `placeholder_kind` | `meal · cafe · walk · activity · sight · bar · night` — 그림 종류. 사진이 깨질 때도 쓴다 |

**저장 위치**
- 실제 사진: `place_image` 테이블에 사진마다 `thumbnail_url · source_url · photographer · license · attribution_text` (0009, 기존의 source · 검증 상태 · 같은 사진 키는 그대로). 라이선스가 **사진마다 다르기** 때문에(1유형/3유형) 장소가 아니라 사진에 둔다. 채우기: `uv run python -m app.cli images-credit [--apply]` (원본 캐시의 `cpyrhtDivCd` · `firstimage2`).
- 분위기 이미지: `data/media/category_images.json` — 업종 코드마다 한 장, 같은 필드 (`url · thumbnail_url · page_url · author · license · source · attribution_text`). 예전 Wikimedia 항목은 읽을 때 채운다.

## 3. 분위기 이미지 모으기 (사람이 고른다)

```
# 후보 모으기: Openverse 는 키 없이, Pexels · Unsplash 는 키가 있을 때만
uv run python scripts/curate_mood_images.py search [--only food.korean] [--per 4]
#   → data/media/mood_candidates.json + mood_candidates.review.html 을 열어 전부 눈으로 본다
# 고른 것만 반영
uv run python scripts/curate_mood_images.py apply --pick food.korean=pexels:<id>
```

- 키: `PEXELS_API_KEY` · `UNSPLASH_ACCESS_KEY` (`apps/api/.env`). **둘 다 아직 없다** — 무료 발급(Pexels: pexels.com/api, Unsplash: unsplash.com/developers).
- **서비스 도중에 API 를 부르지 않는다.** 한 번 골라 파일에 적어 두고, 화면은 그 주소를 쓴다. 무료 한도(시간당 50~200회)에 걸릴 일이 없고, 검색 결과가 멋대로 바뀌지 않는다.
- 자동으로 고르지 않는다: "bibimbap" 검색 결과가 **어느 가게의 간판 사진**일 수 있다. 간판 · 로고 · 읽히는 메뉴판 · 알아볼 수 있는 사람이 있는 사진은 고르지 않는다.
- 라이선스: 상업적 이용 + 변경(자르기 · 톤 조정) 허용만. Openverse 는 `license_type=commercial,modification` 으로 찾고 NC · ND 는 한 번 더 거른다. Pexels · Unsplash 는 각자 라이선스(무료 · 상업 가능).
- Unsplash 규칙: 사진은 Unsplash 주소 그대로(hotlink), 작가 링크에 `utm_source` 표기, 쓰기로 정할 때 `download_location` 호출 — `apply` 가 한다.

## 4. 화면 규칙 (`PlacePhoto`)

| image_type | 작은 칸 (코스 카드 72~80px) | 큰 칸 (둘러보기 카드 · 상세 시트) |
|---|---|---|
| actual | 보통 사진. 손대지 않는다(3유형 = 변경금지). 출처는 "자세히"를 열면 한 줄 | 보통 사진 + 오른쪽 아래 "사진 ⓒ한국관광공사" |
| category | 아래 띠 **"분위기 이미지"**, 조금 가라앉힌 톤, 툴팁에 작가 · 라이선스 | 왼쪽 아래 "분위기 이미지" + 오른쪽 아래 작가 · 라이선스 · 출처(원본 링크) |
| branded-placeholder | 종류별 장면 (식사: 그릇 · 젓가락 / 카페: 김 나는 잔 · 원두 / 산책: 굽은 길 · 나무 / 놀거리: 입장권 · 색종이). 볼거리 · 한잔 · 야경은 아이콘 | 같은 장면 + 종류 이름 |

- 사진을 못 받으면 빈 상자 대신 그 종류의 그림으로 내려간다.
- 바꾸기 후보 목록은 분위기 이미지를 쓰지 않는다 — 같은 업종 후보들이 같은 사진이 되어 고르기 어렵다. 실제 사진이 없으면 그림.
- `NEXT_PUBLIC_EXAMPLE_PHOTOS=off` 면 분위기 이미지를 끄고 그림으로 간다.
- 이번에 고친 결함: 둘러보기 상세 시트가 분위기 이미지를 **아무 표시 없이** 보여 주고 있었다(카드에서 넘긴 주소만 받아서). 이제 같은 `image` 를 받아 같은 표시를 한다.

## 5. 하지 않는 것
- 외부 사이트 무단 크롤링, 네이버 플레이스 · 인스타그램 · 블로그 이미지 저장(약관 · 저작권).
- 좌표 근처 아무 사진이나 붙이기(docs/29 에서 거부됨).
- 분위기 이미지를 그 가게 사진처럼 보이게 하기 — 표시 없이, 원본 톤 그대로, 상세 화면의 "이 장소 사진"으로.
- Google Places 사진 — 유료 · 캐시 금지. 붙인다면 창업자 결정 뒤 1단계에 "사진 · Google" 표기로(docs/39).

## 6. 남은 것
- Pexels · Unsplash 키 발급 → `search` → 검수 → `apply`. 특히 지금 Wikimedia 사진이 약한 코드(카페 · 디저트 · 놀거리 하위)부터.
- 코스 카드의 실제 사진은 아직 큰 원본(940px)을 받는다. `place_image.thumbnail_url` 에 작은 크기가 채워졌으니(약 2.5만 장), 장소 투영(`place.thumbnail_url`)에 작은 크기를 함께 싣는 것은 다음 단계.
- 공공누리 3유형 사진을 카드 비율로 **잘라 보여 주는 것**이 '변경'에 해당하는지는 공공누리 안내를 확인할 것. 걱정되면 3유형은 `object-contain` 으로 바꾼다.
- 운영자 업로드 사진에는 아직 라이선스 칸을 채우지 않는다(업로드 화면에 "권리 확인" 입력이 생길 때).
