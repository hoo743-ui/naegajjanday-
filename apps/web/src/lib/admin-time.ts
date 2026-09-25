/** 관리자 표의 시각: "25. 9. 25. 오후 10:11" 식의 짧은 한국 시각 */
export function adminTime(iso: string | null | undefined): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("ko-KR", { year: "2-digit", month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
