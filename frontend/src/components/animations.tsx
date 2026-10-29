import { AnimatePresence, motion } from "framer-motion";
import { Bell, Building2, CalendarCheck2, Check, ClipboardList, FileText, Loader2, Paperclip, Pill, Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { cn } from "@/lib/format";

// ─────────── Care Planning: a note is scanned and sorted into structured categories ───────────
export function PlanningAnim() {
  const chips = [
    { label: "Medication", c: "bg-sky-100 text-sky-700" },
    { label: "Investigation", c: "bg-violet-100 text-violet-700" },
    { label: "Follow-up", c: "bg-emerald-100 text-emerald-700" },
    { label: "Referral", c: "bg-amber-100 text-amber-700" },
    { label: "Red flag", c: "bg-rose-100 text-rose-700" },
  ];
  return (
    <div className="relative flex h-44 w-full items-center justify-center gap-6">
      <div className="relative h-36 w-28 overflow-hidden rounded-xl border border-line bg-white p-3 shadow-[var(--shadow-card)]">
        {[90, 70, 85, 60, 80, 50, 75].map((w, i) => (
          <div key={i} className="mb-2 h-1.5 rounded-full bg-slate-200" style={{ width: `${w}%` }} />
        ))}
        <motion.div className="absolute inset-x-0 h-8 bg-gradient-to-b from-transparent via-brand-300/40 to-transparent" animate={{ top: ["-20%", "100%"] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeInOut" }} />
      </div>
      <motion.div animate={{ rotate: [0, 12, -12, 0], scale: [1, 1.15, 1] }} transition={{ duration: 1.6, repeat: Infinity }} className="text-brand-500">
        <Sparkles className="size-7" />
      </motion.div>
      <div className="flex flex-col gap-1.5">
        {chips.map((c, i) => (
          <motion.div key={c.label} className={cn("rounded-lg px-2.5 py-1 text-[11px] font-semibold", c.c)} initial={{ opacity: 0, x: -24 }} animate={{ opacity: [0, 1, 1, 0], x: [-24, 0, 0, 0] }} transition={{ duration: 3, delay: i * 0.3, repeat: Infinity, repeatDelay: 0.4, times: [0, 0.15, 0.85, 1] }}>
            {c.label}
          </motion.div>
        ))}
      </div>
    </div>
  );
}

// ─────────── Booking: calendar scans for availability, a slot gets stamped ───────────
export function BookingAnim() {
  const [pick, setPick] = useState(-1);
  useEffect(() => {
    let i = 0;
    const order = [3, 9, 15, 10, 17, 23, 11];
    const t = setInterval(() => {
      setPick(order[i % order.length]);
      i++;
    }, 380);
    return () => clearInterval(t);
  }, []);
  return (
    <div className="relative flex h-44 items-center justify-center">
      <div className="w-56 rounded-2xl border border-line bg-white p-3 shadow-[var(--shadow-card)]">
        <div className="mb-2 flex items-center justify-between">
          <div className="h-2 w-16 rounded-full bg-slate-200" />
          <CalendarCheck2 className="size-4 text-brand-500" />
        </div>
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: 28 }).map((_, i) => (
            <motion.div key={i} animate={pick === i ? { scale: [1, 1.25, 1], backgroundColor: "#6366f1" } : { scale: 1, backgroundColor: i % 7 > 4 ? "#f1f5f9" : "#e9f7f5" }} transition={{ duration: 0.3 }} className="aspect-square rounded-md" />
          ))}
        </div>
      </div>
      <motion.div className="absolute right-[calc(50%-8.5rem)] top-3 grid size-12 place-items-center rounded-full bg-brand-600 text-white shadow-lg shadow-brand-600/30" animate={{ scale: [0, 1.15, 1, 1, 0], rotate: [-30, 0, 0, 0, 0] }} transition={{ duration: 2.6, repeat: Infinity, times: [0, 0.15, 0.25, 0.85, 1] }}>
        <Check className="size-6" strokeWidth={3} />
      </motion.div>
    </div>
  );
}

