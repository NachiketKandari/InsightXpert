"use client";

import { motion, AnimatePresence } from "framer-motion";
import { RefreshCw, Clock } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import type { HealthStatus } from "@/hooks/use-health-check";

interface ServerDownScreenProps {
  status: HealthStatus;
  lastChecked: Date | null;
  onRetry: () => void;
}

// ─── Witty messages ───────────────────────────────────────────────────────────

const MESSAGES = [
  {
    headline: "Looks like our calculators ran out of coffee",
    subtext: "The analytics engine is taking an unscheduled break. Back before you can say",
  },
  {
    headline: "Seems the SQL server needed a bathroom break",
    subtext: "Even databases need a moment. Hang tight while we flush the connection pool and try again —",
  },
  {
    headline: "Our data pipeline got tangled up",
    subtext: "Someone left a semicolon in the wrong place. We're untangling the query queue as we speak —",
  },
  {
    headline: "The spreadsheets have gone on strike",
    subtext: "Negotiations are underway. Expect a resolution before the next GROUP BY clause. Meanwhile —",
  },
  {
    headline: "Error 503: Insufficient caffeine in server room",
    subtext: "Engineering has been dispatched with an emergency espresso. Normal service resumes shortly —",
  },
  {
    headline: "Our servers are doing unauthorized yoga",
    subtext: "The downward-dog pose is wreaking havoc on uptime. We're stretching toward a fix —",
  },
  {
    headline: "The dashboard flew to the wrong endpoint",
    subtext: "We've issued an APB for the missing analytics. Last seen near port 8000, heading north —",
  },
  {
    headline: "Our data gnomes clocked out early",
    subtext: "They left a note: back after a GROUP BY and a cup of tea. We'll have them sorted —",
  },
  {
    headline: "Someone tripped over the ethernet cable again",
    subtext: "A classic. The culprit has been identified. Data flow should resume any second now —",
  },
  {
    headline: "The analytics engine phoned in sick",
    subtext: "We've sent the backup hamster to power the wheel. ETA: very soon —",
  },
] as const;

// ─── Layout variants (3 different chaotic arrangements) ──────────────────────

const VARIANTS = [
  {
    p1: "translate(8, 8) rotate(-12, 30, 38)",
    p2: "translate(178, 5) rotate(16, 30, 38)",
    p3: "translate(105, 72) rotate(-7, 23, 29)",
    chart: "translate(52, 104) rotate(22, 26, 22)",
    ruler: "translate(18, 162) rotate(-18, 74, 6)",
    mug: "translate(196, 114)",
    spill: "translate(160, 144)",
  },
  {
    p1: "translate(18, 12) rotate(-24, 30, 38)",
    p2: "translate(162, 12) rotate(10, 30, 38)",
    p3: "translate(82, 58) rotate(14, 23, 29)",
    chart: "translate(158, 92) rotate(-18, 26, 22)",
    ruler: "translate(28, 158) rotate(16, 74, 6)",
    mug: "translate(186, 118)",
    spill: "translate(148, 150)",
  },
  {
    p1: "translate(5, 18) rotate(9, 30, 38)",
    p2: "translate(188, 8) rotate(-20, 30, 38)",
    p3: "translate(112, 80) rotate(-16, 23, 29)",
    chart: "translate(42, 92) rotate(-10, 26, 22)",
    ruler: "translate(12, 165) rotate(-28, 74, 6)",
    mug: "translate(198, 110)",
    spill: "translate(158, 140)",
  },
] as const;

// ─── SVG shape helpers ────────────────────────────────────────────────────────

function SpreadsheetPaper({ w = 60, h = 76 }: { w?: number; h?: number }) {
  const cw = w / 3;
  const rh = h / 6;
  return (
    <g>
      <rect
        width={w} height={h} rx={2}
        fill="currentColor" fillOpacity={0.04}
        stroke="currentColor" strokeWidth={1.5}
      />
      <rect width={w} height={rh} rx={2} fill="currentColor" fillOpacity={0.1} />
      <line x1={cw} y1={0} x2={cw} y2={h} stroke="currentColor" strokeWidth={0.75} opacity={0.3} />
      <line x1={cw * 2} y1={0} x2={cw * 2} y2={h} stroke="currentColor" strokeWidth={0.75} opacity={0.3} />
      {[2, 3, 4, 5].map((i) => (
        <line
          key={i} x1={0} y1={i * rh} x2={w} y2={i * rh}
          stroke="currentColor" strokeWidth={0.75} opacity={0.3}
        />
      ))}
      {[1, 2, 3, 4].map((row) => (
        <g key={row}>
          <line
            x1={3} y1={row * rh + rh / 2} x2={cw - 4} y2={row * rh + rh / 2}
            stroke="currentColor" strokeWidth={0.9} opacity={0.25}
          />
          <line
            x1={cw + 3} y1={row * rh + rh / 2} x2={cw * 2 - 5} y2={row * rh + rh / 2}
            stroke="currentColor" strokeWidth={0.9} opacity={0.2}
          />
          {row < 3 && (
            <line
              x1={cw * 2 + 3} y1={row * rh + rh / 2} x2={w - 4} y2={row * rh + rh / 2}
              stroke="currentColor" strokeWidth={0.9} opacity={0.2}
            />
          )}
        </g>
      ))}
    </g>
  );
}

