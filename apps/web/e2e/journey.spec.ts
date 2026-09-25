import { createCourse, expect, expectHealthyLayout, firstPopulatedRegion, hasNationwideData, test } from "./fixtures";

test.describe("핵심 여정 (실제 API)", () => {
  test("홈: 두 갈래 · 빠른 코스 만들기가 실제 데이터로 뜨고, 소개에 목적 카드가 있고, CTA 가 위저드로 간다", async ({ page }) => {
    // 홈페이지 주소(/)는 인트로다 — 서비스 홈은 /home (2026-09-24)
    await page.goto("/home");
    await expect(page.getByRole("heading", { level: 1 })).toContainText("오늘 어떤 하루를");
    // 첫 화면의 핵심은 둘: 예산부터 짜기 · 갈 곳부터 둘러보기
    const paths = page.getByRole("navigation", { name: "시작하는 두 갈래" });
    await expect(paths.getByRole("link")).toHaveCount(2);
    // 빠른 코스 만들기: 예산을 바꾸면 한 줄 요약(예시 금액 · 남는 돈)이 바뀌고, 예산을 넘지 않는다
    const quick = page.getByRole("region", { name: "빠른 코스 만들기" });
    const summary = quick.getByText(/남아요/);
    const before = await summary.innerText();
    await quick.getByRole("button", { name: /10만 원/ }).click();
    await expect.poll(async () => summary.innerText()).not.toBe(before);
    // 증거 숫자는 API(/meta/regions)에서 온 실제 값이다
    await expect(quick.getByText(/전국 실제 장소/)).toBeVisible();
    // 채팅을 쓸 수 없는 환경이면 메뉴에 올리지 않는다
    const features = await (await page.request.get(`${process.env.E2E_API_URL ?? "http://localhost:8000/v1"}/meta/features`)).json();
    if (features.chat === false) await expect(page.getByRole("banner").getByRole("link", { name: "짠이와 대화" })).toHaveCount(0);
    // 목적 카드는 소개(/about)로 옮겼다. GET /meta/purposes 에서 온다 — 계약이 어긋나면 여기서 에러 바운더리가 뜬다
    await page.goto("/about");
    await page.locator("#purposes").scrollIntoViewIfNeeded();
    await expect(page.locator("#purposes").getByText("데이트").first()).toBeVisible();
    await expectHealthyLayout(page);

    await page.goto("/home");
    await page.getByRole("link", { name: /이 조건으로 코스 짜기/ }).click();
    await expect(page).toHaveURL(/\/plan/);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("어디서");
  });

  test("위저드 4단계 → 코스 생성 → 결과 화면", async ({ page }) => {
    const region = await firstPopulatedRegion(page);
    await page.goto("/plan");

    // 지역은 시도 → 시군구로 들어가며 고르거나 검색한다. 검색 결과는 radio 로 뜬다.
    await page.getByRole("searchbox").fill(region.name);
    await page.getByRole("radio", { name: new RegExp(region.name) }).first().click();
    await page.getByRole("button", { name: "다음" }).click();

    await expect(page.getByRole("heading", { level: 1 })).toContainText("어떤 약속");
    // 목적 선택지는 시각적으로 숨긴 radio + 라벨 카드다 → 사용자가 누르는 라벨 글자를 누른다.
    // 목적을 고르면 위저드가 스스로 다음 단계로 넘어가므로, 제목을 보고 필요할 때만 "다음"을 누른다.
    const heading = page.getByRole("heading", { level: 1 });
    const goTo = async (title: string) => {
      const arrived = await heading.filter({ hasText: title }).waitFor({ timeout: 2500 }).then(() => true, () => false);
      if (!arrived) await page.getByRole("button", { name: "다음", exact: true }).click();
      await expect(heading).toContainText(title);
    };
    await page.getByText("데이트", { exact: true }).first().click();
    await goTo("몇 명");
    // 기본 예산은 1인당 범위 × 인원이다. API 의 총액을 1인당으로 읽어 데이트 2인이 15만원으로 잡히던 회귀를 막는다.
    await expect(page.getByRole("button", { name: /6만원\s*적당히|적당히\s*·?\s*6만원/ })).toHaveAttribute("aria-pressed", "true");
    // 만나는 시간: 내일 저녁 6시부터 3시간 → 요약 문구와 결과 화면 머리말에 그대로 나와야 한다
    const when = page.getByRole("region", { name: "언제 만나요?" });
    await when.getByRole("button", { name: "내일" }).click();
    await when.getByRole("button", { name: /저녁 18:00/ }).click();
    await when.getByRole("button", { name: /^3시간/ }).click();
    await expect(when.getByText(/18:00 ~ 21:00/)).toBeVisible();
    await expectHealthyLayout(page);
    await goTo("취향");
    // 짧은 질문 셋 (docs/30 · docs/32 B §10): 아무것도 안 골라도 되고, "특별한 경험"은 재미 우선 코스가 된다
    const special = page.getByRole("checkbox", { name: /특별한 경험/ });
    await expect(special).not.toBeChecked();
    await special.click();
    await expect(special).toBeChecked();
    await expect(page.getByRole("radio", { name: /적당히 이동/ })).toBeChecked();
    // 고른 것을 말로 되읽는다
    await expect(page.getByRole("heading", { name: "좋아요. 이렇게 이해했어요." })).toBeVisible();
    await expect(page.getByText("특별한 경험").last()).toBeVisible();
    // 세부 태그는 "더 자세히" 안에. 그룹명이 API 원시 코드(activity/feature/…)로 새지 않아야 한다
    await page.getByRole("button", { name: /더 자세히/ }).click();
    await expect(page.getByText("술 한잔 포함", { exact: true })).toBeVisible();
    await expect(page.getByRole("group", { name: /^(activity|feature|food|mood)$/ })).toHaveCount(0);
    await expectHealthyLayout(page);

    await page.getByRole("button", { name: /코스 짜 주세요/ }).click();
    await page.waitForURL(/\/course\/[0-9a-f-]{36}/, { timeout: 80_000 });
    await expect(page.getByLabel("코스 일정")).toBeVisible();
    // 3시간 창 → 머리말에 시간대가 뜨고, 들르는 곳은 3곳을 넘지 않는다
    await expect(page.getByText(/18:00 ~ 21:00/).first()).toBeVisible();
    expect(await page.getByLabel("코스 일정").getByRole("article").count()).toBeLessThanOrEqual(3);
    await expectHealthyLayout(page);
  });

  test("결과 화면: 조건·합계·지도·동선 안내가 서로 맞는다", async ({ page }) => {
    const id = await createCourse(page);
    await page.goto(`/course/${id}`);

    const stops = page.getByLabel("코스 일정").getByRole("article");
    await expect(stops.first()).toBeVisible();
    const count = await stops.count();
    expect(count).toBeGreaterThanOrEqual(2);

    await expect(page.getByText(/예산 80,000원/).first()).toBeVisible(); // 요청 조건 에코 (request.*)
    await expect(page.getByRole("tab").first()).toBeVisible(); // 대안 코스 탭 (siblings)

    // 지도: 카카오든 Leaflet 이든 같은 번호 핀을 쓴다 → 핀 수 = 스톱 수 (약도(SVG)로 떨어졌을 때만 건너뛴다)
    if (await page.locator(".jj-map").count()) {
      await expect(page.locator(".jj-pin")).toHaveCount(count);
    }
    // 장소마다 길찾기 버튼 하나 → "어디서 출발할까요?" 시트 → 네이버지도 열기 (docs/42)
    const second = page.getByLabel("코스 일정").getByRole("article").nth(1);
    await second.getByRole("button", { name: /길찾기$/ }).click();
    await expect(page.getByRole("dialog", { name: "어디서 출발할까요?" })).toBeVisible();
    await expect(page.getByRole("radio", { name: /이전 장소/ })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByRole("button", { name: /네이버지도 열기/ })).toBeVisible();
    await page.getByRole("button", { name: "닫기" }).click();
    // 코스 전체: 오늘의 이동 · 전체 코스 보기 · 네이버 지도에서 길찾기
    await expect(page.getByRole("heading", { name: "오늘의 이동" })).toBeVisible();
    const route = page.getByRole("button", { name: /오늘의 이동/ });
    if ((await route.getAttribute("aria-expanded")) !== "true") await route.click();
    await expect(page.getByRole("link", { name: /네이버 지도에서 길찾기/ })).toHaveAttribute("href", /^https:\/\/map\.naver\.com\/p\/directions\//);
    await expectHealthyLayout(page);
  });

  test("결과 화면: 합계가 예산을 넘지 않고 스톱 금액의 합과 같다", async ({ page }) => {
    const id = await createCourse(page);
    const res = await page.request.get(`${process.env.E2E_API_URL ?? "http://localhost:8000/v1"}/courses/${id}`);
    const { course, request } = (await res.json()) as {
      course: { totals: { price: number; budget_left: number }; stops: { est_price: number }[] };
      request: { budget_total: number };
    };
    const sum = course.stops.reduce((acc, s) => acc + s.est_price, 0);
    expect(course.totals.price).toBe(sum);
    expect(course.totals.price).toBeLessThanOrEqual(request.budget_total);
    expect(course.totals.budget_left).toBe(request.budget_total - sum);
  });

  test("코스 스타일: '재미 우선'은 놀거리를 넣고, 체인 카페를 빼고, 화면에 표시된다", async ({ page }) => {
    test.skip(!(await hasNationwideData(page)), "시드 DB 의 홍대 40곳에는 공원을 대신할 놀거리가 모자란다 — 전국 DB 에서만 본다");
    const evening = (() => {
      const d = new Date();
      d.setDate(d.getDate() + 1);
      return `${d.toISOString().slice(0, 10)}T18:00:00+09:00`;
    })();
    const id = await createCourse(page, { style: "fun", start_at: evening, budget_total: 80_000 });
    const res = await page.request.get(`${process.env.E2E_API_URL ?? "http://localhost:8000/v1"}/courses/${id}`);
    const { course, request } = (await res.json()) as {
      course: { stops: { role: string; place: { name: string }; score_breakdown: Record<string, number> }[] };
      request: { style: string };
    };
    expect(request.style).toBe("fun");
    const roles = course.stops.map((s) => s.role);
    expect(roles, "무료 공원 산책 대신 놀거리가 들어간다").toContain("ACTIVITY");
    expect(roles).not.toContain("ATTRACTION");
    const cafe = course.stops.find((s) => s.role === "CAFE");
    expect(cafe?.place.name ?? "").not.toMatch(/스타벅스|메가|컴포즈|빽다방|이디야|투썸/);
    expect(course.stops.every((s) => "buzz" in s.score_breakdown)).toBeTruthy();

    await page.goto(`/course/${id}`);
    await expect(page.getByText(/재미 우선/).first()).toBeVisible();
    await expectHealthyLayout(page);
  });

  test("1박 2일 · 두 동네: 날짜별 탭과 그날 밤 묵을 곳, 동네 사이 이동이 구간으로 나온다", async ({ page }) => {
    // 여행 일정은 같은 요청의 코스들을 "1일차 · 2일차" 탭으로 보여 준다. 예산은 날마다 나눠 쓴다.
    const id = await createCourse(page, { nights: 1, budget_total: 240_000, purposes: ["friends"] });
    await page.goto(`/course/${id}`);
    await expect(page.getByLabel("코스 일정").getByRole("article").first()).toBeVisible();
    await expect(page.getByRole("tab", { name: "1일차" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "2일차" })).toBeVisible();
    await expect(page.getByText(/1일차 \/ 2일/).first()).toBeVisible();
    await expect(page.getByText(/데이트 \+ 친구/).first()).toBeVisible(); // 고른 목적이 모두 보인다
    // 숙소: 관광공사 등재분이 근처에 없으면 카드는 아예 나오지 않는다(없는 것을 말하지 않는다) → 있으면 요금 고지를 확인한다
    const stay = page.getByRole("region", { name: /이 근처에서 묵는다면/ });
    if (await stay.count()) {
      await stay.getByText(/요금 안내/).click();
      await expect(stay.getByText(/숙박 요금은 공식 데이터가 없어요/)).toBeVisible();
    }
    await expectHealthyLayout(page);

    // 하루에 두 동네: 동네가 바뀌는 구간은 걷는 구간이 아니라 "○○(으)로 대중교통 N분"이다
    const res = await page.request.post(`${process.env.E2E_API_URL ?? "http://localhost:8000/v1"}/courses/generate`, {
      data: { regions: ["seoul-hongdae", "seoul-seongsu"], purpose: "friends", party_size: 3, budget_total: 150_000, duration_min: 420, start_at: `${new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)}T12:00:00+09:00` },
    });
    expect(res.ok()).toBeTruthy();
    const hop = (await res.json()) as { courses: { id: string; totals: { price: number } }[] };
    expect(hop.courses[0]!.totals.price).toBeLessThanOrEqual(150_000);
    await page.goto(`/course/${hop.courses[0]!.id}`);
    await expect(page.getByLabel("코스 일정").getByText(/\(으\)로 (대중교통|자동차|도보)/).first()).toBeVisible();
    await expectHealthyLayout(page);
  });

  test("지역 선택: 시도에서 시·군으로 들어가고, 행정구역이 아닌 동네는 역으로 찾는다", async ({ page }) => {
    test.skip(!(await hasNationwideData(page)), "시드 DB 에는 경기도 · 수원시 지역 나무가 없다 — 전국 DB 에서만 본다");
    await page.goto("/plan");
    // 처음에는 많이 찾는 동네뿐, 지역 나무는 "지역에서 직접 고르기" 뒤에 있다(docs/41) — 열면 시도만 보인다
    await page.getByRole("button", { name: /지역에서 직접 고르기/ }).click();
    await page.getByRole("button", { name: /경기도 안으로 들어가기/ }).click();
    await expect(page.getByRole("navigation", { name: "지역 단계" })).toContainText("경기도");
    await expect(page.getByRole("radio", { name: /경기도 전체/ })).toBeVisible();
    await expect(page.getByRole("button", { name: /수원시 안으로 들어가기/ })).toBeVisible(); // 구가 있는 시는 한 번 더 묶인다

    // "신도림"은 구로구 안의 동네라 지역 이름으로는 없다 → 지하철역으로 찾아 그 주변으로 짠다
    await page.getByRole("searchbox").fill("신도림");
    await expect(page.getByRole("radio", { name: /신도림역 주변/ })).toBeVisible();
    await expectHealthyLayout(page);
  });

  test("둘러보기: 전체 지역에서도 목록과 이벤트가 뜬다", async ({ page }) => {
    await page.goto("/explore");
    await expect(page.getByRole("heading", { name: "이번 주 이벤트" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "장소 목록" })).toBeVisible();
    await expect(page.getByText("VALIDATION_ERROR")).toHaveCount(0);
    await expectHealthyLayout(page);
  });

  test("둘러보기: 장소를 누르면 상세 시트가 열리고 지도·길찾기·검색으로 이어진다", async ({ page }) => {
    await page.goto("/explore");
    const opener = page.locator("article h3 button").first();
    await expect(opener).toBeVisible();
    const name = (await opener.textContent())?.trim() ?? "";
    await opener.click();

    const sheet = page.getByRole("dialog");
    await expect(sheet.getByRole("heading", { name })).toBeVisible();
    const links = sheet.getByRole("navigation", { name: "관련 페이지" }).getByRole("link");
    // 서버가 찾은 공식 링크(docs/44)든 검색 링크든: 그 장소의 지도 페이지 하나와 "여기까지 길찾기"는 늘 있다
    await expect(links.first()).toBeVisible();
    const hrefs = await links.evaluateAll((els) => els.map((a) => a.getAttribute("href") ?? ""));
    expect(hrefs.some((h) => /^https:\/\/(place\.map\.kakao\.com\/|map\.kakao\.com\/(link\/search\/|\?q=))/.test(h))).toBeTruthy();
    expect(hrefs.some((h) => /^https:\/\/map\.kakao\.com\/link\/to\/.+,\d+\.\d+,\d+\.\d+$/.test(h))).toBeTruthy();
    await expect(sheet.getByRole("link", { name: /이 근처로 코스 짜기/ })).toHaveAttribute("href", /^\/plan/);
    await expectHealthyLayout(page);

    await page.keyboard.press("Escape");
    await expect(sheet).toHaveCount(0);
  });
});

test.describe("페이지 스모크", () => {
  for (const path of ["/login", "/chat", "/my", "/plan", "/explore", "/terms", "/privacy"]) {
    test(`${path} 가 에러 없이 뜬다`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole("banner")).toBeVisible();
      await expectHealthyLayout(page);
    });
  }

  test("없는 코스는 404 안내를 보여 준다 (에러 화면이 아니라)", async ({ page }) => {
    await page.goto("/course/00000000-0000-4000-8000-000000000000");
    await expect(page.getByText("INTERNAL_ERROR")).toHaveCount(0);
  });
});
