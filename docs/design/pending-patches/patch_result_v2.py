"""Redesign v2 · step 1 (docs/25 §5, §9-1): the course result reads CONDITION → JJANI → RECEIPT → the rest.

- the conditions are chips (one fact each) with "조건 바꾸기" at the end, not one blue sentence
- the receipt comes right after Jjani's line: the story (narrative) and the neighbourhood card move below it
- the narrative is a ruled aside, the three numbers are one ruled row — not four more white cards

DRY=1 → anchors are asserted and nothing is written. Do not run in ANY mode while an audit is running.
"""
import io
import os

DRY = os.environ.get("DRY") == "1"
ROOT = r"C:\Users\LG\OneDrive\바탕 화면\링커스\내가짠데이\apps\web\src"


def edit(rel, pairs):
    p = os.path.join(ROOT, rel)
    s = io.open(p, encoding="utf-8").read()
    for a, b in pairs:
        assert s.count(a) == 1, (rel, s.count(a), a[:70])
        s = s.replace(a, b, 1)
    if DRY:
        return
    io.open(p, "w", encoding="utf-8", newline="\n").write(s)


NARRATIVE_OLD = (
    "              {narrative.text ? (\n"
    "                <p className=\"rounded-card bg-white p-5 text-[15px] leading-[1.75] whitespace-pre-line text-ink-2 shadow-soft\" aria-live=\"polite\" aria-busy={narrative.status === \"streaming\"}>\n"
    "                  {narrative.text}\n"
    "                  {narrative.status === \"streaming\" ? <span aria-hidden className=\"ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse rounded-sm bg-blue-deep\" /> : null}\n"
    "                </p>\n"
    "              ) : narrative.status === \"streaming\" ? (\n"
    "                <p className=\"skeleton-shimmer h-[68px] rounded-card\" aria-label=\"짠이가 코스 설명을 쓰는 중\" />\n"
    "              ) : null}\n"
    "            </header>\n"
)
LOCAL_NEW = (
    "              {data.local ? <LocalCard local={data.local} focus={request.focus} onPick={readOnly ? undefined : (word) => onReroll(false, word)} busy={reroll.isPending} /> : null}\n\n"
)
LEFTOVER_OLD = (
    "              {/* 남은 돈은 자랑하고 끝낼 숫자가 아니다: 그 돈으로 갈 만한 곳을 권한다 */}\n"
    "              <LeftoverCard\n"
    "                courseId={id}\n"
    "                budgetLeft={data.totals.budget_left}\n"
    "                budget={request.budget_total}\n"
    "                editable={!readOnly}\n"
    "                onAdded={(name, price) => setNotice({ mood: \"cheers\", title: `${name}을(를) 코스에 넣었어요`, body: price > 0 ? `${won(price)}을 더 써서, 남은 돈은 ${won(data.totals.budget_left - price)}이에요.` : \"돈은 그대로 남아 있어요.\" })}\n"
    "              />\n\n"
)
TIMELINE_END = (
    "                onSwap={onSwap}\n"
    "                onMove={onMove}\n"
    "              />\n"
)
NARRATIVE_NEW = (
    "\n"
    "              {/* 늦게 도착하는 것은 장소 목록 뒤에 둔다: 추천(조회 뒤에 뜬다)과 이야기(스켈레톤 68px → 본문 250px)가 목록 위에\n"
    "                  있을 때는, 화면이 뜬 뒤 1초 동안 첫 장소 카드가 613px 아래로 밀렸다(누르려던 버튼이 달아난다). 추천은 \"마지막\n"
    "                  장소에서 걸어갈 수 있는 곳\"이므로 마지막 장소 다음이 제자리이기도 하다 */}\n"
    + LEFTOVER_OLD.split("\n", 1)[1]
    + "              {/* 짠이의 이야기: 카드가 아니라 금빛 선 하나를 세운 곁글 */}\n"
    "              {narrative.text ? (\n"
    "                <p className=\"border-l-2 border-gold pl-4 text-[15px] leading-[1.8] whitespace-pre-line text-ink-2\" aria-live=\"polite\" aria-busy={narrative.status === \"streaming\"}>\n"
    "                  {narrative.text}\n"
    "                  {narrative.status === \"streaming\" ? <span aria-hidden className=\"ml-0.5 inline-block h-4 w-[7px] translate-y-0.5 animate-pulse rounded-sm bg-blue-deep\" /> : null}\n"
    "                </p>\n"
    "              ) : narrative.status === \"streaming\" ? (\n"
    "                <p className=\"skeleton-shimmer h-[68px] rounded-2xl\" aria-label=\"짠이가 코스 설명을 쓰는 중\" />\n"
    "              ) : null}\n"
)