// ─────────── Monitoring: ECG trace ───────────
export function HeartbeatAnim({ className, color = "#6366f1" }: { className?: string; color?: string }) {
  const path = "M0 30 L40 30 L50 30 L56 18 L62 42 L70 4 L78 56 L86 30 L120 30 L130 30 L136 22 L142 36 L150 30 L200 30";
  return (
    <svg viewBox="0 0 200 60" className={cn("h-16 w-56", className)} fill="none">
      <path d={path} stroke="#e6eaf0" strokeWidth="2" />
      <motion.path d={path} stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" initial={{ pathLength: 0, opacity: 1 }} animate={{ pathLength: [0, 1, 1], opacity: [1, 1, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut", times: [0, 0.8, 1] }} />
    </svg>
  );
}

export function MonitoringAnim() {
  return (
    <div className="relative flex h-44 flex-col items-center justify-center">
      <div className="relative">
        <span className="absolute inset-0 rounded-full bg-rose-300 animate-[var(--animate-pulse-ring)]" />
        <span className="absolute inset-0 rounded-full bg-rose-200 animate-[var(--animate-pulse-ring)] [animation-delay:0.6s]" />
        <div className="relative grid size-14 place-items-center rounded-full bg-rose-500 text-white shadow-lg shadow-rose-500/30">
          <Bell className="size-6" />
        </div>
      </div>
      <HeartbeatAnim className="mt-4" color="#e11d48" />
    </div>
  );
}

// ─────────── Documentation: pages assemble into a package ───────────
export function DocumentAnim() {
  return (
    <div className="relative flex h-44 items-center justify-center">
      {[0, 1, 2].map((i) => (
        <motion.div key={i} className="absolute h-32 w-24 rounded-xl border border-line bg-white p-2.5 shadow-[var(--shadow-card)]" initial={{ x: (i - 1) * 120, y: 30, opacity: 0, rotate: (i - 1) * 14 }} animate={{ x: [(i - 1) * 120, (i - 1) * 6, (i - 1) * 6], y: [30, -i * 4, -i * 4], opacity: [0, 1, 1], rotate: [(i - 1) * 14, (i - 1) * 4, (i - 1) * 4] }} transition={{ duration: 2.4, delay: i * 0.25, repeat: Infinity, repeatDelay: 0.6 }}>
          <FileText className="mb-2 size-4 text-brand-500" />
          {[80, 60, 90, 50, 70].map((w, j) => (
            <div key={j} className="mb-1.5 h-1 rounded-full bg-slate-200" style={{ width: `${w}%` }} />
          ))}
        </motion.div>
      ))}
      <motion.div className="absolute -top-0 right-[calc(50%-4rem)] text-amber-500" animate={{ y: [-20, 6, 6], opacity: [0, 1, 1], rotate: [-40, 10, 10] }} transition={{ duration: 2.4, delay: 1, repeat: Infinity, repeatDelay: 0.6 }}>
        <Paperclip className="size-7" />
      </motion.div>
    </div>
  );
}

// ─────────── Referral routing: paper plane to a provider ───────────
export function SendAnim() {
  return (
    <div className="relative flex h-44 w-full items-center justify-between px-10">
      <div className="grid size-12 place-items-center rounded-2xl bg-brand-50 text-brand-600 ring-1 ring-brand-100">
        <FileText className="size-5" />
      </div>
      <svg className="absolute inset-x-16 top-1/2 h-16 -translate-y-1/2" viewBox="0 0 200 60" preserveAspectRatio="none" style={{ width: "calc(100% - 8rem)" }}>
        <path d="M0 40 C 60 -10, 140 -10, 200 30" stroke="#cbd5e1" strokeWidth="1.5" strokeDasharray="4 5" fill="none" />
      </svg>
      <motion.div className="absolute left-16 top-1/2 text-brand-600" animate={{ x: ["0%", "540%"], y: [-4, -34, -14], rotate: [-10, 8, 20], opacity: [0, 1, 1, 0] }} transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}>
        <Send className="size-7" />
      </motion.div>
      <motion.div className="grid size-12 place-items-center rounded-2xl bg-indigo-50 text-indigo-600 ring-1 ring-indigo-100" animate={{ scale: [1, 1, 1.12, 1] }} transition={{ duration: 1.8, repeat: Infinity, times: [0, 0.75, 0.88, 1] }}>
        <Building2 className="size-5" />
      </motion.div>
    </div>
  );
}

