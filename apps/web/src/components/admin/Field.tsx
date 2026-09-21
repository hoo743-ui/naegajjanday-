import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface FieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

/** label + 입력 + 도움말/에러. 입력에는 id 와 aria-describedby={`${id}-desc`} 를 직접 달아 준다. */
export function Field({ id, label, hint, error, required, className, children }: FieldProps) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label htmlFor={id} className="text-sm font-extrabold text-ink-2">
        {label}
        {required ? (
          <span className="text-pink-deep" aria-hidden>
            *
          </span>
        ) : null}
      </Label>
      {children}
      {error ? (
        <p id={`${id}-desc`} role="alert" className="text-[13px] font-bold text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-desc`} className="text-[13px] text-muted-foreground">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** 네이티브 select — 모바일에서 OS 피커가 뜨고 react-hook-form register 와 바로 붙는다 */
export const nativeSelectClass =
  "h-9 w-full rounded-md border border-input bg-white px-3 text-sm text-ink shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:opacity-50";

export function FormMessage({ tone, children }: { tone: "success" | "error"; children: ReactNode }) {
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={cn(
        "rounded-xl px-3.5 py-2.5 text-sm font-bold",
        tone === "success" ? "bg-success-soft text-success" : "bg-pink-soft text-pink-deep",
      )}
    >
      {children}
    </p>
  );
}
