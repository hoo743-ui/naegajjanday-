"""Redesign v2 step 1a (docs/25): the stop card and the map speak one language.
A real photo is shown large, a stand-in photo small; the price is the loudest thing in the card; the
tools fit one quiet line; numbers and pins are ink, the chosen one blue, the route a single blue.
Every control keeps its accessible name (the screen contract and the E2E selectors depend on them)."""
import io
import os

DRY = os.environ.get("DRY") == "1"  # anchors are asserted, nothing is written. Never run during an audit.
ROOT = r"C:\Users\LG\OneDrive\바탕 화면\링커스\내가짠데이\apps\web\src"
PENDING = {}  # path → text: a file edited twice is read back from here, so a dry run sees what a real run would


def put(path, text):
    """The only place this script writes."""
    PENDING[path] = text
    if DRY:
        return
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def get(path):
    return PENDING[path] if path in PENDING else io.open(path, encoding="utf-8").read()


def edit(rel, pairs):
    p = os.path.join(ROOT, rel)
    s = get(p)
    for a, b in pairs:
        assert a in s, (rel, a[:70])
        s = s.replace(a, b, 1)
    put(p, s)


def between(rel, start, end, new):
    p = os.path.join(ROOT, rel)
    s = get(p)
    i, j = s.index(start), s.index(end)
    assert 0 <= i < j, rel
    put(p, s[:i] + new + s[j:])


# ── colours: ink numbers, one blue route ───────────────────────────────────────────────────────
put(
    os.path.join(ROOT, "components/course/colors.ts"),
    "/**\n"
    " * 지도와 타임라인의 색 (docs/25): 순번은 잉크, 고른 것만 파랑, 경로는 파랑 한 가지.\n"
    " * 예전에는 순번마다 파랑 → 보라 → 분홍으로 달랐다 — 종이 톤의 화면에서 지도만 따로 놀았다.\n"
    " */\n"
    "export const PIN_INK = \"#10192E\";\n"
    "export const ROUTE_BLUE = \"#2A5BD7\";\n\n"
    "/** i번째 스톱의 번호 색. 모든 순번이 같은 잉크다(인자는 호출부를 그대로 두려고 남겼다) */\n"
    "export function stopColor(_index?: number, _count?: number): string {\n  return PIN_INK;\n}\n\n"
    "/** 구간(경로선 · 이동 시간 칩)의 색 */\n"
    "export function routeColor(): string {\n  return ROUTE_BLUE;\n}\n"
)
for rel in ("components/course/KakaoRouteMap.tsx", "components/course/LeafletRouteMap.tsx"):
    edit(rel, [
        ("import { stopColor } from \"./colors\";", "import { routeColor, stopColor } from \"./colors\";"),
        ("      const color = stopColor(i + 1, stops.length); // 도착 스톱의 색\n", "      const color = routeColor();\n"),
    ])
edit("components/course/KakaoRouteMap.tsx", [
    ("legChipHtml(legs[i]!.label, stopColor(i + 1, stops.length), layout.chip.angle)", "legChipHtml(legs[i]!.label, routeColor(), layout.chip.angle)"),
])
edit("app/globals.css", [
    (".jj-pin.is-active {\n  --size: 58px;\n}\n",
     ".jj-pin.is-active {\n  --size: 58px;\n  --pin: var(--blue-deep) !important; /* 고른 핀만 파랑. 나머지는 잉크 */\n}\n"),
])

