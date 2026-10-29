import { AnimatePresence, motion } from "framer-motion";
import { Loader2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { forwardRef, useEffect, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn, initials } from "@/lib/format";

// ───────────── Button ─────────────
type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "soft" | "outline";
const BTN: Record<BtnVariant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm shadow-brand-600/20",
  secondary: "bg-white text-ink-900 border border-line hover:bg-slate-50 hover:border-slate-300",
  outline: "border border-brand-200 text-brand-700 bg-white hover:bg-brand-50",
  ghost: "text-ink-700 hover:bg-slate-100",
  danger: "bg-rose-600 text-white hover:bg-rose-700 shadow-sm shadow-rose-600/20",
  soft: "bg-brand-50 text-brand-700 hover:bg-brand-100",
};
export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: BtnVariant; size?: "sm" | "md" | "lg"; loading?: boolean; icon?: ReactNode }>(
  function Button({ variant = "primary", size = "md", loading, icon, className, children, disabled, ...rest }, ref) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all duration-150 active:scale-[0.98] disabled:opacity-55 disabled:pointer-events-none whitespace-nowrap",
          size === "sm" && "h-8 px-3 text-xs",
          size === "md" && "h-10 px-4 text-sm",
          size === "lg" && "h-12 px-6 text-sm",
          BTN[variant],
          className,
        )}
        {...rest}
      >
        {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
        {children}
      </button>
    );
  },
);

// ───────────── Card ─────────────
export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-line bg-white shadow-[var(--shadow-card)]", className)} {...rest}>
      {children}
    </div>
  );
}

export function CardHeader({ title, subtitle, icon, action, className }: { title: ReactNode; subtitle?: ReactNode; icon?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 px-5 pt-5 pb-3", className)}>
      <div className="flex items-start gap-3 min-w-0">
        {icon && <div className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600">{icon}</div>}
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold text-ink-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
        </div>
      </div>
      {action}
    </div>
  );
}

// ───────────── Badge ─────────────
const TONES = {
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  brand: "bg-brand-50 text-brand-700 ring-brand-200",
  blue: "bg-sky-50 text-sky-700 ring-sky-200",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  indigo: "bg-indigo-50 text-indigo-700 ring-indigo-200",
} as const;
export type Tone = keyof typeof TONES;
export function Badge({ tone = "gray", children, className, dot }: { tone?: Tone; children: ReactNode; className?: string; dot?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset whitespace-nowrap", TONES[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current opacity-80" />}
      {children}
    </span>
  );
}

export const severityTone = (s: string): Tone => (s === "CRITICAL" ? "red" : s === "HIGH" ? "amber" : s === "MEDIUM" ? "blue" : "gray");
export const statusTone = (s: string): Tone =>
  ({
    COMPLETED: "green", TAKEN: "green", RESOLVED: "green", ACTIVE: "green", ACCEPTED: "green", REVIEWED: "green", LOW: "green",
    SCHEDULED: "blue", BOOKED: "blue", IN_PROGRESS: "brand", IN_TREATMENT: "brand", SENT: "indigo", RECOVERING: "brand",
    PENDING: "gray", DRAFT: "violet", TENTATIVE: "violet", CREATED: "gray", AWAITING_RESULT: "amber", PENDING_REVIEW: "amber", ACKNOWLEDGED: "blue", MODERATE: "amber",
    MISSED: "red", SKIPPED: "amber", FAILED: "red", DECLINED: "red", ESCALATED: "red", OPEN: "amber", HIGH: "red", CANCELLED: "gray", RESCHEDULED: "gray", ADMITTED: "violet",
  })[s] as Tone ?? "gray";

// ───────────── Inputs ─────────────
const FIELD = "w-full rounded-xl border border-line bg-white px-3.5 text-sm text-ink-900 placeholder:text-ink-400 outline-none transition focus:border-brand-400 focus:ring-4 focus:ring-brand-100";
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...p }, ref) {
  return <input ref={ref} className={cn(FIELD, "h-10", className)} {...p} />;
});
export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...p }, ref) {
  return <textarea ref={ref} className={cn(FIELD, "py-2.5 leading-relaxed resize-none", className)} {...p} />;
});
export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(FIELD, "h-10 pr-8 appearance-none bg-[url('data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2212%22 height=%2212%22 viewBox=%220 0 24 24%22 fill=%22none%22 stroke=%22%2364748b%22 stroke-width=%222%22><path d=%22m6 9 6 6 6-6%22/></svg>')] bg-[length:14px] bg-[right_0.75rem_center] bg-no-repeat", className)} {...p}>
      {children}
    </select>
  );
}
export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 block text-xs font-medium text-ink-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-ink-500">{hint}</span>}
    </label>
  );
}

