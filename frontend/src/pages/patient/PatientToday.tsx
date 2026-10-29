import { motion } from "framer-motion";
import { Activity, CalendarClock, MessageCircleHeart, Phone, Pill, Sparkles, Stethoscope } from "lucide-react";
import { Link } from "react-router-dom";
import { Avatar, Button, Card, CardHeader, EmptyState, PageSkeleton } from "@/components/ui";
import { AppointmentRow, DoseList, ObservationForm } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import { fmtDate } from "@/lib/format";
import type { PatientRecord } from "@/types";

function Ring({ value }: { value: number | null }) {
  const v = value ?? 0;
  const r = 34, c = 2 * Math.PI * r;
  return (
    <div className="relative grid size-24 place-items-center">
      <svg viewBox="0 0 80 80" className="absolute inset-0 -rotate-90">
        <circle cx="40" cy="40" r={r} stroke="#e6f6f3" strokeWidth="7" fill="none" />
        <motion.circle cx="40" cy="40" r={r} stroke="#6366f1" strokeWidth="7" fill="none" strokeLinecap="round" strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c - (c * v) / 100 }} transition={{ duration: 1.2, ease: "easeOut" }} />
      </svg>
      <div className="text-center">
        <div className="font-display text-xl font-bold">{value === null ? "—" : `${value}%`}</div>
        <div className="text-[10px] text-ink-500">on track</div>
      </div>
    </div>
  );
}

export default function PatientHome() {
  const { data, reload } = useApi<PatientRecord>("/api/overview", { poll: 30000 });
  if (!data) return <PageSkeleton />;
  const { patient } = data;
  const first = patient.user.name.split(" ")[0];
  const today = new Date().toDateString();
  const todays = data.doses.filter((d) => new Date(d.scheduledAt).toDateString() === today && d.status !== "CANCELLED");
  const upcoming = data.appointments.filter((a) => new Date(a.startsAt) >= new Date() && ["BOOKED", "TENTATIVE"].includes(a.status));
  const readings = data.tasks.filter((t) => t.type === "MONITORING" && t.status === "IN_PROGRESS");
  const day = patient.dischargeDate ? Math.max(Math.floor((Date.now() - new Date(patient.dischargeDate).getTime()) / 86_400_000), 0) : null;
  const hasPlan = data.plans.some((p) => p.status === "ACTIVE");

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="relative mb-6 overflow-hidden rounded-3xl border border-brand-100 bg-gradient-to-br from-brand-50 via-white to-sky-50 p-6 sm:p-8">
        <div className="dot-grid absolute inset-0 opacity-50" />
        <div className="relative flex flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wider text-brand-700">{day !== null ? `Recovery day ${day}` : "Welcome"}</div>
            <h1 className="mt-1 text-2xl font-bold sm:text-3xl">Hi {first}, here’s your day</h1>
            <p className="mt-1 max-w-lg text-sm text-ink-500">
              {hasPlan ? `${todays.filter((d) => d.status === "PENDING").length} medicine dose(s) left today${upcoming[0] ? ` · next: ${upcoming[0].title}, ${fmtDate(upcoming[0].startsAt, "EEE h:mm a")}` : ""}.` : "Your doctor is preparing your recovery plan. You’ll be notified once it’s ready."}
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to="/patient/assistant"><Button icon={<MessageCircleHeart className="size-4" />}>Ask your care assistant</Button></Link>
              <Link to="/patient/plan"><Button variant="secondary" icon={<Sparkles className="size-4" />}>My recovery plan</Button></Link>
            </div>
          </div>
          <div className="flex items-center gap-4 rounded-2xl bg-white/80 p-4 ring-1 ring-line backdrop-blur">
            <Ring value={data.adherence} />
            <div className="text-xs text-ink-500">Medicine<br />adherence<br />this week</div>
          </div>
        </div>
      </motion.div>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader title="Today’s medicines" subtitle="Tap “Taken” after each dose — reminders arrive 30 minutes before" icon={<Pill className="size-4" />} />
            <div className="px-5 pb-5"><DoseList doses={todays} canRecord onChange={reload} /></div>
          </Card>
          <Card>
            <CardHeader title="Coming up" icon={<CalendarClock className="size-4" />} action={<Link to="/patient/appointments" className="text-xs font-medium text-brand-600 hover:underline">All appointments</Link>} />
            <div className="space-y-2 px-5 pb-5">
              {!upcoming.length && <EmptyState icon={<CalendarClock className="size-5" />} title="No upcoming appointments" />}
              {upcoming.slice(0, 4).map((a) => <AppointmentRow key={a.id} a={a} />)}
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="How are you feeling?" subtitle={readings.length ? `Your doctor asked you to: ${readings.map((r) => r.title.toLowerCase()).join("; ")}` : "Log a reading or tell us about any problem"} icon={<Activity className="size-4" />} />
            <div className="px-5 pb-5"><ObservationForm patientId={patient.id} onDone={reload} /></div>
          </Card>
          <Card>
            <CardHeader title="Your care team" icon={<Stethoscope className="size-4" />} />
            <div className="space-y-3 px-5 pb-5">
              {[{ u: patient.doctor, role: "Treating doctor" }, ...(patient.nurse ? [{ u: patient.nurse, role: "Your nurse" }] : [])].map(({ u, role }) => (
                <div key={u.id} className="flex items-center gap-3">
                  <Avatar name={u.name} />
                  <div className="min-w-0 flex-1"><div className="text-sm font-medium">{u.name}</div><div className="text-xs text-ink-500">{role}</div></div>
                  {u.phone && <a href={`tel:${u.phone}`} className="grid size-9 place-items-center rounded-xl bg-brand-50 text-brand-600"><Phone className="size-4" /></a>}
                </div>
              ))}
              <p className="rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 ring-1 ring-rose-100">In an emergency call <b>108 / 112</b> immediately.</p>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