# ── the card ───────────────────────────────────────────────────────────────────────────────────
NEW = '''      {/* 그 가게의 실제 사진이면 크게 보여 준다: "실제로 있는 곳"이라는 믿음이 여기서 생긴다.
          업종 예시 사진은 아래 줄의 작은 썸네일로만 쓴다(같은 라떼 사진이 코스마다 화면을 덮지 않게). */}
      {place.thumbnail_url ? (
        <div className="photo-edge relative -mx-4 -mt-4 mb-4 aspect-[16/9] overflow-hidden sm:-mx-5 sm:-mt-5">
          <Image src={place.thumbnail_url} alt="" fill sizes="(max-width: 1024px) 100vw, 520px" className="object-cover" unoptimized={!canOptimize(place.thumbnail_url)} />
          <span aria-hidden className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-black/40 to-transparent" />
          {credit ? <span className="absolute right-2.5 bottom-2 rounded-md bg-black/45 px-1.5 py-0.5 text-[10.5px] font-medium text-white/95">{credit}</span> : null}
        </div>
      ) : null}

      <div className="flex items-start gap-3.5">
        <span aria-hidden className={cn("tabular mt-0.5 grid size-8 shrink-0 place-items-center rounded-full text-sm font-extrabold text-white transition-colors duration-300", active ? "bg-blue-deep" : "bg-ink")}>
          {stop.position}
        </span>

        <div className="min-w-0 flex-1">
          <p className="tabular flex flex-wrap items-center gap-x-2 text-xs font-extrabold text-blue-deep">
            <span>{roleLabel(stop.role)}</span>
            <span className="inline-flex items-center gap-1 text-muted-foreground">
              <Clock aria-hidden className="size-3" />
              {clock(stop.arrive_at)} – {clock(stop.leave_at)}
            </span>
          </p>
          <h3 className="truncate text-[17px] font-extrabold tracking-tight sm:text-lg">
            {/* 이름을 누르면 우리가 가진 그 가게의 정보(조사된 메뉴 가격 · 사진 · 영업시간 · 개업 연도)를 연다 */}
            {stop.place.kind === "event" ? (
              place.name
            ) : (
              <button type="button" onClick={() => { setSheet(true); track("place_sheet_opened", { course_id: courseId, position: stop.position }); }} className="max-w-full truncate text-left underline decoration-line decoration-2 underline-offset-4 hover:decoration-blue-deep">
                {place.name}
              </button>
            )}
          </h3>
          <p className="truncate text-[13px] text-muted-foreground">
            {place.category_name ?? place.category}
            {place.address ? ` · ${place.address}` : ""}
          </p>
        </div>

        {/* 금액: 카드에서 가장 큰 글자 */}
        <p className="tabular shrink-0 text-right text-xl leading-tight font-extrabold tracking-tight">
          {priceUnknown ? (
            <span className="text-[13px] font-bold text-muted-foreground">가격 정보 없음</span>
          ) : (
            <>
              {free ? "0원" : won(stop.est_price)}
              <small className="mt-0.5 block text-[11.5px] font-bold tracking-normal text-muted-foreground">
                {free ? "무료" : partySize > 1 ? (place.price_per_person !== null ? `1인 ${won(place.price_per_person)}` : `${partySize}명 합계`) : "1인"}
              </small>
              {!free && place.price_is_estimated ? (
                <span className="mt-1 inline-block rounded-md bg-gold-soft px-1.5 py-0.5 text-[11px] font-bold tracking-normal text-gold-ink" title="이 가게의 메뉴판 가격이 아니라, 같은 지역·같은 업종의 1인 평균가로 계산한 금액이에요">
                  평균가
                </span>
              ) : null}
            </>
          )}
        </p>
      </div>

      {place.rating !== null || stop.congestion || place.tags.length > 0 || (!place.thumbnail_url && example) ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-xs font-bold">
          {!place.thumbnail_url && example ? (
            // 그 가게의 실제 사진이 아니라 업종 대표 이미지임을 밝히고, 오픈 라이선스 조건대로 출처를 단다
            <a
              href={example.page_url ?? example.url}
              target="_blank"
              rel="noreferrer"
              title="이 가게의 사진이 아니라 같은 업종의 예시 사진이에요"
              className="mr-1 inline-flex items-center gap-2 rounded-full border border-line py-0.5 pr-2.5 pl-0.5 font-medium text-muted-foreground hover:border-ink-2"
            >
              <span className="relative size-7 shrink-0 overflow-hidden rounded-full">
                <Image src={example.url} alt="" fill sizes="28px" className="object-cover" unoptimized={!canOptimize(example.url)} />
              </span>
              <span className="max-w-[210px] truncate text-[11px]">
                예시 사진 · © {example.author} · {example.license}
              </span>
            </a>
          ) : null}
          {place.rating !== null ? (
            <span className="tabular inline-flex items-center gap-1 text-ink-2">
              <Star aria-hidden className="size-3.5 fill-gold text-gold-deep" />
              <span className="sr-only">평점</span>
              {place.rating.toFixed(1)}
              <span className="font-medium text-muted-foreground">({num(place.review_count)})</span>
            </span>
          ) : null}
          {stop.congestion ? (
            <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5", congestionTone(stop.congestion.value))}>
              <Users aria-hidden className="size-3" />
              <span className="sr-only">도착 시간 혼잡도</span>
              {stop.congestion.level}
            </span>
          ) : null}
          {place.tags.slice(0, 3).map((tag) => (
            <span key={tag} className="rounded-full bg-soft px-2 py-0.5 text-ink-2">
              {tag}
            </span>
          ))}
        </div>
      ) : null}

      {/* 이유는 상자가 아니라 본문이다: 왼쪽의 가는 선 하나로 "짠이의 말"임을 표시한다 */}
      {stop.reason ? <p className="mt-3 border-l-2 border-line pl-3 text-[13.5px] leading-relaxed font-medium text-ink-2">{stop.reason}</p> : null}

      {/* 도구는 한 줄: 왼쪽은 읽을 것(왜 여기 · 거리뷰 · 지도 앱), 오른쪽은 바꿀 것(순서 · 바꾸기) */}
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-2.5">
        <div className="flex min-w-0 items-center gap-0.5">
          <button
            type="button"
            aria-expanded={open}
            aria-controls={panelId}
            onClick={() => {
              if (!open) track("stop_reason_opened", { course_id: courseId, position: stop.position });
              setOpen((v) => !v);
            }}
            className="inline-flex items-center gap-1 rounded-full px-2 py-1.5 text-[13px] font-extrabold text-blue-deep hover:bg-blue-soft"
          >
            왜 여기?
            <ChevronDown aria-hidden className={cn("size-4 transition-transform duration-300", open && "rotate-180")} />
          </button>
          {KAKAO_KEY ? (
            <button
              type="button"
              aria-expanded={street}
              aria-label={street ? "거리뷰 닫기" : "가게 앞 거리뷰"}
              title={street ? "거리뷰 닫기" : "가게 앞 거리뷰"}
              onClick={() => {
                setStreet((v) => !v);
                if (!street) track("place_link_clicked", { course_id: courseId, position: stop.position, to: "roadview" });
              }}
              className={cn("grid size-11 place-items-center rounded-full hover:bg-soft", street ? "bg-blue-soft text-blue-deep" : "text-ink-2 hover:text-ink")}
            >
              <Eye aria-hidden className="size-4" />
            </button>
          ) : null}
          {/* 그 가게의 실제 사진·메뉴판·후기는 지도 앱에 있다(우리가 긁어 올 수는 없다) → 한 번 탭으로 넘긴다. 카카오맵 공식 링크 규격. */}
          <a
            href={`https://map.kakao.com/link/search/${encodeURIComponent(placeQuery)}`}
            target="_blank"
            rel="noreferrer"
            aria-label="실제 사진·메뉴 보기"
            title="지도 앱에서 실제 사진 · 메뉴 보기"
            onClick={() => track("place_link_clicked", { course_id: courseId, position: stop.position, to: "kakaomap" })}
            className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft hover:text-ink"
          >
            <ExternalLink aria-hidden className="size-4" />
          </a>
          {stop.place.category === STADIUM ? (
            <a
              href={KBO_SCHEDULE}
              target="_blank"
              rel="noreferrer"
              className="ml-1 inline-flex items-center gap-1 rounded-full bg-blue-soft px-2.5 py-1.5 text-[13px] font-extrabold text-blue-deep hover:brightness-95"
            >
              오늘 경기 있는지 확인
              <ExternalLink aria-hidden className="size-3.5" />
            </a>
          ) : null}
        </div>
        {editable ? (
          <div className="flex shrink-0 items-center gap-1">
            <button type="button" onClick={() => onMove(-1)} disabled={busy || stop.position === 1 || !canMoveUp} aria-label={`${place.name} 순서를 앞으로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft disabled:opacity-30">
              <ChevronUp aria-hidden className="size-4" />
            </button>
            <button type="button" onClick={() => onMove(1)} disabled={busy || stop.position === count || !canMoveDown} aria-label={`${place.name} 순서를 뒤로`} className="grid size-11 place-items-center rounded-full text-ink-2 hover:bg-soft disabled:opacity-30">
              <ChevronDown aria-hidden className="size-4" />
            </button>
            <SwapMenu placeName={place.name} pending={swapping} onSwap={onSwap} />
          </div>
        ) : null}
      </div>

'''
between("components/course/StopCard.tsx", "      {/* 사진은 그 순번의 카드 안에 둔다", "      {street && KAKAO_KEY ? <RoadviewPeek", NEW)
edit("components/course/StopCard.tsx", [
    ("import { stopColor } from \"./colors\";\n", ""),
    ("  const index = stop.position - 1;\n", ""),
    ("  const photo = place.thumbnail_url ?? example?.url ?? null;\n", ""),
])
print("ok")
