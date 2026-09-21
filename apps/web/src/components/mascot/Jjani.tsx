"use client";

/**
 * 짠이 — 공식 캐릭터. 루트 index.html <defs> 의 심볼(jj-hi … jj-cheers)을 그대로 옮겼다.
 * 좌표·색은 원본과 1:1 이고, 팔/눈/소품을 서브 컴포넌트로 쪼개 Motion 으로 따로 움직인다.
 * 표정이 바뀌면 팔은 새 포즈로 스프링 이동한다 (심볼 교체가 아니라 같은 몸이 움직이는 느낌).
 */
import { motion, useReducedMotion, type Transition } from "motion/react";
import { MOOD_LABEL, type JjaniMood } from "@/lib/mascot-copy";
import { cn } from "@/lib/utils";

const GOLD = "#F5B93A";
const GOLD_DEEP = "#E29A14";
const INK = "#14213D";
const BLUE = "#2F6BEA";

type ArmPose = { x: number; y: number; rotate: number };
const LEFT_ARM: Record<"down" | "up", ArmPose> = {
  down: { x: 22, y: 128, rotate: 18 },
  up: { x: 20, y: 94, rotate: -28 },
};
const RIGHT_ARM: Record<"down" | "up" | "mid", ArmPose> = {
  down: { x: 178, y: 128, rotate: -18 },
  up: { x: 180, y: 94, rotate: 28 },
  mid: { x: 178, y: 97, rotate: 20 },
};

interface MoodSpec {
  left: keyof typeof LEFT_ARM;
  right: keyof typeof RIGHT_ARM;
  eyes: "open" | "arc" | "wink";
  eyeOffset?: [number, number];
  cheekOffset?: [number, number];
}

const MOODS: Record<JjaniMood, MoodSpec> = {
  hi: { left: "down", right: "up", eyes: "open" },
  think: { left: "down", right: "down", eyes: "open", eyeOffset: [2, -2], cheekOffset: [0, 2] },
  done: { left: "up", right: "up", eyes: "arc" },
  wink: { left: "down", right: "mid", eyes: "wink" },
  sorry: { left: "down", right: "down", eyes: "open", eyeOffset: [0, 2], cheekOffset: [0, 2] },
  cheers: { left: "down", right: "mid", eyes: "arc" },
};

const SPRING: Transition = { type: "spring", stiffness: 260, damping: 18 };
const fillBox = { transformBox: "fill-box" } as const;

export interface JjaniProps {
  mood?: JjaniMood;
  /** px. 높이는 200:220 비율로 따라간다. className 으로 크기를 잡을 땐 생략. */
  size?: number;
  /** 팔 흔들기·깜빡임 등 idle 애니메이션. prefers-reduced-motion 이면 자동으로 꺼진다. */
  animated?: boolean;
  /** 둥실둥실 떠 있는 효과 */
  floating?: boolean;
  /** 장식용일 때 true → 스크린리더에서 숨긴다 */
  decorative?: boolean;
  label?: string;
  className?: string;
}

export function Jjani({
  mood = "hi",
  size,
  animated = true,
  floating = false,
  decorative = false,
  label,
  className,
}: JjaniProps) {
  const reduced = useReducedMotion();
  const live = animated && !reduced;
  const spec = MOODS[mood];

  return (
    <motion.svg
      viewBox="0 0 200 220"
      width={size}
      height={size ? Math.round(size * 1.1) : undefined}
      className={cn("block shrink-0 overflow-visible", className)}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : (label ?? MOOD_LABEL[mood])}
      aria-hidden={decorative || undefined}
      focusable="false"
      animate={live && floating ? { y: [0, -8, 0] } : { y: 0 }}
      transition={live && floating ? { duration: 5, repeat: Infinity, ease: "easeInOut" } : undefined}
    >
      <Back live={live} />
      <Arm pose={LEFT_ARM[spec.left]} live={live} wave={false} side="left" bounce={mood === "done"} />
      <Arm pose={RIGHT_ARM[spec.right]} live={live} wave={mood === "hi"} side="right" bounce={mood === "done"} />
      <motion.g
        animate={live && mood === "done" ? { y: [0, -5, 0] } : { y: 0 }}
        transition={live && mood === "done" ? { duration: 0.9, repeat: Infinity, ease: "easeInOut" } : SPRING}
      >
        <Coin />
        <Brows mood={mood} live={live} />
        <Eyes variant={spec.eyes} offset={spec.eyeOffset} live={live} glance={mood === "think"} />
        <Cheeks offset={spec.cheekOffset} />
        <Mouth mood={mood} />
      </motion.g>
      <Prop mood={mood} live={live} />
    </motion.svg>
  );
}

// ── 파츠 ────────────────────────────────────────────────────
function Back({ live }: { live: boolean }) {
  return (
    <g>
      <motion.ellipse
        cx="100"
        cy="207"
        rx="52"
        ry="8"
        fill={INK}
        opacity=".12"
        style={fillBox}
        animate={live ? { scaleX: [1, 0.94, 1] } : undefined}
        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
      />
      <ellipse cx="76" cy="197" rx="17" ry="10" fill={GOLD_DEEP} />
      <ellipse cx="124" cy="197" rx="17" ry="10" fill={GOLD_DEEP} />
    </g>
  );
}

