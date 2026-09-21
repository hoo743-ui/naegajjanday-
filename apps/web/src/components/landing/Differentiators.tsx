import { Footprints, Route, Ticket, Wallet, X, type LucideIcon } from "lucide-react";
import { Receipt } from "@/components/brand/Receipt";
import { sampleCourse } from "@/components/brand/sample-course";
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
    body: "식사에서 아낀 돈은 카페로 넘어갑니다. 식당·카페·놀거리를 따로 고르지 않고, 총액이 맞는 조합을 통째로 제안해요.",
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
    from: "식당·카페만",
    to: "놀거리·행사 포함",
  },
];

/** 설명 대신 장면으로: 늘 하던 방식(검색 → 더하기 → 초과 → 다시 검색)과 영수증 한 장. 품목은 히어로와 같은 예시 계산이다. */
const OLD_WAY = ["맛집 검색", "가격 확인", "카페 검색", "놀거리 검색", "계산기로 더하기"];
const DEMO = { budget: 40000, party: 2 };

function Compare() {
  return (
    <Reveal className="mt-12 grid items-stretch gap-5 lg:grid-cols-[1fr_auto_1fr]">
      <div className="flex flex-col rounded-[32px] border border-line bg-white p-7 sm:p-8">
        <p className="text-sm font-extrabold text-muted-foreground">늘 하던 방식</p>
        <ol className="mt-5 grid gap-2.5">
          {OLD_WAY.map((step, i) => (
            <li key={step} className="flex items-center gap-3 rounded-2xl bg-[#F3F5FA] px-4 py-3 text-[15px] font-bold text-ink-2">
              <span className="tabular text-xs font-extrabold text-muted-foreground">{i + 1}</span>
              {step}
            </li>
          ))}
        </ol>
        <p className="mt-4 flex items-center justify-between gap-3 rounded-2xl bg-pink-soft px-4 py-3.5 text-pink-deep">
          <span className="flex items-center gap-2 text-[15px] font-extrabold">
            <X aria-hidden className="size-4" /> 더해 보니 예산 초과
          </span>
          <b className="tabular text-lg font-extrabold">+12,000원</b>
        </p>
        <p className="mt-3 text-center text-sm font-bold text-muted-foreground">…그래서 처음부터 다시 검색</p>
      </div>

      <p aria-hidden className="grid place-items-center font-round text-2xl text-muted-foreground max-lg:py-1">
        <span className="max-lg:rotate-90">→</span>
      </p>

      <div className="flex flex-col justify-center rounded-[32px] bg-grad-soft p-6 sm:p-8">
        <p className="mb-4 text-center text-sm font-extrabold text-blue-deep">내가짠데이: 예산부터 말하면</p>
        <Receipt
          className="mx-auto w-full max-w-[360px]"
          heading={`${DEMO.party}명 · 40,000원 · 예시`}
          items={sampleCourse(DEMO.budget / DEMO.party, DEMO.party)}
          budget={DEMO.budget}
        />
      </div>
    </Reveal>
  );
}

export function Differentiators() {
  return (
    <section id="different" className="bg-soft-band scroll-mt-20 py-20 lg:py-28">
      <div className="wrap">
        <div className="text-center">
          <span className="inline-flex rounded-full bg-pink-soft px-3.5 py-2 text-sm font-extrabold text-pink-deep">무엇이 다른가요</span>
          <h2 className="mt-4 mb-4 text-[clamp(29px,4.2vw,50px)] font-extrabold font-serif">
            아끼는 것이 아니라,
            <br />
            <span className="hl">예산 안에서 더 잘 즐기게</span> 합니다
          </h2>
        </div>

        <Compare />

        <div className="mt-5 grid gap-5 md:grid-cols-2">
          {ITEMS.map((item, i) => (
            <Reveal as="article" key={item.tag} delay={(i % 2) * 0.08} className="flex flex-col gap-4 rounded-[32px] border border-line bg-white p-8 shadow-soft transition-[transform,box-shadow] duration-300 hover:-translate-y-1 hover:shadow-card">
              <div className="flex items-center gap-3">
                <span className="bg-grad-soft grid size-[54px] place-items-center rounded-[18px] text-blue-deep">
                  <item.icon aria-hidden className="size-[26px]" />
                </span>
                <span className="rounded-lg bg-blue-soft px-3 py-1.5 text-[13px] font-extrabold text-blue-deep">{item.tag}</span>
              </div>
              <h3 className="text-[clamp(20px,2.2vw,25px)] font-extrabold">{item.title}</h3>
              <p className="text-[15.5px] text-muted-foreground">{item.body}</p>
              <p className="mt-auto flex flex-wrap items-center gap-2 pt-2 text-sm font-extrabold">
                <span className="rounded-full bg-[#EEF1F7] px-3.5 py-1.5 text-[#66718A] line-through">{item.from}</span>
                <span aria-hidden className="text-[#9AA4B8]">→</span>
                <span className="sr-only">대신</span>
                <span className="rounded-full bg-ink px-3.5 py-1.5 text-white">{item.to}</span>
              </p>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}
