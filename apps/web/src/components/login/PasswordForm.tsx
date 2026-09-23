"use client";

import { useEffect, useId, useState, type FormEvent } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { track } from "@/lib/analytics";
import type { ApiError } from "@/lib/api/client";
import { passwordAuth } from "@/lib/auth/token";
import { cn } from "@/lib/utils";

type Mode = "login" | "signup";

/** API 와 같은 규칙 (apps/api 의 가입 검증과 짝): 먼저 화면에서 알려 주고, 최종 판단은 서버가 한다 */
const ID_RULE = /^[a-z0-9._-]{4,20}$/;
function idProblem(id: string): string | null {
  if (!id) return "아이디를 적어 주세요.";
  if (!ID_RULE.test(id)) return "아이디는 영문 소문자 · 숫자 · . _ - 로 4~20자예요.";
  return null;
}
function passwordProblem(pw: string): string | null {
  if (pw.length < 8 || pw.length > 72) return "비밀번호는 8~72자예요.";
  if (!/[A-Za-z]/.test(pw) || !/[0-9]/.test(pw)) return "비밀번호에 영문과 숫자를 하나 이상 넣어 주세요.";
  return null;
}

function serverMessage(mode: Mode, error: ApiError): string {
  if (error.code === "INVALID_CREDENTIALS") return "아이디 또는 비밀번호가 맞지 않아요.";
  if (error.code === "LOGIN_ID_TAKEN") return "이미 쓰고 있는 아이디예요. 다른 아이디를 골라 주세요.";
  if (error.code === "RATE_LIMITED") return "시도가 너무 많았어요. 잠시 뒤에 다시 해 주세요.";
  if (error.status === 403) return "이용이 정지된 계정이에요.";
  if (error.status === 0 || error.status >= 500) return "서버에 닿지 못했어요. 잠시 뒤에 다시 해 주세요.";
  return error.detail ?? (mode === "login" ? "로그인하지 못했어요. 다시 시도해 주세요." : "가입하지 못했어요. 다시 시도해 주세요.");
}

interface PasswordFormProps {
  /** 성공 뒤 이동은 부모(LoginCard)가 로그인 상태를 보고 한다 */
  onDone?: () => void;
}

/**
 * 아이디 · 비밀번호로 들어오기. 우리 DB 가 계정을 관리하고, 가입에 이메일 인증은 없다 —
 * 가입하는 순간 로그인된 상태가 되어 저장 · 내 코스 · 취향 기억을 바로 쓴다.
 */
