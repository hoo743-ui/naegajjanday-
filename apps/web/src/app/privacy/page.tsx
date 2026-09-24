import type { Metadata } from "next";
import { LegalDoc, type LegalSection } from "@/components/legal/LegalDoc";
import { OPERATOR, RETENTION, field } from "@/lib/legal";
import { Wordmark } from "@/components/brand/Wordmark";

export const metadata: Metadata = { title: "개인정보처리방침", description: "내가짠데이가 어떤 정보를 왜 모으고, 언제 지우는지 알려 드려요." };

/**
 * 본문은 이 서비스가 실제로 하는 일을 코드 기준으로 옮긴 것이다. 기능이 바뀌면 여기도 바꾼다:
 *  - 수집 항목: OAuth(apps/api auth) · 취향(me/preferences) · 저장 코스 · 접속 IP(rate limit)
 *  - 브라우저가 직접 요청하는 외부 자원: 지도 타일 · 보행 경로 · 사진 (아래 "외부 서비스" 표)
 *  - 보관 기간: lib/legal.ts 의 RETENTION (API 설정과 같아야 한다)
 */
const sections: LegalSection[] = [
  {
    title: "수집하는 정보와 이유",
    body: (
      <>
        <p>가입하지 않아도 코스를 짤 수 있어요. 로그인은 코스를 저장하고 취향을 기억할 때만 필요해요.</p>
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>언제</th>
                <th>무엇을</th>
                <th>왜</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>코스를 짤 때 (비회원 포함)</td>
                <td>고른 지역 또는 출발 지점, 약속 종류, 인원, 예산, 시간, 취향 태그</td>
                <td>예산 안에서 코스를 만들기 위해</td>
              </tr>
              <tr>
                <td>소셜 로그인할 때</td>
                <td>로그인 제공자(카카오 · 네이버 · 구글)가 알려 주는 식별자, 이메일, 닉네임</td>
                <td>계정을 구분하고 저장한 코스를 본인에게만 보여 주기 위해</td>
              </tr>
              <tr>
                <td>로그인 상태로 이용할 때</td>
                <td>저장한 코스, 저장한 취향(좋아요 · 피할래요 태그, 이동 수단), 직접 남긴 피드백</td>
                <td>내 코스 목록과 다음 추천에 반영하기 위해</td>
              </tr>
              <tr>
                <td>서비스에 접속할 때</td>
                <td>접속 IP, 요청 시각, 브라우저 정보</td>
                <td>과도한 요청을 막고(이용 한도) 장애를 확인하기 위해</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>주민등록번호 · 결제 정보 · 연락처 · 정밀한 실시간 위치는 수집하지 않아요. 출발 지점은 직접 고른 동네나 역의 좌표예요.</p>
      </>
    ),
  },
  {
    title: "보관 기간과 파기",
    body: (
      <ul>
        <li>
          저장하지 않은 코스: 만든 뒤 <b>{RETENTION.unsavedCourseHours}시간</b>이 지나면 지워요.
        </li>
        <li>저장한 코스 · 취향: 직접 지우거나 탈퇴할 때까지 보관해요.</li>
        <li>
          탈퇴: 즉시 로그인이 막히고, <b>{RETENTION.deletedAccountDays}일</b> 뒤 계정과 연결된 개인정보를 복구할 수 없게 지워요. 그 사이에 다시 로그인해도 복구되지 않아요.
        </li>
        <li>접속 기록: 장애 · 부정 이용 확인에 필요한 기간만 보관한 뒤 지워요.</li>
        <li>누가 만들었는지 알 수 없게 된 통계(예: 지역별 코스 생성 수)는 서비스 개선을 위해 남길 수 있어요.</li>
      </ul>
    ),
  },
  {
    title: "쿠키와 브라우저 저장소",
    body: (
      <ul>
        <li>로그인 유지용 쿠키 1개(자바스크립트로 읽을 수 없는 HttpOnly 쿠키). 로그아웃하면 지워져요.</li>
        <li>광고 · 추적 목적의 쿠키는 쓰지 않아요.</li>
        <li>이용 통계 도구를 쓰게 되면 어떤 도구인지, 무엇을 보내는지 이 문서에 먼저 적을게요.</li>
      </ul>
    ),
  },
  {
    title: "화면을 그리기 위해 브라우저가 직접 연결하는 외부 서비스",
    body: (
      <>
        <p>아래 서비스에는 우리가 개인정보를 보내지 않아요. 다만 브라우저가 직접 자료를 받아 오기 때문에 그 서비스에 접속 IP가 남을 수 있어요.</p>
        <div className="overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>서비스</th>
                <th>받아 오는 것</th>
                <th>전달되는 정보</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>OpenStreetMap (또는 카카오맵)</td>
                <td>지도 타일</td>
                <td>보고 있는 지도의 위치</td>
              </tr>
              <tr>
                <td>한국관광공사</td>
                <td>장소 · 축제 사진</td>
                <td>사진 주소</td>
              </tr>
              <tr>
                <td>Wikimedia Commons</td>
                <td>업종 예시 사진</td>
                <td>사진 주소</td>
              </tr>
              <tr>
                <td>카카오맵 · 네이버 검색 (링크)</td>
                <td>길찾기, 가게 사진 · 메뉴, 축제 일정</td>
                <td>직접 눌렀을 때만, 장소 이름과 좌표</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>걷는 경로는 우리 서버가 코스에 들어간 장소들의 좌표만으로 계산해요. 이용자를 알아볼 수 있는 정보는 함께 보내지 않아요.</p>
      </>
    ),
  },
  {
    title: "제3자 제공과 처리 위탁",
    body: (
      <ul>
        <li>개인정보를 다른 회사에 팔거나 넘기지 않아요. 법령에 따른 요청이 있을 때만 예외예요.</li>
        <li>서버 · 데이터베이스 운영을 클라우드 사업자에게 맡기게 되면 업체 이름과 맡기는 일을 여기에 적을게요.</li>
        <li>장소 정보는 공공데이터(소상공인시장진흥공단 · 행정안전부 · 한국관광공사 등)에서 온 것이고, 이용자 정보와 섞지 않아요.</li>
      </ul>
    ),
  },
  {
    title: "이용자의 권리",
    body: (
      <ul>
        <li>내 코스 · 취향은 &lsquo;내 코스&rsquo; 화면에서 언제든 보고, 고치고, 지울 수 있어요.</li>
        <li>탈퇴는 &lsquo;내 코스&rsquo; 화면 아래에서 바로 할 수 있어요.</li>
        <li>열람 · 정정 · 삭제 · 처리 정지를 요청하려면 아래 연락처로 알려 주세요. 본인 확인 뒤 지체 없이 처리할게요.</li>
        <li>만 14세 미만은 법정대리인의 동의가 필요해요. 동의 없이 가입한 사실을 알게 되면 계정을 지워요.</li>
      </ul>
    ),
  },
  {
    title: "안전하게 지키기 위한 조치",
    body: (
      <ul>
        <li>모든 통신은 암호화(HTTPS)해요.</li>
        <li>비밀번호를 받지 않아요(소셜 로그인만). 로그인 토큰은 짧게 유지하고, 재사용이 감지되면 모두 무효로 만들어요.</li>
        <li>개인정보에 접근할 수 있는 사람을 최소로 두고, 관리자 작업은 기록을 남겨요.</li>
      </ul>
    ),
  },
  {
    title: "문의",
    body: (
      <ul>
        <li>운영자: {field(OPERATOR.name)} (대표 {field(OPERATOR.representative)})</li>
        <li>개인정보 보호책임자: {field(OPERATOR.privacyOfficer)}</li>
        <li>연락처: {field(OPERATOR.email)}</li>
        <li>개인정보 침해 상담: 개인정보침해신고센터(국번 없이 118), 개인정보분쟁조정위원회(1833-6972)</li>
        <li>이 문서가 바뀌면 시행 7일 전(중요한 변경은 30일 전)에 서비스 안에서 알릴게요.</li>
      </ul>
    ),
  },
];

export default function PrivacyPage() {
  return (
    <LegalDoc
      title="개인정보처리방침"
      lead={<p><Wordmark size="inline" />는 코스를 짜는 데 꼭 필요한 정보만 받아요. 무엇을 왜 받고 언제 지우는지, 어려운 말 없이 적었어요.</p>}
      sections={sections}
      other={{ href: "/terms", label: "이용약관" }}
    />
  );
}
