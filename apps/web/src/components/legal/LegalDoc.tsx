import type { ReactNode } from "react";
import Link from "next/link";
import { PageShell } from "@/components/layout/PageShell";
import { LEGAL_READY, OPERATOR, field } from "@/lib/legal";

export interface LegalSection {
  title: string;
  body: ReactNode;
}

/** 약관·개인정보처리방침 공통 틀: 읽기 좋은 폭, 번호 매긴 조항, 시행일, 초안 안내. */
export function LegalDoc({ title, lead, sections, other }: { title: string; lead: ReactNode; sections: LegalSection[]; other: { href: string; label: string } }) {
  return (
    <PageShell className="wrap-narrow section-y">
      <article className="mx-auto max-w-[760px]">
        {LEGAL_READY ? null : (
          <p role="note" className="mb-8 rounded-2xl bg-paper-2 text-ink-2 px-5 py-4 text-sm font-bold">
            이 문서는 <b className="font-extrabold">초안</b>이에요. 사업자 정보가 아직 채워지지 않았고 법률 검토 전이라, 정식 공개 전에 내용이 바뀔 수 있어요.
          </p>
        )}
        <h1 className="text-[clamp(28px,4vw,40px)] font-extrabold">{title}</h1>
        <p className="tabular mt-3 text-sm font-bold text-muted-foreground">시행일 {field(OPERATOR.effectiveDate)}</p>
        <div className="mt-6 text-[15.5px] leading-[1.85] text-ink-2">{lead}</div>

        <ol className="mt-10 grid gap-9">
          {sections.map((section, i) => (
            <li key={section.title}>
              <h2 className="text-[19px] font-extrabold text-ink">
                제{i + 1}조 {section.title}
              </h2>
              <div className="mt-3 grid gap-2.5 text-[15.5px] leading-[1.85] text-ink-2 [&_li]:ml-5 [&_li]:list-disc [&_table]:w-full [&_td]:border-b [&_td]:py-2.5 [&_td]:pr-3 [&_td]:align-top [&_th]:border-b-2 [&_th]:py-2 [&_th]:pr-3 [&_th]:text-left [&_th]:text-[13px] [&_th]:font-extrabold [&_th]:text-muted-foreground">
                {section.body}
              </div>
            </li>
          ))}
        </ol>

        <p className="mt-12 border-t pt-6 text-sm text-muted-foreground">
          함께 읽어 보세요:{" "}
          <Link href={other.href} className="font-extrabold text-blue-deep underline-offset-4 hover:underline">
            {other.label}
          </Link>
        </p>
      </article>
    </PageShell>
  );
}