function BarChart() {
  const bars = [
    { x: 5, y: 28, h: 12 },
    { x: 17, y: 18, h: 22 },
    { x: 29, y: 10, h: 30 },
    { x: 41, y: 22, h: 18 },
  ] as const;
  return (
    <g>
      <rect
        width={52} height={44} rx={2}
        fill="currentColor" fillOpacity={0.04}
        stroke="currentColor" strokeWidth={1.5}
      />
      {bars.map((b, i) => (
        <rect
          key={i} x={b.x} y={b.y} width={8} height={b.h} rx={1}
          fill="currentColor" fillOpacity={0.15 + i * 0.04}
          stroke="currentColor" strokeWidth={0.75}
        />
      ))}
      <line x1={2} y1={40} x2={50} y2={40} stroke="currentColor" strokeWidth={0.9} opacity={0.4} />
      <line x1={2} y1={4} x2={2} y2={40} stroke="currentColor" strokeWidth={0.9} opacity={0.4} />
    </g>
  );
}

function Ruler() {
  return (
    <g>
      <rect
        width={148} height={12} rx={2}
        fill="currentColor" fillOpacity={0.05}
        stroke="currentColor" strokeWidth={1.5}
      />
      {Array.from({ length: 14 }, (_, i) => (
        <line
          key={i}
          x1={8 + i * 10} y1={0}
          x2={8 + i * 10} y2={i % 2 === 0 ? 6 : 4}
          stroke="currentColor" strokeWidth={0.75} opacity={0.45}
        />
      ))}
    </g>
  );
}

function CoffeeMugFallen() {
  return (
    <g>
      <rect
        width={46} height={30} rx={5}
        fill="currentColor" fillOpacity={0.07}
        stroke="currentColor" strokeWidth={1.5}
      />
      <ellipse
        cx={46} cy={15} rx={5} ry={13.5}
        fill="currentColor" fillOpacity={0.06}
        stroke="currentColor" strokeWidth={1.5}
      />
      <ellipse
        cx={0} cy={15} rx={5} ry={13.5}
        fill="currentColor" fillOpacity={0.06}
        stroke="currentColor" strokeWidth={1.5}
      />
      <path d="M 14 0 C 14 -12 32 -12 32 0" stroke="currentColor" strokeWidth={1.5} fill="none" />
      <path
        d="M -4 10 C -8 14 -10 18 -6 22"
        stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" fill="none" opacity={0.55}
      />
    </g>
  );
}

function CoffeeSpill() {
  return (
    <motion.path
      d="M 12 8 C 4 2 -8 6 -14 14 C -20 22 -16 34 -4 34 C 8 34 22 38 36 32 C 50 26 56 14 46 8 C 36 2 20 14 12 8 Z"
      fill="currentColor" fillOpacity={0.09}
      stroke="currentColor" strokeWidth={1} strokeOpacity={0.18}
      animate={{ scale: [1, 1.05, 1] }}
      transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      style={{ transformOrigin: "18px 20px" }}
    />
  );
}

// ─── Illustration ─────────────────────────────────────────────────────────────

interface IllustrationProps {
  variant: number;
  isChecking: boolean;
}

