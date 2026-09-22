import { Jjani } from "@/components/mascot/Jjani";
import type { JjaniMood } from "@/lib/mascot-copy";
import { ChapterMark } from "./ChapterMark";
import { Reveal } from "./Reveal";

const STEPS: { n: string; mood: JjaniMood; title: string; body: string; quote: string }[] = [
  { n: "01", mood: "hi", title: "예산부터 말해요", body: "어디서, 몇 명이, 얼마로. 가격을 찾아 헤매기 전에 쓸 돈부터 정합니다.", quote: "얼마 쓸 거예요?" },
  { n: "02", mood: "think", title: "짠이가 걸러내요", body: "예산을 넘는 곳, 그 시간에 문 닫은 곳은 처음부터 뺍니다. 남은 곳을 예산 적합도 · 거리 · 약속의 분위기 · 취향으로 점수 매겨요.", quote: "예산 안에서 찾는 중…" },
  { n: "03", mood: "done", title: "코스로 이어 줘요", body: "식사에서 카페, 놀거리까지 덜 걷는 순서로 잇고 총액을 계산해요. 마음에 안 드는 한 곳만 바꿔도 예산은 유지돼요.", quote: "짠! 코스 나왔어요" },
];

/**
 * 장면 02 — 예산 → 영수증 → 코스. 카드 세 장이 아니라, 영수증의 줄처럼 한 줄씩 찍히는 세 단계.
 * 데스크톱은 제목이 왼쪽에 머물고(sticky — 스크롤을 가로채지 않는다) 단계들이 오른쪽으로 지나간다.
 */
export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 bg-paper-2 py-[clamp(72px,10vw,140px)]">
      <div className="wrap">
        <ChapterMark n="02" label="예산 → 영수증 → 코스" />
        <div className="mt-12 grid gap-12 lg:grid-cols-[.9fr_1.1fr] lg:gap-20">
          <div className="lg:sticky lg:top-[calc(var(--header-h)+48px)] lg:self-start">
            <h2 className="font-serif text-display">
              네 단계의 약속 준비를
              <br />
              <span className="text-blue-deep">한 번의 입력으로</span>
            </h2>
            <p className="mt-6 max-w-[440px] text-body-lg text-ink-2">
              지도 앱에서 검색하고, 가격 확인하고, 직접 더해 보고, 넘으면 다시 검색하던 일. 이제 순서를 뒤집습니다.
            </p>
          </div>

          <ol className="grid">
            {STEPS.map((step, i) => (
              <Reveal as="li" key={step.n} delay={i * 0.06} className="grid grid-cols-[auto_1fr] gap-x-6 border-t-[1.5px] border-dashed border-ink/20 py-9 first:border-t-0 first:pt-0 sm:gap-x-9">
                <span className="tabular text-h1 leading-none font-semibold text-ink/35">{step.n}</span>
                <div>
                  <h3 className="text-h2 font-bold">{step.title}</h3>
                  <p className="mt-2.5 max-w-[520px] text-body text-ink-2">{step.body}</p>
                  {/* 짠이는 한 줄로만 끼어든다 */}
                  <p className="mt-5 inline-flex items-center gap-2 text-body-sm font-semibold text-ink">
                    <Jjani mood={step.mood} size={30} animated={false} decorative />“{step.quote}”
                  </p>
                </div>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
