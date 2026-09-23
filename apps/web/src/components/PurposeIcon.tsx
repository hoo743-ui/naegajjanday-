import { GraduationCap, Heart, House, Luggage, PartyPopper, Sparkles, User, Users, Utensils, type LucideIcon } from "lucide-react";

/**
 * API 의 purpose.icon(키 문자열) → 아이콘. 목록 자체는 API 에서 오고, 여기는 "그림 사전"일 뿐이다.
 * 모르는 키가 오면 기본 아이콘으로 떨어지므로 새 목적이 추가돼도 코드 수정 없이 동작한다.
 */
const ICONS: Record<string, LucideIcon> = {
  heart: Heart,
  luggage: Luggage,
  // DB 시드가 쓰는 이름 (travel = suitcase, solo = user)
  suitcase: Luggage,
  user: User,
  home: House,
  users: Users,
  utensils: Utensils,
  // docs/34: 대학교를 고른 하루의 목적
  "graduation-cap": GraduationCap,
  "party-popper": PartyPopper,
};

export function PurposeIcon({ icon, className }: { icon: string; className?: string }) {
  const Icon = ICONS[icon];
  if (Icon) return <Icon className={className} aria-hidden />;
  // 아이콘 키가 아니라 이모지 등 짧은 문자가 오면 그대로 보여준다
  if (icon && icon.length <= 4 && !/^[a-z_-]+$/i.test(icon)) {
    return (
      <span className={className} aria-hidden>
        {icon}
      </span>
    );
  }
  return <Sparkles className={className} aria-hidden />;
}
