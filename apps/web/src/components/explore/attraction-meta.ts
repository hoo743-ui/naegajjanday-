import { Landmark, Palette, PartyPopper, Ticket, TreePine, type LucideIcon } from "lucide-react";
import type { AttractionType } from "@/lib/api/types";

/** API enum(AttractionType)의 화면 표기. 목록 데이터가 아니라 enum 번역이다. */
export const ATTRACTION_TYPE_META: Record<AttractionType, { label: string; icon: LucideIcon; gradient: string }> = {
  attraction: { label: "관광지", icon: Landmark, gradient: "from-[#DCE8FF] to-[#F4EEFF]" },
  park: { label: "공원", icon: TreePine, gradient: "from-[#D9F3E4] to-[#EAF2FF]" },
  exhibition: { label: "전시", icon: Palette, gradient: "from-[#F4EEFF] to-[#FFEAF3]" },
  festival: { label: "축제", icon: PartyPopper, gradient: "from-[#FFEAF3] to-[#FFF3D6]" },
  culture: { label: "문화공간", icon: Ticket, gradient: "from-[#FFF3D6] to-[#EAF2FF]" },
};

export const ATTRACTION_TYPES = Object.keys(ATTRACTION_TYPE_META) as AttractionType[];

export function isAttractionType(value: string | null | undefined): value is AttractionType {
  return !!value && value in ATTRACTION_TYPE_META;
}
