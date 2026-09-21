import type { Metadata } from "next";
import { LegalDoc, type LegalSection } from "@/components/legal/LegalDoc";
import { OPERATOR, RETENTION, field } from "@/lib/legal";

export const metadata: Metadata = { title: "이용약관", description: "내가짠데이를 쓰실 때 서로 지키기로 한 약속이에요." };

/** 서비스가 실제로 하는 일에 맞춘 초안. 특히 제3조(가격은 추정일 수 있다)는 제품의 핵심 고지다 — 화면의 "(업종 평균가)" 표기와 짝을 이룬다. */
const sections: LegalSection[] = [
  {
    title: "서비스가 하는 일",
    body: (
      <p>
        내가짠데이는 지역 · 인원 · 예산 · 시간을 받아, 그 예산 안에서 갈 만한 식당 · 카페 · 놀거리 · 볼거리를 하루 코스로 이어서 보여 드리는 서비스예요. 예약 · 결제 · 티켓 판매는 하지 않아요.
      </p>
    ),
  },
  {
    title: "가입과 계정",
    body: (
      <ul>
        <li>가입하지 않아도 코스를 짤 수 있어요. 코스를 저장하거나 취향을 기억해 두려면 소셜 로그인이 필요해요.</li>
        <li>계정은 본인만 써 주세요. 다른 사람의 계정을 쓰거나 계정을 넘기면 안 돼요.</li>
        <li>언제든 &lsquo;내 코스&rsquo; 화면에서 탈퇴할 수 있어요. 탈퇴하면 {RETENTION.deletedAccountDays}일 뒤 계정 정보가 복구할 수 없게 지워져요.</li>
      </ul>
    ),
  },
  {
    title: "가격 · 영업 정보의 정확성",
    body: (
      <ul>
        <li>
          장소 정보는 공공데이터에서 가져와요. 대부분의 가격은 그 가게의 메뉴판 가격이 아니라 <b>같은 지역 · 같은 업종의 평균가로 계산한 추정치</b>예요. 화면에는 &lsquo;(업종 평균가)&rsquo;, 실제 조사된 가격에는 &lsquo;(메뉴판 가격)&rsquo;이라고 구분해 적어요.
        </li>
        <li>영업시간 · 휴무 · 폐업 여부는 실제와 다를 수 있어요. 특히 멀리 가시거나 시간이 빠듯하면, 출발 전에 지도 앱에서 한 번 더 확인해 주세요.</li>
        <li>실제로 쓴 돈이 화면의 합계와 달라도 그 차액을 보상하지는 않아요. 다만 틀린 정보를 알려 주시면 바로 고칠게요.</li>
        <li>사진에 &lsquo;예시 사진&rsquo;이라고 적힌 것은 그 장소의 사진이 아니라 같은 업종의 대표 사진이에요.</li>
      </ul>
    ),
  },
  {
    title: "코스의 저장과 공유",
    body: (
      <ul>
        <li>저장하지 않은 코스는 만든 뒤 {RETENTION.unsavedCourseHours}시간이 지나면 지워져요. 링크도 그때부터 열리지 않아요.</li>
        <li>코스 링크를 받은 사람은 코스를 볼 수 있어요. 링크에는 만든 사람의 이름이나 계정 정보가 들어가지 않아요.</li>
      </ul>
    ),
  },
  {
    title: "하지 말아 주세요",
    body: (
      <ul>
        <li>자동화된 수단으로 대량 요청을 보내거나, 장소 데이터를 긁어 가는 일</li>
        <li>서비스의 보안 · 이용 한도를 우회하려는 시도</li>
        <li>다른 사람을 사칭하거나 허위 정보를 제보하는 일</li>
      </ul>
    ),
  },
  {
    title: "콘텐츠의 권리",
    body: (
      <ul>
        <li>서비스의 화면 · 캐릭터(짠이) · 문구의 권리는 운영자에게 있어요.</li>
        <li>장소 정보와 사진은 각 출처의 이용 조건을 따라요: 공공데이터포털(공공누리), 한국관광공사 사진(출처 표시), OpenStreetMap(ODbL), Wikimedia Commons(각 사진의 라이선스).</li>
        <li>이용자가 남긴 제보 · 피드백은 서비스 개선과 장소 정보 수정에 쓸 수 있어요.</li>
      </ul>
    ),
  },
  {
    title: "서비스의 변경 · 중단과 책임",
    body: (
      <ul>
        <li>서비스는 무료로 제공되고, 기능이 바뀌거나 점검 · 장애로 잠시 멈출 수 있어요. 미리 알릴 수 있는 일은 미리 알릴게요.</li>
        <li>운영자의 고의나 중대한 과실이 아닌 이유로 생긴 손해(추천한 장소의 휴무 · 가격 차이 · 이동 중의 사고 등)는 책임지기 어려워요. 법이 달리 정한 경우에는 그에 따라요.</li>
        <li>약관이 바뀌면 시행 7일 전(이용자에게 불리한 변경은 30일 전)에 서비스 안에서 알려요. 바뀐 뒤에도 계속 쓰시면 동의한 것으로 봐요.</li>
      </ul>
    ),
  },
  {
    title: "운영자와 문의",
    body: (
      <ul>
        <li>
          {field(OPERATOR.name)} · 대표 {field(OPERATOR.representative)} · 사업자등록번호 {field(OPERATOR.businessNumber)}
        </li>
        <li>주소: {field(OPERATOR.address)}</li>
        <li>문의: {field(OPERATOR.email)}</li>
        <li>이 약관은 대한민국 법을 따르고, 분쟁은 민사소송법이 정한 법원에서 다뤄요.</li>
      </ul>
    ),
  },
];

export default function TermsPage() {
  return (
    <LegalDoc
      title="이용약관"
      lead={<p>어려운 말 대신, 서비스가 실제로 하는 일과 서로 지킬 약속을 적었어요.</p>}
      sections={sections}
      other={{ href: "/privacy", label: "개인정보처리방침" }}
    />
  );
}
