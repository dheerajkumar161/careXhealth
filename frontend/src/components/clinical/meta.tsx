import { Activity, AlertOctagon, Apple, Ban, CalendarClock, Dumbbell, FlaskConical, HandHeart, HeartPulse, Pill, Stethoscope, type LucideIcon } from "lucide-react";

export const CATEGORY_META: Record<string, { label: string; icon: LucideIcon; color: string; bg: string; ring: string }> = {
  MEDICATION: { label: "Medication", icon: Pill, color: "text-sky-600", bg: "bg-sky-50", ring: "ring-sky-100" },
  INVESTIGATION: { label: "Investigation", icon: FlaskConical, color: "text-violet-600", bg: "bg-violet-50", ring: "ring-violet-100" },
  FOLLOW_UP: { label: "Follow-up", icon: Stethoscope, color: "text-emerald-600", bg: "bg-emerald-50", ring: "ring-emerald-100" },
  REFERRAL: { label: "Referral / Rehabilitation", icon: HandHeart, color: "text-amber-600", bg: "bg-amber-50", ring: "ring-amber-100" },
  MONITORING: { label: "Monitoring", icon: Activity, color: "text-cyan-600", bg: "bg-cyan-50", ring: "ring-cyan-100" },
  DIET: { label: "Diet", icon: Apple, color: "text-lime-600", bg: "bg-lime-50", ring: "ring-lime-100" },
  EXERCISE: { label: "Exercise", icon: Dumbbell, color: "text-indigo-600", bg: "bg-indigo-50", ring: "ring-indigo-100" },
  RESTRICTION: { label: "Restrictions", icon: Ban, color: "text-orange-600", bg: "bg-orange-50", ring: "ring-orange-100" },
  CARE_INSTRUCTION: { label: "Care instructions", icon: HeartPulse, color: "text-pink-600", bg: "bg-pink-50", ring: "ring-pink-100" },
  RED_FLAG: { label: "Red flags", icon: AlertOctagon, color: "text-rose-600", bg: "bg-rose-50", ring: "ring-rose-100" },
};

export const CATEGORY_ORDER = ["MEDICATION", "INVESTIGATION", "FOLLOW_UP", "REFERRAL", "MONITORING", "RESTRICTION", "DIET", "EXERCISE", "CARE_INSTRUCTION", "RED_FLAG"];

export const AGENT_META: Record<string, { label: string; color: string; dot: string }> = {
  PLANNING: { label: "Care Planning", color: "text-violet-700 bg-violet-50 ring-violet-200", dot: "bg-violet-500" },
  EXECUTION: { label: "Execution & Scheduling", color: "text-sky-700 bg-sky-50 ring-sky-200", dot: "bg-sky-500" },
  MONITORING: { label: "Monitoring & Escalation", color: "text-rose-700 bg-rose-50 ring-rose-200", dot: "bg-rose-500" },
  COMMUNICATION: { label: "Communication & Docs", color: "text-amber-700 bg-amber-50 ring-amber-200", dot: "bg-amber-500" },
  INTELLIGENCE: { label: "Clinical Intelligence", color: "text-emerald-700 bg-emerald-50 ring-emerald-200", dot: "bg-emerald-500" },
  SERVICE: { label: "Hospital Service", color: "text-slate-700 bg-slate-100 ring-slate-200", dot: "bg-slate-400" },
  HUMAN: { label: "Clinician", color: "text-brand-700 bg-brand-50 ring-brand-200", dot: "bg-brand-500" },
};

export const METRIC_OPTIONS = [
  ["TEMPERATURE", "Temperature (°F)"],
  ["SYSTOLIC_BP", "Systolic BP (mmHg)"],
  ["DIASTOLIC_BP", "Diastolic BP (mmHg)"],
  ["HEART_RATE", "Heart rate (bpm)"],
  ["SPO2", "SpO₂ (%)"],
  ["PAIN", "Pain score (/10)"],
  ["BLOOD_GLUCOSE", "Blood glucose (mg/dL)"],
  ["WEIGHT", "Weight (kg)"],
  ["WEIGHT_GAIN", "Weight gain over 72 h (kg)"],
  ["SYMPTOM", "Symptom keywords"],
] as const;

export const UNIT: Record<string, string> = { TEMPERATURE: "°F", SYSTOLIC_BP: "mmHg", DIASTOLIC_BP: "mmHg", HEART_RATE: "bpm", SPO2: "%", PAIN: "/10", BLOOD_GLUCOSE: "mg/dL", WEIGHT: "kg", WEIGHT_GAIN: "kg" };

const freq = (n: number) => (n === 1 ? "once" : n === 2 ? "twice" : `${n} times`);

/** Human-readable title regenerated from structured details while a doctor edits an item. */
export function autoTitle(category: string, d: Record<string, unknown>): string {
  switch (category) {
    case "MEDICATION":
      return `${d.name ?? "Medication"}${d.dose ? " " + d.dose : ""} — ${freq(Number(d.timesPerDay) || 1)} daily for ${d.durationDays ?? 7} days`;
    case "INVESTIGATION":
      return `${d.test ?? "Test"} on day ${d.dayOffset ?? 1}`;
    case "FOLLOW_UP": {
      const days = Number(d.dayOffset) || 14;
      return `Follow-up${d.specialty ? ` with ${d.specialty}` : ""} in ${days % 7 === 0 ? `${days / 7} week${days > 7 ? "s" : ""}` : `${days} days`}`;
    }
    case "REFERRAL": {
      const s = Number(d.sessions) || 1;
      return `${d.referralType ?? "Referral"} — ${s} session${s > 1 ? "s" : ""}${s > 1 ? `, ${d.frequencyPerWeek ?? 1}/week for ${d.durationWeeks ?? 1} week${Number(d.durationWeeks) > 1 ? "s" : ""}` : ""}`;
    }
    case "MONITORING":
      return `Record ${String(METRIC_OPTIONS.find((m) => m[0] === d.metric)?.[1] ?? d.metric ?? "vital").replace(/ \(.*\)/, "").toLowerCase()} ${freq(Number(d.timesPerDay) || 1)} daily`;
    case "RED_FLAG": {
      const act = String(d.action ?? "NOTIFY_NURSE").replace("NOTIFY_", "notify ").replace("EMERGENCY", "emergency").toLowerCase();
      if (d.metric === "SYMPTOM") return `Symptoms: ${Array.isArray(d.keywords) ? (d.keywords as string[]).join(", ") : (d.keywords ?? "")} → ${act}`;
      const label = String(METRIC_OPTIONS.find((m) => m[0] === d.metric)?.[1] ?? d.metric).replace(/ \(.*\)/, "");
      return `${label} ${d.operator ?? ">"} ${d.threshold ?? "?"}${UNIT[String(d.metric)] ?? ""} → ${act}`;
    }
    default:
      return String(d.text ?? "");
  }
}