export function PasswordForm({ onDone }: PasswordFormProps) {
  const [mode, setMode] = useState<Mode>("login");
  const [loginId, setLoginId] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const uid = useId();
  // 스크립트가 붙기 전에 누르면 브라우저가 폼을 그대로 보낸다(GET 이면 비밀번호가 주소창 · 기록에 남는다) →
  // 붙기 전에는 제출 버튼을 잠그고, 혹시 보내지더라도 method="post" 라 주소에는 실리지 않게 한다
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);

  const id = loginId.trim().toLowerCase();
  const signup = mode === "signup";
  const problems = {
    id: signup ? idProblem(id) : id ? null : "아이디를 적어 주세요.",
    password: signup ? passwordProblem(password) : password ? null : "비밀번호를 적어 주세요.",
    confirm: signup && confirm !== password ? "비밀번호가 서로 달라요." : null,
  };
  const valid = !problems.id && !problems.password && !problems.confirm;

  const switchMode = (next: Mode) => {
    setMode(next);
    setError(null);
    setTouched(false);
    setConfirm("");
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setTouched(true);
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    track("login_clicked", { provider: "password" });
    const result = await passwordAuth(mode, { login_id: id, password });
    setBusy(false);
    if (!result.ok) {
      setError(serverMessage(mode, result.error));
      return;
    }
    if (signup) track("signup_completed", { method: "password" });
    onDone?.();
  };

  const field = "h-12 w-full rounded-xl border border-line bg-white px-3.5 text-body text-ink outline-none placeholder:text-muted-foreground focus-visible:border-blue-deep focus-visible:ring-[3px] focus-visible:ring-blue-deep/20 aria-invalid:border-pink-deep";
  const hint = (text: string | null, key: string) =>
    touched && text ? (
      <p id={`${uid}-${key}`} className="mt-1 text-left text-caption font-semibold text-pink-deep">
        {text}
      </p>
    ) : null;

  return (
    <form method="post" onSubmit={(e) => void onSubmit(e)} noValidate className="grid gap-3 text-left">
      {/* 로그인 ↔ 가입: 같은 칸, 가입만 확인 칸이 하나 더 */}
      <div role="tablist" aria-label="로그인 또는 가입" className="grid grid-cols-2 rounded-xl bg-paper-2 p-1">
        {(["login", "signup"] as const).map((m) => (
          <button
            key={m}
            type="button"
            role="tab"
            aria-selected={mode === m}
            onClick={() => switchMode(m)}
            className={cn("h-10 rounded-lg text-body-sm font-semibold transition-colors", mode === m ? "bg-white text-ink shadow-soft" : "text-ink-2 hover:text-ink")}
          >
            {m === "login" ? "로그인" : "아이디 만들기"}
          </button>
        ))}
      </div>

      <div>
        <label htmlFor={`${uid}-id`} className="text-body-sm font-semibold text-ink-2">
          아이디
        </label>
        <input
          id={`${uid}-id`}
          name="username"
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          inputMode="email"
          value={loginId}
          onChange={(e) => setLoginId(e.target.value)}
          placeholder={signup ? "영문 소문자 · 숫자 4~20자" : "아이디"}
          aria-invalid={touched && Boolean(problems.id)}
          aria-describedby={touched && problems.id ? `${uid}-idp` : undefined}
          className={cn(field, "mt-1")}
        />
        {hint(problems.id, "idp")}
      </div>

      <div>
        <label htmlFor={`${uid}-pw`} className="text-body-sm font-semibold text-ink-2">
          비밀번호
        </label>
        <div className="relative mt-1">
          <input
            id={`${uid}-pw`}
            name="password"
            type={show ? "text" : "password"}
            autoComplete={signup ? "new-password" : "current-password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={signup ? "영문 + 숫자 8자 이상" : "비밀번호"}
            aria-invalid={touched && Boolean(problems.password)}
            aria-describedby={touched && problems.password ? `${uid}-pwp` : undefined}
            className={cn(field, "pr-12")}
          />
          <button
            type="button"
            onClick={() => setShow((v) => !v)}
            aria-label={show ? "비밀번호 가리기" : "비밀번호 보기"}
            aria-pressed={show}
            className="absolute top-0 right-0 grid size-12 place-items-center rounded-r-xl text-muted-foreground hover:text-ink"
          >
            {show ? <EyeOff aria-hidden className="size-4" /> : <Eye aria-hidden className="size-4" />}
          </button>
        </div>
        {hint(problems.password, "pwp")}
      </div>

      {signup ? (
        <div>
          <label htmlFor={`${uid}-pw2`} className="text-body-sm font-semibold text-ink-2">
            비밀번호 확인
          </label>
          <input
            id={`${uid}-pw2`}
            name="password-confirm"
            type={show ? "text" : "password"}
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            aria-invalid={touched && Boolean(problems.confirm)}
            aria-describedby={touched && problems.confirm ? `${uid}-pw2p` : undefined}
            className={cn(field, "mt-1")}
          />
          {hint(problems.confirm, "pw2p")}
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-xl bg-pink-soft px-3 py-2.5 text-body-sm font-semibold text-pink-deep">
          {error}
        </p>
      ) : null}

      <Button type="submit" variant="brand" size="xl" disabled={busy || !ready} aria-busy={busy} className="mt-1 w-full">
        {busy ? (signup ? "만드는 중…" : "들어가는 중…") : signup ? "아이디 만들고 시작하기" : "로그인"}
      </Button>
      {signup ? <p className="text-center text-caption text-muted-foreground">이메일 인증 없이 바로 쓸 수 있어요.</p> : null}
    </form>
  );
}
