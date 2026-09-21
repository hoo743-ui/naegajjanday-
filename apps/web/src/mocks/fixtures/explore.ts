/**
 * ⚠️ 개발용 목 데이터 (탐색). MSW 핸들러만 import 한다. 화면 컴포넌트에서 쓰지 말 것.
 * 지역별로 같은 틀을 찍어 내되, 좌표는 지역 중심 주변으로 결정적으로 흩뿌린다.
 */
import type { Attraction, AttractionType, EventItem, Region } from "@/lib/api/types";
import { regions } from "./meta";

interface Seed {
  type: AttractionType;
  name: (region: Region) => string;
  price: number;
  tags: string[];
  summary: string;
  rating: number | null;
  /** 기간이 있는 항목: [시작 오프셋(일), 종료 오프셋(일)] */
  period?: [number, number];
}

const SEEDS: Seed[] = [
  { type: "attraction", name: (r) => `${r.name} 전망 포인트`, price: 0, tags: ["뷰맛집", "사진 잘 나오는"], summary: "해 질 무렵에 가면 동네가 한눈에 들어와요.", rating: 4.5 },
  { type: "attraction", name: (r) => `${r.name} 골목 벽화길`, price: 0, tags: ["산책", "사진 잘 나오는"], summary: "천천히 걸으며 구경하기 좋은 골목이에요.", rating: 4.3 },
  { type: "attraction", name: () => "레트로 오락실 거리", price: 5000, tags: ["실내", "힙한"], summary: "동전 몇 개로 한 시간이 훌쩍 가요.", rating: 4.2 },
  { type: "park", name: (r) => `${r.name} 숲길 공원`, price: 0, tags: ["산책", "조용한"], summary: "돈 들이지 않고 걷기 좋은 무료 산책 코스예요.", rating: 4.6 },
  { type: "park", name: () => "물빛 호수공원", price: 0, tags: ["산책", "뷰맛집"], summary: "호수를 한 바퀴 도는 데 40분쯤 걸려요.", rating: 4.7 },
  { type: "exhibition", name: () => "미디어아트 특별전", price: 15000, tags: ["전시", "실내", "사진 잘 나오는"], summary: "빛과 소리로 채운 몰입형 전시예요.", rating: 4.4, period: [-20, 21] },
  { type: "exhibition", name: () => "동네 미술관 기획전", price: 5000, tags: ["전시", "조용한"], summary: "작지만 알찬 기획전, 한 시간이면 충분해요.", rating: 4.5, period: [-5, 40] },
  { type: "exhibition", name: () => "사진가 3인전", price: 0, tags: ["전시", "조용한"], summary: "무료로 열리는 사진전이에요.", rating: null, period: [-2, 5] },
  { type: "festival", name: (r) => `${r.name} 가을 거리축제`, price: 0, tags: ["힙한", "산책"], summary: "거리 공연과 먹거리 부스가 열려요.", rating: 4.4, period: [-1, 8] },
  { type: "festival", name: () => "플리마켓 & 버스킹 위크", price: 0, tags: ["힙한"], summary: "주말마다 열리는 플리마켓과 버스킹.", rating: 4.2, period: [0, 3] },
  { type: "festival", name: () => "야시장 페스타", price: 0, tags: ["시끄러운", "힙한"], summary: "해가 지면 열리는 먹거리 야시장이에요.", rating: 4.3, period: [6, 16] },
  { type: "culture", name: () => "독립서점 & 갤러리", price: 0, tags: ["조용한", "아늑한"], summary: "책 구경하다 작은 전시까지 볼 수 있어요.", rating: 4.6 },
  { type: "culture", name: () => "복합문화공간 창고", price: 3000, tags: ["힙한", "실내"], summary: "옛 창고를 고쳐 만든 문화공간이에요.", rating: 4.4 },
  { type: "culture", name: () => "소극장 낮공연", price: 12000, tags: ["실내", "체험"], summary: "평일 낮에는 할인된 가격으로 볼 수 있어요.", rating: 4.5 },
];

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
  return (h >>> 0) / 4294967295;
}

export function day(offset: number): string {
  return new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10);
}

function scatter(region: Region, id: string): { lat: number; lng: number } {
  const angle = hash(id) * Math.PI * 2;
  const radius = (0.2 + hash(`${id}r`) * 0.7) * region.radius_m;
  return {
    lat: Number((region.center.lat + (Math.sin(angle) * radius) / 111_320).toFixed(6)),
    lng: Number(
      (region.center.lng + (Math.cos(angle) * radius) / (111_320 * Math.cos((region.center.lat * Math.PI) / 180))).toFixed(6),
    ),
  };
}

export function buildAttractions(): Attraction[] {
  return regions.flatMap((region) =>
    SEEDS.map((seed, i) => {
      const id = `a_${region.slug}_${i}`;
      return {
        id,
        type: seed.type,
        name: seed.name(region),
        region: { slug: region.slug, name: region.name },
        ...scatter(region, id),
        address: `${region.parent?.name ?? ""} ${region.name} ${Math.round(hash(`${id}a`) * 70) + 1}길 ${Math.round(hash(`${id}b`) * 30) + 1}`.trim(),
        thumbnail_url: null,
        is_free: seed.price === 0,
        price_per_person: seed.price,
        period: seed.period ? { starts_on: day(seed.period[0]), ends_on: day(seed.period[1]) } : null,
        tags: seed.tags,
        summary: seed.summary,
        rating: seed.rating,
      } satisfies Attraction;
    }),
  );
}

export function buildEvents(): EventItem[] {
  const seeds: { title: (r: Region) => string; type: EventItem["type"]; venue: string; range: [number, number]; price: number | null }[] = [
    { title: (r) => `${r.name} 가을 거리축제`, type: "festival", venue: "메인 거리 일대", range: [-1, 8], price: null },
    { title: () => "플리마켓 & 버스킹 위크", type: "market", venue: "공원 앞 광장", range: [0, 3], price: null },
    { title: () => "미디어아트 특별전", type: "exhibition", venue: "미디어아트 뮤지엄", range: [-20, 21], price: 15000 },
    { title: () => "인디밴드 주말 공연", type: "performance", venue: "라이브홀 온", range: [4, 5], price: 20000 },
    { title: () => "야시장 페스타", type: "festival", venue: "공영주차장 특설무대", range: [6, 16], price: null },
  ];
  return regions.flatMap((region) =>
    seeds.map((seed, i) => ({
      id: `e_${region.slug}_${i + 1}`,
      title: seed.title(region),
      type: seed.type,
      region: { slug: region.slug, name: region.name },
      venue: seed.venue,
      starts_on: day(seed.range[0]),
      ends_on: day(seed.range[1]),
      is_free: seed.price === null,
      price: seed.price,
      thumbnail_url: null,
      link_url: null,
    })),
  );
}
