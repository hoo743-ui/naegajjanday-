/** NEXT_PUBLIC_API_MOCKING=enabled 일 때만 화면 구석에 뜬다. 목 데이터를 실제로 착각하지 않게 하는 안전장치. */
export function MockBadge() {
  if (process.env.NEXT_PUBLIC_API_MOCKING !== "enabled") return null;
  return (
    <div
      role="note"
      aria-label="목 API 사용 중: 화면의 데이터는 개발용 가짜 데이터입니다"
      title="NEXT_PUBLIC_API_MOCKING=enabled — 화면의 장소·가격은 개발용 가짜 데이터입니다"
      className="pointer-events-none fixed bottom-3 left-3 z-[90] flex items-center gap-1.5 rounded-full bg-ink px-3 py-1.5 text-[11px] font-extrabold tracking-[.12em] text-gold shadow-card"
    >
      <span aria-hidden className="size-1.5 animate-pulse rounded-full bg-gold" />
      MOCK
    </div>
  );
}
