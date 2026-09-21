/**
 * 약관·개인정보처리방침에 들어가는 사업자 정보. **출시 전에 이 파일만 채우면 된다.**
 * 하나라도 비어 있으면 두 문서 위에 "초안" 안내가 뜬다 — 빈 칸이 있는 법적 문서가 조용히 공개되는 일을 막는다.
 * 본문은 이 서비스가 실제로 하는 일(코드 기준)을 옮겨 쓴 초안이다. 법률 검토를 받은 문서가 아니다.
 */
export const OPERATOR = {
  /** 상호 또는 법인명 */
  name: "",
  /** 대표자 */
  representative: "",
  /** 사업자등록번호 */
  businessNumber: "",
  /** 주소 */
  address: "",
  /** 고객 문의 · 개인정보 문의 이메일 */
  email: "",
  /** 개인정보 보호책임자 (성명 · 직책) */
  privacyOfficer: "",
  /** 시행일 YYYY-MM-DD */
  effectiveDate: "",
} as const;

export const LEGAL_READY = Object.values(OPERATOR).every((v) => v.trim().length > 0);

/** 빈 값은 "[미정]" 으로 보여 준다 — 빈 칸이 자연스러운 문장처럼 읽히면 안 된다 */
export const field = (value: string) => (value.trim() ? value : "[미정]");

/** 보관 기간 — API 설정과 같은 값이어야 한다 (unsaved course TTL · account purge grace) */
export const RETENTION = { unsavedCourseHours: 24, deletedAccountDays: 30 } as const;
