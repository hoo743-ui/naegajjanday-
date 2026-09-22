import { Footprints, Route, Ticket, Wallet, type LucideIcon } from "lucide-react";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
import { ChapterMark } from "./ChapterMark";
import { Reveal } from "./Reveal";

const ITEMS: { icon: LucideIcon; tag: string; title: string; body: string; from: string; to: string }[] = [
  {
    icon: Wallet,
    tag: "예산이 먼저",
    title: "가격을 검색하지 않아요. 예산으로 결정해요",
    body: "예산을 먼저 받고, 그 안에 들어오는 곳만 보여 줍니다. 무조건 싼 곳이 아니라 예산을 알맞게 쓰는 곳이 높은 점수를 받아요.",
    from: "가격 검색",
    to: "예산 기반 결정",
  },
  {
    icon: Route,
    tag: "장소가 아니라 코스",
    title: "맛집 하나로 끝나지 않는 하루 전체",
    body: "식사에서 아낀 돈은 카페로 넘어갑니다. 식당 · 카페 · 놀거리를 따로 고르지 않고, 총액이 맞는 조합을 통째로 제안해요.",
    from: "장소 추천",
    to: "하루 소비 코스",
  },
  {
    icon: Footprints,
    tag: "진짜 동선 최적화",
    title: "가장 덜 걷는 순서를 계산해요",
    body: "영업시간과 이동시간을 함께 놓고 방문 순서를 풉니다. 밥 먹고 카페 가는 자연스러운 순서는 지키면서요.",
    from: "지도에서 눈대중",
    to: "경로 최적화",
  },
  {
    icon: Ticket,
    tag: "관광지 · 축제까지",
    title: "오늘 열리는 축제도 코스에 넣어요",
    body: "공원, 전시, 문화공간, 지금 진행 중인 축제까지 후보에 올립니다. 무료로 즐길 거리는 예산을 아껴 주는 카드예요.",
    from: "식당 · 카페만",
    to: "놀거리 · 행사 포함",
  },
];

/** 설명 대신 장면으로: 늘 하던 방식(검색 → 더하기 → 초과 → 다시 검색)과 영수증 한 장. 품목은 히어로와 같은 예시 계산이다. */
const OLD_WAY = ["맛집 검색", "가격 확인", "카페 검색", "놀거리 검색", "계산기로 더하기"];
const DEMO = { budget: 40000, party: 2 };

/**
 * 장면 03 — 무엇이 다른가요. 흰 카드 여섯 장이던 구획을 열린 배치로:
 * 왼쪽은 지워지는 옛 방식(줄이 그어진 목록), 오른쪽은 영수증 한 장. 아래 네 가지는 선으로만 나눈 격자.
 */
export function Differentiators() {
  return (
    <section id="different" className="scroll-mt-20 py-[clamp(72px,10vw,140px)]">
      <div className="wrap">
        <ChapterMark n="03" label="무엇이 다른가요" />
        <h2 className="mt-12 max-w-[760px] font-serif text-display">
          아끼는 것이 아니라,
          <br />
          예산 안에서 <span className="relative whitespace-nowrap">더 잘 즐기게<span aria-hidden className="absolute inset-x-0 bottom-[0.06em] -z-10 h-[0.2em] rounded-full bg-gold/40" /></span> 합니다
        </h2>

        <Reveal className="mt-14 grid items-center gap-12 lg:grid-cols-[1fr_1fr] lg:gap-20">
          <div>
            <p className="text-body-sm font-semibold text-muted-foreground">늘 하던 방식</p>
            <ol className="mt-4 grid border-l-2 border-line pl-6">
              {OLD_WAY.map((step, i) => (
                <li key={step} className="flex items-baseline gap-3 py-2 text-body-lg font-bold text-ink-2/70">
                  <span className="tabular text-caption font-extrabold text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
                  <span className="line-through decoration-ink/25 decoration-[1.5px]">{step}</span>
                </li>
              ))}
            </ol>
            <p className="mt-5 flex items-baseline justify-between gap-3 border-t border-pink/40 pt-4 text-pink-deep">
              <span className="text-body font-extrabold">더해 보니 예산 초과</span>
              <b className="money text-price-sm">+12,000원</b>
            </p>
            <p className="mt-2 text-body-sm font-semibold text-muted-foreground">…그래서 처음부터 다시 검색</p>
          </div>

          <div>
            <p className="mb-4 text-body-sm font-semibold text-blue-deep">내가짠데이: 예산부터 말하면</p>
            <Receipt className="w-full max-w-[380px]" heading={`${DEMO.party}명 · 40,000원 · 예시`} items={sampleCourse(DEMO.budget / DEMO.party, DEMO.party)} budget={DEMO.budget} />
          </div>
        </Reveal>

        <div className="mt-20 grid gap-x-16 md:grid-cols-2">
          {ITEMS.map((item, i) => (
            <Reveal as="article" key={item.tag} delay={(i % 2) * 0.06} className="grid content-start gap-3 border-t border-ink/12 py-9">
              <p className="flex items-center gap-2 text-body-sm font-semibold text-blue-deep">
                <item.icon aria-hidden className="size-4" />
                {item.tag}
              </p>
              <h3 className="text-h2 font-bold">{item.title}</h3>
              <p className="max-w-[500px] text-body text-ink-2">{item.body}</p>
              <p className="mt-1 flex flex-wrap items-center gap-2 text-body-sm font-semibold">
                <span className="text-muted-foreground line-through">{item.from}</span>
                <span aria-hidden className="text-muted-foreground">→</span>
                <span className="sr-only">대신</span>
                <span className="text-ink">{item.to}</span>
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
