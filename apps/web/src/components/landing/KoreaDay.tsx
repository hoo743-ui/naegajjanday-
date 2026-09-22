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
 * 장면 — 그 하루가 일어나는 곳. 성문 앞을 지나는 오늘의 차들.
 * 사진은 겹쳐 띄우지 않고 한 장을 넓게 편다(docs/31 §14). 글은 그 아래, 제목 5 : 본문 7 의 비대칭.
 */
export function KoreaDay() {
  return (
    <section id="korea" className="scroll-mt-20 pt-[clamp(56px,8vw,112px)] pb-[clamp(48px,7vw,96px)]">
      <div className="wrap">
        <ChapterMark label="그 하루가 일어나는 곳" />

        <Reveal className="mt-8">
          <figure>
            <div className="photo-edge relative aspect-[4/3] overflow-hidden rounded-lg sm:aspect-[21/9]">
              <Image src="/images/story/sungnyemun-night.jpg" alt="밤의 숭례문과 그 앞을 지나는 차들의 빛" fill sizes="(max-width: 1200px) 94vw, 1136px" className="object-cover object-[50%_60%]" />
            </div>
            <figcaption className="mt-2">
              <PhotoCredit place="숭례문" />
            </figcaption>
          </figure>
        </Reveal>

        <div className="mt-10 grid gap-x-16 gap-y-8 lg:mt-14 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
          <h2 className="font-serif text-display">
            성문 앞에서 시작해도,
            <br />
            한강에서 끝나도,
            <br />
            하루는 한 장이에요.
          </h2>
          <div className="lg:pt-2">
            <p className="max-w-[520px] text-body-lg text-ink-2">
              궁궐 옆 카페, 시장 골목의 저녁, 바닷가의 산책. 짠이는 한국관광공사와 공공데이터에 있는 실제 장소로 하루를 잇고, 그 하루를 영수증 한 장으로 정리해요.
            </p>
            {/* 영수증 문법: 공간 ···· 하루 */}
            <ul className="mt-8 grid max-w-[460px] gap-3 text-body">
              {LINES.map((line) => (
                <li key={line.place} className="flex items-baseline gap-2">
                  <span className="font-semibold text-ink">{line.place}</span>
                  <span aria-hidden className="receipt-leader" />
                  <span className="font-bold text-blue-deep">{line.day}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
