"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  CalendarDays,
  Image as ImageIcon,
  Landmark,
  LayoutDashboard,
  LogOut,
  Map as MapIcon,
  MapPin,
  Menu,
  Settings2,
  Database,
  Contact,
  ScrollText,
  Route,
  Users,
  type LucideIcon,
} from "lucide-react";
import { EmptyState } from "@/components/mascot/EmptyState";
import { Jjani } from "@/components/mascot/Jjani";
import { JjaniLoader } from "@/components/mascot/JjaniLoader";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useAuth } from "@/lib/auth/AuthProvider";
import { cn } from "@/lib/utils";
import { Wordmark } from "@/components/brand/Wordmark";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

const NAV: { title: string; items: NavItem[] }[] = [
  { title: "현황", items: [{ href: "/admin", label: "대시보드", icon: LayoutDashboard }] },
  {
    title: "콘텐츠",
    items: [
      { href: "/admin/places", label: "장소 승인 · 수정", icon: MapPin },
      { href: "/admin/attractions", label: "관광지 추가", icon: Landmark },
      { href: "/admin/events", label: "이벤트", icon: CalendarDays },
      { href: "/admin/banners", label: "배너", icon: ImageIcon },
    ],
  },
  {
    title: "운영",
    items: [
      { href: "/admin/regions", label: "지역 관리", icon: MapIcon },
      { href: "/admin/scoring", label: "추천 설정", icon: Settings2 },
      { href: "/admin/database", label: "설정 · DB", icon: Database },
    ],
  },
  {
    title: "분석",
    items: [
      { href: "/admin/users", label: "사용자 분석", icon: Users },
      { href: "/admin/members", label: "회원 목록", icon: Contact },
      { href: "/admin/visits", label: "방문 로그", icon: ScrollText },
      { href: "/admin/course-requests", label: "코스 요청", icon: Route },
      { href: "/admin/recommendations", label: "추천 결과 통계", icon: BarChart3 },
    ],
  },
];

function NavList({ pathname }: { pathname: string }) {
  return (
    <nav aria-label="관리자 메뉴" className="grid gap-5">
      {NAV.map((group) => (
        <div key={group.title}>
          <p className="mb-1.5 px-3 text-caption font-semibold tracking-wide text-muted-foreground">{group.title}</p>
          <ul className="grid gap-0.5">
            {group.items.map(({ href, label, icon: Icon }) => {
              const active = href === "/admin" ? pathname === href : pathname.startsWith(href);
              return (
                <li key={href}>
                  <Link
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-2.5 text-body font-bold transition-colors",
                      active ? "bg-blue-soft text-blue-deep" : "text-ink-2 hover:bg-soft",
                    )}
                  >
                    <Icon className="size-[18px]" aria-hidden />
                    {label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/admin" className="flex items-center gap-2 leading-none" aria-label="내가짠데이 관리자 홈">
      <Jjani mood="hi" size={32} animated={false} decorative />
      <Wordmark size="sm" />
      <span className="rounded-md bg-ink px-1.5 py-0.5 font-sans text-caption font-semibold tracking-wider text-white">ADMIN</span>
    </Link>
  );
}

export function AdminShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { status, me, isStaff, logout } = useAuth();
  const [open, setOpen] = useState(false);

  useEffect(() => setOpen(false), [pathname]);

  if (status === "loading") {
    return <JjaniLoader stages={["권한을 확인하는 중…"]} className="min-h-dvh" />;
  }

  if (status === "anonymous") {
    return (
      <main id="main" className="bg-hero grid min-h-dvh place-items-center">
        <EmptyState mood="hi" size="lg" title="관리자 로그인이 필요해요" description="운영자 계정으로 로그인하면 관리 화면이 열려요.">
          <Button asChild variant="brand" size="md">
            <Link href={`/login?next=${encodeURIComponent(pathname)}`}>로그인하기</Link>
          </Button>
          <Button asChild variant="soft" size="md">
            <Link href="/home">홈으로</Link>
          </Button>
        </EmptyState>
      </main>
    );
  }

  if (!isStaff) {
    return (
      <main id="main" className="bg-hero grid min-h-dvh place-items-center">
        <EmptyState
          mood="sorry"
          size="lg"
          title="여긴 들어올 수 없어요"
          description="이 화면은 운영자·관리자 권한이 있는 계정만 볼 수 있어요. 권한이 필요하면 팀에 요청해 주세요."
          footnote="오류 코드 FORBIDDEN"
        >
          <Button asChild variant="brand" size="md">
            <Link href="/home">홈으로</Link>
          </Button>
        </EmptyState>
      </main>
    );
  }

  const account = (
    <div className="flex items-center justify-between gap-2 rounded-2xl bg-soft px-3 py-2.5">
      <div className="min-w-0">
        <p className="truncate text-body-sm font-semibold text-ink">{me?.nickname}</p>
        <p className="text-caption font-semibold text-muted-foreground">{me?.role === "admin" ? "관리자" : "운영자"}</p>
      </div>
      <Button variant="ghost" size="icon-sm" aria-label="로그아웃" onClick={() => void logout()}>
        <LogOut aria-hidden />
      </Button>
    </div>
  );

  return (
    <div className="min-h-dvh bg-soft lg:grid lg:grid-cols-[260px_minmax(0,1fr)]">
      {/* 데스크톱 사이드바 */}
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 overflow-y-auto border-r bg-white px-4 py-5 lg:flex">
        <div className="px-2">
          <Brand />
        </div>
        <NavList pathname={pathname} />
        <div className="mt-auto grid gap-2">
          {account}
          <Link href="/home" className="px-3 text-caption font-semibold text-muted-foreground hover:text-ink">
            서비스 화면으로 돌아가기
          </Link>
        </div>
      </aside>

      <div className="min-w-0">
        {/* 모바일·태블릿 상단 바 */}
        <header className="sticky top-0 z-40 flex h-14 items-center justify-between gap-3 border-b bg-white/90 px-4 backdrop-blur lg:hidden">
          <Brand />
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" aria-label="관리자 메뉴 열기">
                <Menu aria-hidden />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-[280px] gap-5 overflow-y-auto px-4 py-5">
              <SheetHeader className="p-0 px-2">
                <SheetTitle className="text-h3 font-bold">관리자 메뉴</SheetTitle>
                <SheetDescription className="sr-only">관리자 화면 사이를 이동합니다</SheetDescription>
              </SheetHeader>
              <NavList pathname={pathname} />
              <div className="mt-auto">{account}</div>
            </SheetContent>
          </Sheet>
        </header>

        <main id="main" className="mx-auto w-full max-w-[1320px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  );
}

interface AdminPageHeaderProps {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}

export function AdminPageHeader({ title, description, actions }: AdminPageHeaderProps) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-h2 font-extrabold text-ink sm:text-h1">{title}</h1>
        {description ? <p className="mt-1 max-w-2xl text-body text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Panel({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-card border bg-white p-5 shadow-soft sm:p-6", className)}>
      {title || actions ? (
        <div className="mb-4 flex flex-wrap items-start justify-between gap-2">
          <div>
            {title ? <h2 className="text-body-lg font-extrabold text-ink">{title}</h2> : null}
            {description ? <p className="mt-0.5 text-body-sm text-muted-foreground">{description}</p> : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}
