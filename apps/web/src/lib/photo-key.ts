/**
 * 같은 사진이면 같은 키 (API `domain.media.image_key` 와 같은 규칙, docs/29).
 * 관광공사 사진은 크기만 다른 사본(…_image2_1 · …_image3_1)이 따로 온다 → 번호가 같으면 한 장.
 */
const TOURAPI = /\/cms\/(resource\w*)\/\d+\/(\d+)_image\d+_\d+/i;

export function photoKey(url: string): string {
  const m = TOURAPI.exec(url);
  if (m) return `tourapi:${m[1]!.toLowerCase()}:${m[2]}`;
  try {
    const u = new URL(url);
    return `url:${u.host.toLowerCase()}${u.pathname}`;
  } catch {
    return `url:${url}`;
  }
}

/** 순서를 지키며 같은 사진을 한 번만 */
export function distinctPhotos(urls: readonly (string | null | undefined)[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const url of urls) {
    if (!url) continue;
    const key = photoKey(url);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(url);
  }
  return out;
}