edit("components/course/CourseView.tsx", [
    # 1. conditions → chips
    ("              <p className=\"tabular flex flex-wrap gap-x-2 text-[13px] font-extrabold text-blue-deep\">\n"
     "                {[request.conditions?.includes(\"rain\") ? \"비 오는 날\" : null, request.days && request.days > 1 ? `${request.day}일차 / ${request.days}일` : null, placeLabel, purposeLabel, `${request.party_size}명`, `예산 ${won(request.budget_total)}${tripDay && request.trip_budget_total ? ` (여행 전체 ${won(request.trip_budget_total)})` : \"\"}`, dateLabel(request.start_at), meetWindow(request.start_at, request.duration_min), request.style === \"fun\" ? \"재미 우선\" : null].filter(Boolean).join(\" · \")}\n"
     "              </p>\n",
     "              <ul aria-label=\"이 코스의 조건\" className=\"tabular flex flex-wrap items-center gap-1.5\">\n"
     "                {[request.conditions?.includes(\"rain\") ? \"비 오는 날\" : null, request.days && request.days > 1 ? `${request.day}일차 / ${request.days}일` : null, placeLabel, purposeLabel, `${request.party_size}명`, `예산 ${won(request.budget_total)}${tripDay && request.trip_budget_total ? ` (여행 전체 ${won(request.trip_budget_total)})` : \"\"}`, dateLabel(request.start_at), meetWindow(request.start_at, request.duration_min), request.style === \"fun\" ? \"재미 우선\" : null]\n"
     "                  .filter((c): c is string => Boolean(c))\n"
     "                  .map((c) => (\n"
     "                    <li key={c} className=\"rounded-full border border-line bg-white/70 px-2.5 py-1 text-[12.5px] font-bold text-ink-2\">\n"
     "                      {c}\n"
     "                    </li>\n"
     "                  ))}\n"
     "                {readOnly ? null : (\n"
     "                  <li>\n"
     "                    <Link href={changeHref} className=\"inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[12.5px] font-extrabold text-blue-deep hover:bg-blue-soft\">\n"
     "                      <SlidersHorizontal aria-hidden className=\"size-3.5\" /> 조건 바꾸기\n"
     "                    </Link>\n"
     "                  </li>\n"
     "                )}\n"
     "              </ul>\n"),
    # 2. Jjani says one line, smaller: the receipt is the hero of this screen
    ("tone=\"white\" size={84} bubbleKey={`${id}-${data.totals.price}`}>", "tone=\"white\" size={64} bubbleKey={`${id}-${data.totals.price}`}>"),
    # 3. the story leaves the header …
    (NARRATIVE_OLD, "            </header>\n"),
    # … and the neighbourhood card leaves the space above the receipt
    ("            {data.local ? <LocalCard local={data.local} focus={request.focus} onPick={readOnly ? undefined : (word) => onReroll(false, word)} busy={reroll.isPending} /> : null}\n\n"
     "            <AlternativeTabs",
     "            <AlternativeTabs"),
    # … the neighbourhood card (it comes with the course: nothing arrives late) lands after the receipt
    ("              <dl className=\"tabular grid grid-cols-3 gap-2 text-center\">\n",
     LOCAL_NEW + "              <dl className=\"tabular grid grid-cols-3 divide-x divide-line border-y border-line py-3 text-center\">\n"),
    # … what arrives late (the offer, the story) goes after the places, so nothing above them grows
    (LEFTOVER_OLD, ""),
    (TIMELINE_END, TIMELINE_END + NARRATIVE_NEW),
    # 4. three numbers: one ruled row instead of three cards
    ("                  <div key={item.k} className=\"rounded-2xl bg-white px-2 py-3 shadow-soft\">\n",
     "                  <div key={item.k} className=\"px-2\">\n"),
    ("const baseRequest: GenerateCourseRequest = {",
     "// 조건 바꾸기: 지역 · 목적을 채운 채로 위저드로 돌아간다 (역 · 장소 기준 코스는 지역이 없어 목적만)\n"
     "  const changeHref = `/plan?${new URLSearchParams({ ...(request.region ? { region: request.region.slug } : {}), purpose: request.purpose.code }).toString()}`;\n"
     "  const baseRequest: GenerateCourseRequest = {"),
    ("import { Bookmark, BookmarkCheck, Check, Clock, RotateCw, Share2, Sparkles, TriangleAlert, Users } from \"lucide-react\";",
     "import { Bookmark, BookmarkCheck, Check, Clock, RotateCw, Share2, SlidersHorizontal, Sparkles, TriangleAlert, Users } from \"lucide-react\";"),
])
print("dry: anchors ok, nothing written" if DRY else "written")
