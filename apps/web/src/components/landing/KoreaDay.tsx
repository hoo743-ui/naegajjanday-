import Image from "next/image";
import { ChapterMark, PhotoCredit } from "./ChapterMark";
import { Reveal } from "./Reveal";

/** 한국의 공간 → 그 공간에서 짜는 하루. 사진은 장식이 아니라 "여기서 이런 하루"라는 약속이다 (docs/25 §3) */
const LINES = [
  { place: "숭례문", day: "서울의 하루" },
  { place: "한옥 골목", day: "감성 데이트" },
  { place: "시장", day: "먹거리 코스" },
  { place: "바닷가", day: "여행 코스" },
  { place: "야경", day: "밤 데이트" },
];

/**
 * 장면 01 — 과거 × 현재. 성문 앞을 지나는 오늘의 차들, 궁궐 뒤로 선 빌딩들.
 * 한국적인 이미지로 시작하지만, 곧바로 "그 공간에서 내 하루를 만든다"로 이어진다.
 */
export function KoreaDay() {
  return (
    <section id="korea" className="scroll-mt-20 py-[clamp(72px,10vw,140px)]">
      <div className="wrap">
        <ChapterMark n="01" label="과거 × 현재" />

        <div className="mt-12 grid items-center gap-12 lg:grid-cols-[1.1fr_.9fr] lg:gap-20">
          {/* 사진 두 장: 큰 한 장 위에 작은 한 장을 겹친다. 사진 위에는 글자를 얹지 않는다 */}
          <Reveal className="relative pb-16 sm:pb-20">
            <figure>
              <div className="photo-edge relative aspect-[3/2] overflow-hidden rounded-[20px]">
                <Image src="/images/story/sungnyemun-night.jpg" alt="밤의 숭례문과 그 앞을 지나는 차들의 빛" fill sizes="(max-width: 1024px) 92vw, 600px" className="object-cover" />
              </div>
              <figcaption className="mt-2">
                <PhotoCredit place="숭례문" />
              </figcaption>
            </figure>
            <figure className="absolute right-0 bottom-0 w-[46%] lg:right-[-6%]">
              <div className="photo-edge relative aspect-[4/3] overflow-hidden rounded-[16px] shadow-float ring-[6px] ring-paper">
                <Image src="/images/story/deoksugung.jpg" alt="덕수궁 중화전 뒤로 보이는 도심의 빌딩" fill sizes="(max-width: 1024px) 44vw, 280px" className="object-cover" />
              </div>
              <figcaption className="mt-2 text-right">
                <PhotoCredit place="덕수궁" />
              </figcaption>
            </figure>
          </Reveal>

          <Reveal delay={0.08}>
            <h2 className="font-serif text-[clamp(30px,3.8vw,50px)] leading-[1.22] font-bold tracking-[-0.03em]">
              성문 앞에서 시작해도,
              <br />
              한강에서 끝나도,
              <br />
              하루는 한 장이에요.
            </h2>
            <p className="mt-6 max-w-[460px] text-[16.5px] leading-[1.8] text-ink-2">
              궁궐 옆 카페, 시장 골목의 저녁, 바닷가의 산책. 짠이는 한국관광공사와 공공데이터에 있는 실제 장소로 하루를 잇고, 그 하루를 영수증 한 장으로 정리해요.
            </p>

            {/* 영수증 문법: 공간 ···· 하루 */}
            <ul className="mt-9 grid max-w-[420px] gap-3 text-[15.5px]">
              {LINES.map((line) => (
                <li key={line.place} className="flex items-baseline gap-2">
                  <span className="font-bold text-ink">{line.place}</span>
                  <span aria-hidden className="receipt-leader" />
                  <span className="font-extrabold text-blue-deep">{line.day}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