// ───────────── Modal ─────────────
export function Modal({ open, onClose, title, subtitle, children, size = "md", footer }: { open: boolean; onClose: () => void; title?: ReactNode; subtitle?: ReactNode; children: ReactNode; size?: "sm" | "md" | "lg" | "xl"; footer?: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-slate-900/30 backdrop-blur-[2px]" onClick={onClose} />
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 16, scale: 0.98 }}
            transition={{ type: "spring", damping: 26, stiffness: 320 }}
            className={cn(
              "relative w-full max-h-[92vh] overflow-hidden rounded-t-2xl sm:rounded-2xl bg-white shadow-[var(--shadow-lift)] flex flex-col",
              size === "sm" && "sm:max-w-md",
              size === "md" && "sm:max-w-xl",
              size === "lg" && "sm:max-w-3xl",
              size === "xl" && "sm:max-w-5xl",
            )}
          >
            {title && (
              <div className="flex items-start justify-between gap-4 border-b border-line px-6 py-4">
                <div>
                  <h2 className="text-base font-semibold">{title}</h2>
                  {subtitle && <p className="mt-0.5 text-xs text-ink-500">{subtitle}</p>}
                </div>
                <button onClick={onClose} className="rounded-lg p-1.5 text-ink-500 hover:bg-slate-100" aria-label="Close">
                  <X className="size-4" />
                </button>
              </div>
            )}
            <div className="overflow-y-auto px-6 py-5">{children}</div>
            {footer && <div className="flex justify-end gap-2 border-t border-line bg-slate-50/60 px-6 py-3">{footer}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// ───────────── Tabs ─────────────
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; icon?: ReactNode; count?: number }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto rounded-xl border border-line bg-white p-1 shadow-[var(--shadow-card)]">
      {tabs.map((t) => (
        <button key={t.id} onClick={() => onChange(t.id)} className={cn("relative flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium whitespace-nowrap transition-colors", value === t.id ? "text-brand-700" : "text-ink-500 hover:text-ink-900")}>
          {value === t.id && <motion.span layoutId="tab-pill" className="absolute inset-0 rounded-lg bg-brand-50 ring-1 ring-brand-100" transition={{ type: "spring", damping: 30, stiffness: 400 }} />}
          <span className="relative flex items-center gap-2">
            {t.icon}
            {t.label}
            {!!t.count && <span className="rounded-full bg-white px-1.5 text-[10px] font-semibold text-ink-700 ring-1 ring-line">{t.count}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

// ───────────── Misc ─────────────
export function Avatar({ name, size = 36, tone = "brand" }: { name: string; size?: number; tone?: "brand" | "slate" | "violet" | "amber" | "sky" }) {
  const tones = { brand: "from-brand-400 to-brand-600", slate: "from-slate-400 to-slate-600", violet: "from-violet-400 to-violet-600", amber: "from-amber-400 to-orange-500", sky: "from-sky-400 to-blue-600" };
  return (
    <div className={cn("grid shrink-0 place-items-center rounded-full bg-gradient-to-br font-semibold text-white", tones[tone])} style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials(name)}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton", className)} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-72" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-80 rounded-2xl lg:col-span-2" />
        <Skeleton className="h-80 rounded-2xl" />
      </div>
    </div>
  );
}

export function EmptyState({ icon, title, text, action }: { icon: ReactNode; title: string; text?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 grid size-12 place-items-center rounded-2xl bg-slate-50 text-ink-400 ring-1 ring-line">{icon}</div>
      <p className="text-sm font-medium text-ink-900">{title}</p>
      {text && <p className="mt-1 max-w-sm text-xs text-ink-500">{text}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function StatCard({ label, value, icon, tone = "brand", hint, delay = 0 }: { label: string; value: ReactNode; icon: ReactNode; tone?: "brand" | "amber" | "red" | "blue" | "violet" | "green"; hint?: ReactNode; delay?: number }) {
  const tones = { brand: "bg-brand-50 text-brand-600", amber: "bg-amber-50 text-amber-600", red: "bg-rose-50 text-rose-600", blue: "bg-sky-50 text-sky-600", violet: "bg-violet-50 text-violet-600", green: "bg-emerald-50 text-emerald-600" };
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.35 }}>
      <Card className="p-5 h-full">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-ink-500">{label}</span>
          <span className={cn("grid size-9 place-items-center rounded-xl", tones[tone])}>{icon}</span>
        </div>
        <div className="mt-3 font-display text-2xl font-bold text-ink-900">{value}</div>
        {hint && <div className="mt-1 text-xs text-ink-500">{hint}</div>}
      </Card>
    </motion.div>
  );
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div className={cn("prose-doc", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; eyebrow?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div>
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-wider text-brand-600">{eyebrow}</div>}
        <h1 className="text-2xl font-bold text-ink-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-ink-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function FadeIn({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.3 }} className={className}>
      {children}
    </motion.div>
  );
}
