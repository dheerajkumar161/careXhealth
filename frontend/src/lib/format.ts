import { format, formatDistanceToNowStrict, isToday, isTomorrow, isYesterday } from "date-fns";
import clsx, { type ClassValue } from "clsx";

export const cn = (...c: ClassValue[]) => clsx(c);

export const d = (v: string | Date | null | undefined) => (v ? new Date(v) : null);

export function fmtDate(v: string | Date | null | undefined, pattern = "d MMM yyyy") {
  const x = d(v);
  return x ? format(x, pattern) : "—";
}

export function fmtWhen(v: string | Date | null | undefined) {
  const x = d(v);
  if (!x) return "—";
  if (isToday(x)) return `Today, ${format(x, "h:mm a")}`;
  if (isTomorrow(x)) return `Tomorrow, ${format(x, "h:mm a")}`;
  if (isYesterday(x)) return `Yesterday, ${format(x, "h:mm a")}`;
  return format(x, "EEE d MMM, h:mm a");
}

export function ago(v: string | Date | null | undefined) {
  const x = d(v);
  return x ? `${formatDistanceToNowStrict(x)} ago` : "—";
}

export function age(dob: string | Date) {
  return Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 86_400_000));
}

export function initials(name: string) {
  return name
    .replace(/^Dr\.?\s+/i, "")
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");
}

export const titleCase = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
