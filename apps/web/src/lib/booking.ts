/**
 * 숙소 예약처로 바로 가는 링크 (docs/46). 날짜 · 인원을 채운 검색 주소 — 우리가 예약 · 결제를 하지 않는다.
 * 2026-09-24 브라우저로 확인한 형식만 쓴다:
 *   여기어때   keyword · checkIn · checkOut · personal → 날짜 · 인원이 채워지고 그 숙소가 맨 위
 *   Booking.com ss · checkin · checkout · group_adults · no_rooms → 그 숙소 1곳, 날짜 · 인원 채워짐
 *   야놀자(NOL) q → 그 숙소 검색 (날짜는 그쪽에서 고른다)
 *   아고다는 검색 주소를 무시하고 첫 화면으로 보내서 뺐다.
 */
export interface BookingLink {
  key: "yeogi" | "booking" | "yanolja";
  label: string;
  url: string;
  /** 날짜 · 인원까지 채워지는지 */
  dated: boolean;
}

function plusDays(ymd: string, days: number): string {
  const d = new Date(`${ymd}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** 코스의 시작 시각(ISO) → 그날 한국 날짜 "YYYY-MM-DD" */
export function kstDate(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(iso));
}

export function bookingLinks(name: string, checkin: string, adults: number, nights = 1): BookingLink[] {
  const out = plusDays(checkin, nights);
  const q = encodeURIComponent(name);
  const people = Math.max(1, Math.min(adults, 8));
  return [
    {
      key: "yeogi",
      label: "여기어때",
      url: `https://www.yeogi.com/domestic-accommodations?keyword=${q}&checkIn=${checkin}&checkOut=${out}&personal=${people}`,
      dated: true,
    },
    {
      key: "booking",
      label: "Booking.com",
      url: `https://www.booking.com/searchresults.ko.html?ss=${q}&checkin=${checkin}&checkout=${out}&group_adults=${people}&no_rooms=1&group_children=0`,
      dated: true,
    },
    {
      key: "yanolja",
      label: "야놀자",
      url: `https://nol.yanolja.com/discovery/list/search/PRODUCT_CATEGORY_KOREA_ACCOMMODATION?q=${q}`,
      dated: false,
    },
  ];
}
