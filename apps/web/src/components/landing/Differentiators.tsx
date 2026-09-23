import { Money } from "@/components/brand/Money";
import { sampleCourse } from "@/components/brand/sample-course";
import { Reveal } from "./Reveal";

const ITEMS: { tag: string; title: string; from: string; to: string }[] = [
  {
    tag: "예산이 먼저",
    title: "가격을 검색하지 않아요. 예산으로 결정해요",
    from: "가격 검색",
    to: "예산 기반 결정",
  },
  {
    tag: "장소가 아니라 코스",
    title: "맛집 하나로 끝나지 않는 하루 전체",
    from: "장소 추천",
    to: "하루 소비 코스",
  },
  {
    tag: "진짜 동선 최적화",
    title: "가장 덜 걷는 순서를 계산해요",
    from: "지도에서 눈대중",
    to: "경로 최적화",
  },
  {
    tag: "관광지 · 축제까지",
    title: "오늘 열리는 축제도 코스에 넣어요",
    from: "식당 · 카페만",
    to: "놀거리 · 행사 포함",
  },
];

/** 설명 대신 장면으로: 늘 하던 방식(검색 → 더하기 → 초과 → 다시 검색)과 영수증 한 장. 품목은 히어로와 같은 예시 계산이다. */
const OLD_WAY = ["맛집 검색", "가격 확인", "카페 검색", "놀거리 검색", "계산기로 더하기"];
const DEMO = { budget: 40000, party: 2 };
const DEMO_ITEMS = sampleCourse(DEMO.budget / DEMO.party, DEMO.party);
const DEMO_TOTAL = DEMO_ITEMS.reduce((sum, item) => sum + item.price, 0);

/**
 * 장면 — 무엇이 다른가요. 왼쪽은 지워지는 옛 방식(줄이 그어진 목록), 오른쪽은 같은 하루를 예산부터 짠 결과 — 남은 돈 한 숫자.
 * 영수증 모양은 히어로에 한 번 있으니 여기서는 쓰지 않는다 (docs/33). 이 장면에는 이름표도 없다(장면마다 밀도를 다르게).
 * 아래 네 가지는 아이콘 격자(SaaS 의 "기능 소개")가 아니라 장부의 줄: 왼쪽 칸에 "무엇이 무엇으로", 오른쪽 칸에 한 줄 (docs/31 §6).
 */
export function Differentiators() {
  return (
    <section id="different" className="scroll-mt-20 py-[clamp(48px,7vw,96px)]">
      <div className="wrap">
        <h2 className="max-w-[760px] font-serif text-display">
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

          {/* 같은 네 곳을 예산부터 짜면: 넘치는 대신 남는다. 금색은 돈에만 */}
          <div className="grid content-start gap-5 border-l-2 border-gold pl-6 lg:pl-8">
            <p className="text-body font-bold text-blue-deep">예산부터 말하면</p>
            <p className="tabular text-body-lg font-semibold text-ink-2">
              둘이서 {DEMO.budget.toLocaleString("ko-KR")}원 · {DEMO_ITEMS.map((item) => item.label).join(" → ")}
            </p>
            <div className="grid">
              <span className="text-body-sm font-semibold text-gold-ink">남은 돈</span>
              <Money value={DEMO.budget - DEMO_TOTAL} className="money text-price-lg text-gold-ink" />
            </div>
            <p className="text-body-sm text-muted-foreground">업종 평균가로 계산한 예시예요.</p>
          </div>
        </Reveal>

        <div className="mt-20 border-b border-ink/12">
          {ITEMS.map((item, i) => (
            <Reveal as="article" key={item.tag} delay={Math.min(i * 0.04, 0.12)} className="grid gap-x-16 gap-y-3 border-t border-ink/12 py-6 md:grid-cols-[minmax(0,4fr)_minmax(0,8fr)] md:items-center md:py-7">
              <p className="grid content-start gap-1 text-body font-semibold">
                <span className="text-muted-foreground line-through decoration-ink/30">{item.from}</span>
                <span className="sr-only">대신</span>
                <span className="text-ink">
                  <span aria-hidden className="mr-1.5 text-muted-foreground">→</span>
                  {item.to}
                </span>
              </p>
              <h3 className="text-h2 font-bold">{item.title}</h3>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
