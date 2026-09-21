import { Jjani } from "@/components/mascot/Jjani";
import type { JjaniMood } from "@/lib/mascot-copy";
import { Reveal } from "./Reveal";

const STEPS: { n: number; mood: JjaniMood; title: string; body: string; quote: string }[] = [
  { n: 1, mood: "hi", title: "예산부터 말해요", body: "어디서, 몇 명이, 얼마로. 가격을 찾아 헤매기 전에 쓸 돈부터 정합니다.", quote: "얼마 쓸 거예요?" },
  { n: 2, mood: "think", title: "짠이가 걸러내요", body: "예산을 넘는 곳, 그 시간에 문 닫은 곳은 처음부터 뺍니다. 남은 곳을 예산 적합도·거리·약속의 분위기·취향으로 점수 매겨요.", quote: "예산 안에서 찾는 중…" },
  { n: 3, mood: "done", title: "코스로 이어 줘요", body: "식사에서 카페, 놀거리까지 덜 걷는 순서로 잇고 총액을 계산해요. 마음에 안 드는 한 곳만 바꿔도 예산은 유지돼요.", quote: "짠! 코스 나왔어요" },
];

export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-20 py-20 lg:py-28">
      <div className="wrap">
        <div className="text-center">
          <span className="inline-flex rounded-full bg-blue-soft px-3.5 py-2 text-sm font-extrabold text-blue-deep">짜는 방법</span>
          <h2 className="mt-4 mb-4 text-[clamp(29px,4.2vw,50px)] font-extrabold font-serif">
            네 단계의 약속 준비를
            <br />
            <span className="text-blue-deep">한 번의 입력으로</span>
          </h2>
          <p className="mx-auto max-w-[640px] text-[clamp(16px,1.6vw,19px)] text-muted-foreground">
            지도 앱에서 검색하고, 가격 확인하고, 직접 더해 보고, 넘으면 다시 검색하던 일. 이제 순서를 뒤집습니다.
          </p>
        </div>

        <ol className="mt-12 grid gap-5 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <Reveal as="li" key={step.n} delay={i * 0.08} className="group relative rounded-card border border-line bg-white p-7 shadow-soft transition-[transform,box-shadow] duration-300 hover:-translate-y-1.5 hover:shadow-card">
              <div className="flex items-start justify-between">
                <span className="tabular grid size-10 place-items-center rounded-full bg-ink text-base font-extrabold text-white">{step.n}</span>
                <Jjani mood={step.mood} size={84} animated={false} decorative className="-mt-2 transition-transform duration-300 group-hover:-rotate-3 group-hover:scale-105" />
              </div>
              <h3 className="mt-3 mb-2.5 text-xl font-extrabold">{step.title}</h3>
              <p className="text-[15.5px] text-muted-foreground">{step.body}</p>
              <p className="mt-5 inline-block rounded-[14px] bg-paper-2 text-ink-2 px-3 py-1.5 text-sm font-extrabold">“{step.quote}”</p>
            </Reveal>
          ))}
        </ol>
      </div>
    </section>
  );
}
