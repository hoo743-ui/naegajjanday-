/**
 * ⚠️ 개발용 목 데이터. NEXT_PUBLIC_API_MOCKING=enabled 일 때만 번들에서 실행된다.
 * 화면 컴포넌트는 이 파일을 절대 import 하지 않는다 — 오직 MSW 핸들러만 쓴다.
 */
import type { Banner, Category, Purpose, Region, Tag } from "@/lib/api/types";

export const regions: Region[] = [
  { slug: "seoul-hongdae", name: "홍대입구", level: 3, center: { lat: 37.5572, lng: 126.9245 }, radius_m: 1200, parent: { slug: "seoul-mapo", name: "마포구" }, place_count: 1284 },
  { slug: "seoul-seongsu", name: "성수", level: 3, center: { lat: 37.5446, lng: 127.0559 }, radius_m: 1300, parent: { slug: "seoul-seongdong", name: "성동구" }, place_count: 962 },
  { slug: "seoul-gangnam", name: "강남역", level: 3, center: { lat: 37.4979, lng: 127.0276 }, radius_m: 1100, parent: { slug: "seoul-gangnam-gu", name: "강남구" }, place_count: 1730 },
  { slug: "seoul-euljiro", name: "을지로", level: 3, center: { lat: 37.5662, lng: 126.9916 }, radius_m: 1000, parent: { slug: "seoul-jung", name: "중구" }, place_count: 744 },
  { slug: "seoul-jamsil", name: "잠실·석촌호수", level: 3, center: { lat: 37.5113, lng: 127.0982 }, radius_m: 1500, parent: { slug: "seoul-songpa", name: "송파구" }, place_count: 811 },
  { slug: "busan-jeonpo", name: "부산 전포", level: 3, center: { lat: 35.1553, lng: 129.0634 }, radius_m: 1200, parent: { slug: "busan-busanjin", name: "부산진구" }, place_count: 538 },
  { slug: "jeju-aewol", name: "제주 애월", level: 3, center: { lat: 33.4629, lng: 126.3106 }, radius_m: 4000, parent: { slug: "jeju-jeju", name: "제주시" }, place_count: 312 },
];

export const purposes: Purpose[] = [
  { code: "date", name: "데이트", icon: "heart", description: "분위기 좋은 곳 위주로, 걷는 거리는 짧게", budget_range: { min: 10000, max: 80000, typical: 25000 }, default_party_size: 2, max_party_size: 2 },
  { code: "travel", name: "여행", icon: "luggage", description: "관광지·축제까지 넣은 하루 코스", budget_range: { min: 15000, max: 120000, typical: 40000 }, default_party_size: 2, max_party_size: 8 },
  { code: "family", name: "가족모임", icon: "home", description: "편한 자리, 좋은 서비스, 단체석", budget_range: { min: 12000, max: 100000, typical: 30000 }, default_party_size: 4, max_party_size: 10 },
  { code: "friends", name: "친구모임", icon: "users", description: "밥 먹고 2차까지 동선 맞춰서", budget_range: { min: 10000, max: 80000, typical: 28000 }, default_party_size: 4, max_party_size: 10 },
  { code: "solo", name: "혼밥", icon: "utensils", description: "웨이팅 없고 혼자 가기 편한 곳", budget_range: { min: 6000, max: 50000, typical: 15000 }, default_party_size: 1, max_party_size: 1 },
];

export const tags: Tag[] = [
  { code: "quiet", name: "조용한", group: "mood", group_name: "분위기" },
  { code: "view", name: "뷰맛집", group: "mood", group_name: "분위기" },
  { code: "cozy", name: "아늑한", group: "mood", group_name: "분위기" },
  { code: "hip", name: "힙한", group: "mood", group_name: "분위기" },
  { code: "photo", name: "사진 잘 나오는", group: "mood", group_name: "분위기" },
  { code: "value", name: "가성비", group: "food", group_name: "음식" },
  { code: "korean", name: "한식", group: "food", group_name: "음식" },
  { code: "japanese", name: "일식", group: "food", group_name: "음식" },
  { code: "western", name: "양식", group: "food", group_name: "음식" },
  { code: "dessert", name: "디저트", group: "food", group_name: "음식" },
  { code: "vegan", name: "비건 옵션", group: "food", group_name: "음식" },
  { code: "indoor", name: "실내", group: "activity", group_name: "활동" },
  { code: "walk", name: "산책", group: "activity", group_name: "활동" },
  { code: "exhibition", name: "전시", group: "activity", group_name: "활동" },
  { code: "handson", name: "체험", group: "activity", group_name: "활동" },
  { code: "waiting", name: "웨이팅", group: "avoid", group_name: "피하고 싶어요" },
  { code: "noisy", name: "시끄러운", group: "avoid", group_name: "피하고 싶어요" },
  { code: "stairs", name: "계단 많은", group: "avoid", group_name: "피하고 싶어요" },
];

export const categories: Category[] = [
  { code: "food", name: "음식점", course_role: "MEAL", children: [
    { code: "food.korean", name: "한식", course_role: "MEAL" },
    { code: "food.japanese", name: "일식", course_role: "MEAL" },
    { code: "food.western", name: "양식", course_role: "MEAL" },
    { code: "food.snack", name: "분식", course_role: "MEAL" },
  ] },
  { code: "cafe", name: "카페", course_role: "CAFE", children: [
    { code: "cafe.coffee", name: "커피", course_role: "CAFE" },
    { code: "cafe.dessert", name: "디저트", course_role: "CAFE" },
  ] },
  { code: "play", name: "놀거리", course_role: "ATTRACTION", children: [
    { code: "play.park", name: "공원·산책", course_role: "ATTRACTION" },
    { code: "play.game", name: "오락·포토", course_role: "ATTRACTION" },
    { code: "play.class", name: "원데이 클래스", course_role: "ACTIVITY" },
  ] },
  { code: "culture", name: "문화", course_role: "CULTURE", children: [
    { code: "culture.exhibition", name: "전시", course_role: "CULTURE" },
    { code: "culture.space", name: "문화공간", course_role: "CULTURE" },
  ] },
  { code: "bar", name: "술집", course_role: "BAR" },
];

export const banners: Banner[] = [
  { id: "b_autumn", title: "가을 축제 모아보기", subtitle: "이번 주말, 무료로 즐기는 동네 축제", image_url: null, link_url: "/explore?type=festival", placement: "home" },
  { id: "b_chat", title: "말로 하면 짠이가 짜줘요", subtitle: "“성수에서 3만원으로 혼밥하고 전시 볼래”", image_url: null, link_url: "/chat", placement: "home" },
];
