import Image from "next/image";
import { ChapterMark, PhotoCredit } from "./ChapterMark";
import { Reveal } from "./Reveal";

/**
 * 장면 — 그 하루가 일어나는 곳. 성문 앞을 지나는 오늘의 차들.
 * 사진은 겹쳐 띄우지 않고 한 장을 넓게 편다(docs/31 §14). 글은 그 아래, 제목 5 : 한 문장 7 의 비대칭 (docs/33: 목록은 뺐다).
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
          <p className="max-w-[480px] text-body-lg text-ink-2 lg:pt-2">
            궁궐 옆 카페, 시장 골목의 저녁, 바닷가의 산책. 짠이는 한국관광공사와 공공데이터의 실제 장소로 하루를 이어요.
          </p>
        </div>
      </div>
    </section>
  );
}