function ChaosIllustration({ variant, isChecking }: IllustrationProps) {
  const layout = VARIANTS[variant % VARIANTS.length];

  const float = (duration: number, delay: number) => ({
    animate: { y: [0, -8, 0] },
    transition: { duration, delay, repeat: Infinity, ease: "easeInOut" as const },
  });

  return (
    <svg
      viewBox="-20 -20 320 240"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className="w-full h-full"
      overflow="visible"
    >
      {/* Whole scene subtly pulses when checking, signalling activity */}
      <motion.g
        animate={isChecking ? { opacity: [0.75, 1, 0.75] } : { opacity: 1 }}
        transition={isChecking ? { duration: 1.2, repeat: Infinity, ease: "easeInOut" } : {}}
      >
        {/* Layout key ensures elements animate in fresh on each variant change */}
        <AnimatePresence mode="wait">
          <motion.g
            key={variant}
            initial={{ opacity: 0, scale: 0.93 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.93 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
          >
            {/* Paper 1 */}
            <motion.g {...float(3.4, 0)}>
              <g transform={layout.p1}>
                <SpreadsheetPaper w={60} h={76} />
              </g>
            </motion.g>

            {/* Paper 2 */}
            <motion.g {...float(3.9, 0.7)}>
              <g transform={layout.p2}>
                <SpreadsheetPaper w={60} h={76} />
              </g>
            </motion.g>

            {/* Paper 3 */}
            <motion.g {...float(4.2, 1.4)}>
              <g transform={layout.p3}>
                <SpreadsheetPaper w={46} h={58} />
              </g>
            </motion.g>

            {/* Bar chart */}
            <motion.g {...float(4.6, 1.9)}>
              <g transform={layout.chart}>
                <BarChart />
              </g>
            </motion.g>

            {/* Ruler */}
            <motion.g
              animate={{ y: [0, -3, 0] }}
              transition={{ duration: 5.2, repeat: Infinity, ease: "easeInOut", delay: 0.4 }}
            >
              <g transform={layout.ruler}>
                <Ruler />
              </g>
            </motion.g>

            {/* Coffee mug */}
            <motion.g
              animate={{ y: [0, -2, 0] }}
              transition={{ duration: 6.5, repeat: Infinity, ease: "easeInOut", delay: 1.1 }}
            >
              <g transform={layout.mug}>
                <CoffeeMugFallen />
              </g>
            </motion.g>

            {/* Coffee spill */}
            <g transform={layout.spill}>
              <CoffeeSpill />
            </g>
          </motion.g>
        </AnimatePresence>
      </motion.g>
    </svg>
  );
}

// ─── Seconds counter ──────────────────────────────────────────────────────────

function useSecondsSince(date: Date | null): number | null {
  const [seconds, setSeconds] = useState<number | null>(null);

  useEffect(() => {
    if (!date) { setSeconds(null); return; }
    const update = () => setSeconds(Math.floor((Date.now() - date.getTime()) / 1000));
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [date]);

  return seconds;
}

// ─── Main exported component ──────────────────────────────────────────────────

export function ServerDownScreen({ status, lastChecked, onRetry }: ServerDownScreenProps) {
  const [retryCount, setRetryCount] = useState(0);
  const secondsSince = useSecondsSince(lastChecked);
  const isChecking = status === "checking";

  const handleRetry = useCallback(() => {
    setRetryCount((c) => c + 1);
    onRetry();
  }, [onRetry]);

  const msg = MESSAGES[retryCount % MESSAGES.length];
  const variant = retryCount % VARIANTS.length;

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-background px-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: "easeOut" }}
        className="flex flex-col items-center gap-7 max-w-sm w-full text-center"
      >
        {/* Illustration — extra padding so float animation never clips */}
        <div className="w-72 h-56 overflow-visible text-foreground/75">
          <ChaosIllustration variant={variant} isChecking={isChecking} />
        </div>

        {/* Copy — fades when message changes */}
        <AnimatePresence mode="wait">
          <motion.div
            key={retryCount}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="space-y-2.5"
          >
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              {msg.headline}
            </h1>
            <p className="text-sm text-muted-foreground leading-relaxed">
              {msg.subtext}{" "}
              <code className="text-xs bg-muted px-1.5 py-0.5 rounded font-mono">
                SELECT * FROM calm
              </code>
            </p>
          </motion.div>
        </AnimatePresence>

        {/* Status line */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Clock className="h-3 w-3 shrink-0" />
          {isChecking ? (
            <span>Checking server…</span>
          ) : secondsSince !== null ? (
            <span>
              {secondsSince < 3 ? "Just checked" : `Last checked ${secondsSince}s ago`}
              {" · auto-retrying every 10s"}
            </span>
          ) : null}
        </div>

        {/* Retry button */}
        <Button
          variant="outline"
          size="sm"
          onClick={handleRetry}
          disabled={isChecking}
          className="gap-2"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${isChecking ? "animate-spin" : ""}`} />
          {isChecking ? "Checking…" : "Try now"}
        </Button>
      </motion.div>
    </div>
  );
}