// ─────────── Handoff: clipboard passes between clinicians ───────────
export function HandoffAnim() {
  return (
    <div className="relative flex h-44 w-full items-center justify-between px-12">
      {["bg-sky-500", "bg-brand-500"].map((c, i) => (
        <div key={i} className="flex flex-col items-center gap-1.5">
          <div className={cn("size-12 rounded-full ring-4 ring-white shadow", c)} />
          <div className="h-1.5 w-12 rounded-full bg-slate-200" />
        </div>
      ))}
      <motion.div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-white p-2.5 shadow-[var(--shadow-lift)]" animate={{ x: [-90, 90], rotate: [-8, 8] }} transition={{ duration: 1.6, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }}>
        <ClipboardList className="size-6 text-brand-600" />
      </motion.div>
    </div>
  );
}

// ─────────── Medication taken: capsule drops into a check ───────────
export function PillAnim({ size = 56 }: { size?: number }) {
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      <motion.div initial={{ y: -size * 0.6, rotate: -45, opacity: 0 }} animate={{ y: 0, rotate: 0, opacity: [0, 1, 0] }} transition={{ duration: 0.6 }} className="absolute text-brand-500">
        <Pill style={{ width: size * 0.5, height: size * 0.5 }} />
      </motion.div>
      <motion.div initial={{ scale: 0 }} animate={{ scale: [0, 1.2, 1] }} transition={{ delay: 0.45, duration: 0.4 }} className="grid size-full place-items-center rounded-full bg-emerald-500 text-white">
        <Check style={{ width: size * 0.5, height: size * 0.5 }} strokeWidth={3} />
      </motion.div>
    </div>
  );
}

export function SuccessCheck({ size = 64 }: { size?: number }) {
  return (
    <motion.div initial={{ scale: 0 }} animate={{ scale: [0, 1.15, 1] }} transition={{ duration: 0.45 }} className="grid place-items-center rounded-full bg-emerald-500 text-white shadow-lg shadow-emerald-500/30" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" className="size-1/2" fill="none" stroke="currentColor" strokeWidth={3} strokeLinecap="round" strokeLinejoin="round">
        <motion.path d="M5 12.5l4.5 4.5L19 7.5" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ delay: 0.25, duration: 0.4 }} />
      </svg>
    </motion.div>
  );
}

// ─────────── Agent overlay: animation + live step tracker while an agent works ───────────
export type AgentKind = "planning" | "booking" | "monitoring" | "document" | "send" | "handoff";
const ANIMS: Record<AgentKind, () => React.ReactElement> = { planning: PlanningAnim, booking: BookingAnim, monitoring: MonitoringAnim, document: DocumentAnim, send: SendAnim, handoff: HandoffAnim };

export function AgentOverlay({ open, kind, agent, title, steps }: { open: boolean; kind: AgentKind; agent: string; title: string; steps: string[] }) {
  const [active, setActive] = useState(0);
  useEffect(() => {
    if (!open) return setActive(0);
    const t = setInterval(() => setActive((a) => Math.min(a + 1, steps.length - 1)), 900);
    return () => clearInterval(t);
  }, [open, steps.length]);
  const Anim = ANIMS[kind];
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] grid place-items-center bg-slate-900/25 backdrop-blur-sm p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <motion.div initial={{ scale: 0.94, y: 12 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, opacity: 0 }} className="w-full max-w-md overflow-hidden rounded-3xl bg-white shadow-[var(--shadow-lift)]">
            <div className="dot-grid border-b border-line bg-gradient-to-b from-brand-50/70 to-white px-6 pt-5">
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-brand-700">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-brand-400 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-brand-500" />
                </span>
                {agent}
              </div>
              <Anim />
            </div>
            <div className="px-6 py-5">
              <h3 className="text-base font-semibold">{title}</h3>
              <ul className="mt-3 space-y-2.5">
                {steps.map((s, i) => (
                  <motion.li key={s} initial={{ opacity: 0, x: -6 }} animate={{ opacity: i <= active ? 1 : 0.4, x: 0 }} transition={{ delay: i * 0.05 }} className="flex items-center gap-2.5 text-sm">
                    <span className={cn("grid size-5 shrink-0 place-items-center rounded-full", i < active ? "bg-emerald-500 text-white" : i === active ? "bg-brand-50 text-brand-600" : "bg-slate-100 text-ink-400")}>
                      {i < active ? <Check className="size-3" strokeWidth={3} /> : i === active ? <Loader2 className="size-3 animate-spin" /> : <span className="size-1.5 rounded-full bg-current" />}
                    </span>
                    <span className={i <= active ? "text-ink-900" : "text-ink-500"}>{s}</span>
                  </motion.li>
                ))}
              </ul>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
