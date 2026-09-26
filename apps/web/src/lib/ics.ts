/**
 * 캘린더에 넣기: 코스의 장소마다 일정 하나(.ics). 브라우저에서 만들어 내려받는다 — 서버 · 계정 연동 없음.
 * 구글 · 애플 · 삼성 캘린더가 모두 이 형식을 읽는다 (RFC 5545).
 */
export interface IcsStop {
  name: string;
  start: string;
  end: string;
  address?: string;
  note?: string;
  url?: string;
}

const stamp = (iso: string) => new Date(iso).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");
/** 쉼표 · 세미콜론 · 줄바꿈은 이스케이프 (RFC 5545 §3.3.11) */
const text = (s: string) => s.replace(/\\/g, "\\\\").replace(/([,;])/g, "\\$1").replace(/\r?\n/g, "\\n");
/** 한 줄은 75 옥텟을 넘지 않게 접는다 — 한글은 글자당 3바이트라 넉넉히 24자씩 (이스케이프를 가르지 않게) */
function fold(line: string): string {
  const out: string[] = [];
  let i = 0;
  while (i < line.length) {
    let end = Math.min(i + 24, line.length);
    if (line[end - 1] === "\\" && end < line.length) end += 1;
    out.push(line.slice(i, end));
    i = end;
  }
  return out.join("\r\n ");
}

export function courseIcs(courseId: string, title: string, stops: IcsStop[]): string {
  const now = stamp(new Date().toISOString());
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//naegajjanday//course//KO", "CALSCALE:GREGORIAN", "METHOD:PUBLISH", `X-WR-CALNAME:${text(title)}`];
  stops.forEach((s, i) => {
    lines.push(
      "BEGIN:VEVENT",
      `UID:${courseId}-${i + 1}@naegajjanday`,
      `DTSTAMP:${now}`,
      `DTSTART:${stamp(s.start)}`,
      `DTEND:${stamp(s.end)}`,
      `SUMMARY:${text(`${i + 1}. ${s.name}`)}`,
      ...(s.address ? [`LOCATION:${text(s.address)}`] : []),
      ...(s.note ? [`DESCRIPTION:${text(s.note)}`] : []),
      ...(s.url ? [`URL:${s.url}`] : []),
      "END:VEVENT",
    );
  });
  lines.push("END:VCALENDAR");
  return lines.map(fold).join("\r\n") + "\r\n";
}

/** 파일로 내려받는다 (휴대폰은 캘린더 앱으로 바로 열린다) */
export function downloadIcs(filename: string, body: string): void {
  const url = URL.createObjectURL(new Blob([body], { type: "text/calendar;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