function Arm({
  pose,
  live,
  wave,
  bounce,
  side,
}: {
  pose: ArmPose;
  live: boolean;
  wave: boolean;
  bounce: boolean;
  side: "left" | "right";
}) {
  // 바깥 g: 포즈(위치·각도)로 스프링 이동 / 안쪽 g: 어깨 쪽을 축으로 흔들기
  const dir = side === "right" ? 1 : -1;
  return (
    <motion.g initial={false} animate={{ x: pose.x, y: pose.y, rotate: pose.rotate }} transition={SPRING} style={fillBox}>
      <motion.g
        style={{ ...fillBox, originX: side === "right" ? 0.1 : 0.9, originY: 0.95 }}
        animate={
          live && wave
            ? { rotate: [0, 16 * dir, -6 * dir, 16 * dir, 0] }
            : live && bounce
              ? { y: [0, -4, 0] }
              : { rotate: 0, y: 0 }
        }
        transition={
          live && wave
            ? { duration: 1.4, repeat: Infinity, repeatDelay: 1.2, ease: "easeInOut" }
            : live && bounce
              ? { duration: 0.9, repeat: Infinity, ease: "easeInOut", delay: side === "right" ? 0.08 : 0 }
              : SPRING
        }
      >
        <ellipse cx="0" cy="0" rx="11" ry="16" fill={GOLD} stroke={GOLD_DEEP} strokeWidth="4" />
      </motion.g>
    </motion.g>
  );
}

function Coin() {
  return (
    <g>
      <circle cx="100" cy="112" r="80" fill={GOLD} stroke={GOLD_DEEP} strokeWidth="6" />
      <circle
        cx="100"
        cy="112"
        r="66"
        fill="none"
        stroke={GOLD_DEEP}
        strokeWidth="3"
        strokeDasharray="1 8"
        strokeLinecap="round"
      />
      <path d="M50 84A64 64 0 0 1 82 52" fill="none" stroke="#FFE7A3" strokeWidth="8" strokeLinecap="round" />
      {/* 머리 위 파란 지도 핀 */}
      <g transform="rotate(-8 100 59)">
        <path d="M100 4c-13 0-22 9-22 21 0 16 22 34 22 34s22-18 22-34c0-12-9-21-22-21z" fill={BLUE} />
        <circle cx="100" cy="25" r="7.5" fill="#fff" />
      </g>
    </g>
  );
}

function Brows({ mood, live }: { mood: JjaniMood; live: boolean }) {
  if (mood !== "think" && mood !== "sorry") return null;
  const paths = mood === "think" ? ["M66 99Q76 92 86 97", "M114 97Q124 92 134 99"] : ["M65 101L87 93", "M113 93L135 101"];
  return (
    <motion.g
      fill="none"
      stroke={INK}
      strokeWidth="3.5"
      strokeLinecap="round"
      animate={live && mood === "think" ? { y: [0, -2, 0] } : { y: 0 }}
      transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
    >
      {paths.map((d) => (
        <path key={d} d={d} />
      ))}
    </motion.g>
  );
}

function Eyes({
  variant,
  offset = [0, 0],
  live,
  glance,
}: {
  variant: MoodSpec["eyes"];
  offset?: [number, number];
  live: boolean;
  glance: boolean;
}) {
  if (variant === "arc") {
    return (
      <g fill="none" stroke={INK} strokeWidth="4.5" strokeLinecap="round">
        <path d="M66 118Q76 104 86 118" />
        <path d="M114 118Q124 104 134 118" />
      </g>
    );
  }
  const blink = live ? { scaleY: [1, 1, 0.1, 1] } : undefined;
  const blinkT: Transition = { duration: 0.35, times: [0, 0.4, 0.7, 1], repeat: Infinity, repeatDelay: 3.4 };
  return (
    // transform 속성(오프셋)과 Motion 의 style transform 이 충돌하지 않게 g 를 한 겹 더 둔다
    <g transform={`translate(${offset[0]} ${offset[1]})`}>
     <motion.g
      animate={live && glance ? { x: [0, 3, 3, -2, 0] } : { x: 0 }}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
     >
      <motion.g style={fillBox} animate={blink} transition={blinkT}>
        <circle cx="76" cy="114" r="7" fill={INK} />
        <circle cx="78.5" cy="111.5" r="2.3" fill="#fff" />
      </motion.g>
      {variant === "wink" ? (
        <path d="M116 118Q124 108 132 118" fill="none" stroke={INK} strokeWidth="4.5" strokeLinecap="round" />
      ) : (
        <motion.g style={fillBox} animate={blink} transition={blinkT}>
          <circle cx="124" cy="114" r="7" fill={INK} />
          <circle cx="126.5" cy="111.5" r="2.3" fill="#fff" />
        </motion.g>
      )}
     </motion.g>
    </g>
  );
}

