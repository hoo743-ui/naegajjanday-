import { ChapterMark } from "./ChapterMark";
import { Reveal } from "./Reveal";

const STEPS: { title: string; body: string; quote: string }[] = [
  { title: "예산부터 말해요", body: "어디서, 몇 명이, 얼마로. 가격을 찾아 헤매기 전에 쓸 돈부터 정합니다.", quote: "얼마 쓸 거예요?" },
  { title: "짠이가 걸러내요", body: "예산을 넘는 곳, 그 시간에 문 닫은 곳은 처음부터 뺍니다. 남은 곳을 예산 적합도 · 거리 · 약속의 분위기 · 취향으로 점수 매겨요.", quote: "예산 안에서 찾는 중…" },
  { title: "코스로 이어 줘요", body: "식사에서 카페, 놀거리까지 덜 걷는 순서로 잇고 총액을 계산해요. 마음에 안 드는 한 곳만 바꿔도 예산은 유지돼요.", quote: "짠! 코스 나왔어요" },
];

/**
 * 장면 — 예산 → 영수증 → 코스. 번호 붙은 블록이 아니라 한 줄의 경로 위 세 정거장.
 * 데스크톱은 제목이 왼쪽에 머물고(sticky — 스크롤을 가로채지 않는다) 정거장들이 오른쪽 선을 따라 지나간다.
 * 짠이의 말은 얼굴 없이 한 줄로만 끼어든다 (docs/31 §9).
 */
export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 py-[clamp(48px,7vw,96px)]">
      <div className="wrap">
        <ChapterMark label="예산 → 영수증 → 코스" />
        <div className="mt-10 grid gap-12 lg:grid-cols-[minmax(0,4fr)_minmax(0,6fr)] lg:gap-20">
          <div className="lg:sticky lg:top-[calc(var(--header-h)+48px)] lg:self-start">
            <h2 className="font-serif text-display">
              네 단계의 약속 준비를
              <br />
              <span className="text-blue-deep">한 번의 입력으로</span>
            </h2>
            <p className="mt-6 max-w-[420px] text-body-lg text-ink-2">
              지도 앱에서 검색하고, 가격 확인하고, 직접 더해 보고, 넘으면 다시 검색하던 일. 이제 순서를 뒤집습니다.
            </p>
          </div>

          <ol className="grid">
            {STEPS.map((step, i) => (
              <Reveal as="li" key={step.title} delay={i * 0.06} className="relative pb-12 pl-10 last:pb-0">
                {i < STEPS.length - 1 ? <span aria-hidden className="absolute top-5 bottom-0 left-[6px] border-l-2 border-dashed border-ink/20" /> : null}
                <span aria-hidden className="absolute top-2 left-0 size-3.5 rounded-full border-2 border-ink bg-paper" />
                <h3 className="text-h2 font-bold">{step.title}</h3>
                <p className="mt-2.5 max-w-[520px] text-body text-ink-2">{step.body}</p>
                <p className="mt-4 text-body-sm font-semibold text-muted-foreground">
                  짠이 <span className="text-ink">“{step.quote}”</span>
                </p>
              </Reveal>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
