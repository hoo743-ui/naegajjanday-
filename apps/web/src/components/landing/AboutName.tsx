import Link from "next/link";
import { Play } from "lucide-react";
import { Wordmark } from "@/components/brand/Wordmark";

const PARTS = [
  {
    word: "내가",
    title: "누구와의 하루인지, 내가 정해요",
    body: "어디서 · 몇 명이서 · 얼마로 · 어떤 약속인지. 좋은 하루의 기준은 함께할 사람이 정해요.",
    chips: ["홍대", "2명", "50,000원", "데이트"],
  },
  {
    word: "짠",
    title: "짠은 인색함이 아니라 마음이에요",
    body: "아끼는 짠, 짜는 짠, 짠 하고 나오는 순간. 실제 장소로 예산을 넘지 않게 짜는 건, 같이 가는 사람의 내일까지 아끼는 일이에요.",
    chips: ["식사 22,000", "카페 6,000", "산책 무료", "놀거리 14,000"],
  },
  {
    word: "데이",
    title: "남는 건 장소가 아니라 하루예요",
    body: "먹고 · 걷고 · 쉬고 · 노는 순서가 한 편의 이야기로 이어져요. 남은 돈까지 영수증 한 장에.",
    chips: ["18:00 식사", "19:20 카페", "20:10 산책", "남은 돈 8,000"],
  },
];

/**
 * 소개 페이지의 첫 장: 이름이 곧 서비스다 (docs/38 · docs/40). 인트로를 다시 볼 수 있는 입구도 여기.
 * 코스는 명령이 아니라 편집할 수 있는 초안이라는 태도도 여기서 한 번 말한다.
 */
export function AboutName() {
  return (
    <section aria-labelledby="about-name" className="paper-map bg-paper py-14 lg:py-20">
      <div className="wrap">
        <p className="text-body-sm font-semibold text-muted-foreground">소개</p>
        <h1 id="about-name" className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2 text-display font-extrabold text-ink">
          <Wordmark size="md" /> 는 이런 뜻이에요
        </h1>
        <p className="mt-3 max-w-[620px] text-body-lg text-ink-2">
          하루의 값은 쓴 돈이 아니라 같이 보낸 시간이 정해요. 짠이는 그 시간을 예산 안에서 짜 볼 뿐 — 먼저 짜 본 하루는 정답이 아니라 초안이라, 마음에 안 드는 곳은 바꾸면 돼요.
        </p>
        <Link href="/" className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-full border border-ink/25 bg-white px-4 text-body-sm font-semibold text-ink hover:border-tomato hover:bg-tomato-soft">
          <Play aria-hidden className="size-4" /> 인트로 다시 보기
        </Link>

        <ol className="mt-10 grid gap-4 md:grid-cols-3">
          {PARTS.map((p, i) => (
            <li key={p.word} className="rounded-lg border border-ink/15 bg-white p-5">
              <p className="flex items-baseline gap-2">
                <span className="tabular text-caption font-bold text-muted-foreground">0{i + 1}</span>
                <b className={p.word === "짠" ? "text-h2 font-extrabold text-tomato-deep" : "text-h2 font-extrabold text-ink"}>{p.word}</b>
              </p>
              <h2 className="mt-2 text-h3 font-bold text-ink">{p.title}</h2>
              <p className="mt-1.5 text-body-sm text-ink-2">{p.body}</p>
              <ul className="mt-3 flex flex-wrap gap-1.5 border-t border-dashed border-ink/20 pt-3">
                {p.chips.map((c) => (
                  <li key={c} className="tabular rounded-full border border-ink/20 px-2.5 py-1 text-caption font-semibold text-ink-2">
                    {c}
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