function Cheeks({ offset = [0, 0] }: { offset?: [number, number] }) {
  return (
    <g transform={`translate(${offset[0]} ${offset[1]})`}>
      <ellipse cx="60" cy="132" rx="10" ry="6.5" fill="#FF9E8F" opacity=".75" />
      <ellipse cx="140" cy="132" rx="10" ry="6.5" fill="#FF9E8F" opacity=".75" />
    </g>
  );
}

function Mouth({ mood }: { mood: JjaniMood }) {
  const line = { fill: "none", stroke: INK, strokeWidth: 4, strokeLinecap: "round" as const };
  switch (mood) {
    case "think":
      return <path d="M89 136q5.5-6 11 0t11 0" {...line} />;
    case "done":
      return (
        <g>
          <path d="M86 128Q100 154 114 128Z" fill={INK} />
          <ellipse cx="100" cy="136" rx="7" ry="4" fill="#FF8A80" />
        </g>
      );
    case "sorry":
      return <path d="M90 133Q100 140 110 133" {...line} />;
    default:
      return <path d="M88 130Q100 143 112 130" {...line} />;
  }
}

function Sparkle({ d, fill, live, delay = 0 }: { d: string; fill: string; live: boolean; delay?: number }) {
  return (
    <motion.path
      d={d}
      fill={fill}
      style={fillBox}
      animate={live ? { scale: [1, 1.35, 0.8, 1], opacity: [1, 1, 0.5, 1], rotate: [0, 20, 0] } : undefined}
      transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut", delay }}
    />
  );
}

function Prop({ mood, live }: { mood: JjaniMood; live: boolean }) {
  switch (mood) {
    case "think": // 땀방울
      return (
        <motion.path
          d="M156 74c-5 8-8 12-8 16a8 8 0 0 0 16 0c0-4-3-8-8-16z"
          fill="#8FB8FF"
          stroke={BLUE}
          strokeWidth="2.5"
          strokeLinejoin="round"
          animate={live ? { y: [0, 5, 0], opacity: [1, 0.7, 1] } : undefined}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
        />
      );
    case "done":
      return (
        <g>
          <Sparkle d="M30 34Q30 44 40 44Q30 44 30 54Q30 44 20 44Q30 44 30 34Z" fill={GOLD} live={live} />
          <Sparkle d="M172 28Q172 40 184 40Q172 40 172 52Q172 40 160 40Q172 40 172 28Z" fill={BLUE} live={live} delay={0.4} />
          <Sparkle d="M148 12Q148 18 154 18Q148 18 148 24Q148 18 142 18Q148 18 148 12Z" fill={GOLD} live={live} delay={0.8} />
        </g>
      );
    case "wink": // 손에 든 동전
      return (
        <g>
          <motion.g
            style={fillBox}
            animate={live ? { y: [0, -6, 0], scaleX: [1, 0.2, 1] } : undefined}
            transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut", times: [0, 0.5, 1] }}
          >
            <circle cx="178" cy="66" r="12" fill="#FFE7A3" stroke={GOLD_DEEP} strokeWidth="3" />
            <circle cx="178" cy="66" r="6" fill="none" stroke={GOLD_DEEP} strokeWidth="2.5" />
          </motion.g>
          <Sparkle d="M150 34Q150 40 156 40Q150 40 150 46Q150 40 144 40Q150 40 150 34Z" fill={BLUE} live={live} />
        </g>
      );
    case "sorry": // 하트
      return (
        <motion.path
          d="M166 66c-12-8-18-14-18-21a9 9 0 0 1 18-4 9 9 0 0 1 18 4c0 7-6 13-18 21z"
          fill="#FF8FA3"
          style={fillBox}
          animate={live ? { scale: [1, 1.12, 1] } : undefined}
          transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
        />
      );
    case "cheers": // 건배 잔
      return (
        <g>
          <motion.g
            style={{ ...fillBox, originX: 0.5, originY: 1 }}
            animate={live ? { rotate: [0, -14, 0, -14, 0], y: [0, -3, 0, -3, 0] } : undefined}
            transition={{ duration: 1.6, repeat: Infinity, repeatDelay: 1.4, ease: "easeInOut" }}
          >
            <path d="M164 62h26v20a13 13 0 0 1-26 0z" fill="#EAF3FF" stroke={BLUE} strokeWidth="3" strokeLinejoin="round" />
            <path d="M164 71h26" fill="none" stroke={BLUE} strokeWidth="3" />
          </motion.g>
          <motion.path
            d="M172 44l-3-10M181 42l2-11M190 47l8-6"
            fill="none"
            stroke={GOLD}
            strokeWidth="3.5"
            strokeLinecap="round"
            animate={live ? { opacity: [0, 1, 0], pathLength: [0.2, 1, 1] } : undefined}
            transition={{ duration: 1.6, repeat: Infinity, repeatDelay: 1.4 }}
          />
        </g>
      );
    default:
      return null;
  }
}
