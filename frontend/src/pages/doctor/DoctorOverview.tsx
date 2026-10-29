import { motion } from "framer-motion";
import { Activity, ArrowRightLeft, ClipboardPen, FileClock, FileText, Inbox, Send, TriangleAlert, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Badge, Card, CardHeader, EmptyState, PageHeader, PageSkeleton, StatCard, statusTone } from "@/components/ui";
import { ActivityFeed, AlertCard, DocumentModal } from "@/components/clinical/widgets";
import { PatientTable, RegisterPatient, type PatientSummary } from "@/components/PatientTable";
import { useApi } from "@/hooks/useApi";
import { ago, fmtWhen, titleCase } from "@/lib/format";
import type { AgentEvent, Alert, Doc, Referral, ReleaseRequest } from "@/types";

type PipelineReferral = Referral & { patient: { user: { name: string } }; updatedAt: string; declineReason?: string | null; declinedByName?: string | null };

/** Referral card with a hover detail panel; clicking opens the referral in the Referrals hub. */
function PipelineCard({ r, delay }: { r: PipelineReferral; delay: number }) {
  const done = r.appointments.filter((a) => a.status === "COMPLETED").length;
  const missed = r.appointments.filter((a) => a.status === "MISSED").length;
  const next = r.appointments.filter((a) => ["BOOKED", "TENTATIVE"].includes(a.status) && new Date(a.startsAt) >= new Date()).sort((a, b) => +new Date(a.startsAt) - +new Date(b.startsAt))[0];
  const last = r.timeline[r.timeline.length - 1];
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay }} className="group relative">
      <Link to={`/doctor/referrals?focus=${r.id}`} className="block rounded-xl border border-line p-3 transition hover:border-brand-300 hover:shadow-[var(--shadow-card)]">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold group-hover:text-brand-700">{r.referralType}</span>
          <Badge tone={statusTone(r.status)} dot>{titleCase(r.status)}</Badge>
        </div>
        <div className="mt-0.5 text-xs text-ink-500">{r.patient.user.name} → {r.provider?.name ?? (r.status === "DECLINED" ? "rejected — needs revision" : "finding specialist…")}</div>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-500">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
            <div className="h-full rounded-full bg-brand-500" style={{ width: `${(done / r.sessions) * 100}%` }} />
          </div>
          {done}/{r.sessions}
        </div>
      </Link>
      <div className="pointer-events-none absolute left-0 right-0 top-full z-30 mt-2 translate-y-1 rounded-xl border border-line bg-white p-3 text-xs opacity-0 shadow-[var(--shadow-lift)] transition group-hover:translate-y-0 group-hover:opacity-100">
        <div className="mb-1.5 font-semibold text-ink-900">{r.reason}</div>
        <dl className="grid grid-cols-[90px_1fr] gap-x-2 gap-y-1 text-ink-500">
          <dt>Specialist</dt><dd className="text-ink-700">{r.provider ? `${r.provider.name} · ${r.provider.organization}` : "—"}</dd>
          <dt>Plan</dt><dd className="text-ink-700">{r.sessions} session(s){r.sessions > 1 ? `, ${r.frequencyPerWeek}/week for ${r.durationWeeks} wk` : ""} · {r.urgency.toLowerCase()}</dd>
          <dt>Progress</dt><dd className="text-ink-700">{done} completed{missed ? `, ${missed} missed` : ""}</dd>
          <dt>Next</dt><dd className="text-ink-700">{next ? fmtWhen(next.startsAt) : "—"}</dd>
          {r.declineReason && r.status === "DECLINED" && (<><dt className="text-rose-600">Rejected</dt><dd className="text-rose-700">“{r.declineReason}”</dd></>)}
          {last && (<><dt>Latest</dt><dd className="text-ink-700">{last.note} · {ago(last.at)}</dd></>)}
        </dl>
        <div className="mt-2 text-[11px] font-medium text-brand-700">Click to open →</div>
      </div>
    </motion.div>
  );
}

type Overview = {
  patients: PatientSummary[];
  alerts: Alert[];
  reviews: (Doc & { patient: { user: { name: string } } })[];
  referrals: PipelineReferral[];
  events: AgentEvent[];
  drafts: { id: string; kind: string; patientId: string; createdAt: string; patient: { user: { name: string } } }[];
  releases: ReleaseRequest[];
  incoming: { id: string; referralType: string; reason: string; revision: number; updatedAt: string; patient: { user: { name: string }; doctor: { name: string } } }[];
};

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
}

export default function DoctorHome() {
  const { data, reload } = useApi<Overview>("/api/overview", { poll: 20000 });
  const { data: me } = useApi<{ user: { name: string } }>("/api/auth/me");
  const [doc, setDoc] = useState<Doc | null>(null);
  useEffect(() => {
    const h = () => reload();
    window.addEventListener("agents:cycle", h);
    return () => window.removeEventListener("agents:cycle", h);
  }, [reload]);

  if (!data) return <PageSkeleton />;
  const open = data.alerts.filter((a) => a.status !== "RESOLVED");
  const mine = open.filter((a) => a.escalationLevel >= 2);
  const critical = open.filter((a) => a.severity === "CRITICAL" || a.severity === "HIGH").length;
  const rejected = data.referrals.filter((r) => r.status === "DECLINED" || r.status === "CREATED");

  return (
    <div>
      <PageHeader eyebrow="Doctor workspace" title={`${greeting()}, ${me?.user.name ?? ""}`} subtitle="Here's what your agents have coordinated, and what needs a clinical decision." actions={<RegisterPatient onCreated={reload} />} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Patients under care" value={data.patients.length} icon={<Users className="size-4" />} hint={`${data.patients.filter((p) => p.status === "RECOVERING").length} recovering at home`} />
        <StatCard label="Open alerts" value={open.length} icon={<TriangleAlert className="size-4" />} tone={critical ? "red" : "amber"} hint={`${critical} high / critical · ${mine.length} escalated to you`} delay={0.05} />
        <StatCard label="Reports to review" value={data.reviews.length} icon={<FileClock className="size-4" />} tone="violet" hint="From test centers" delay={0.1} />
        <StatCard label="Plans awaiting approval" value={data.drafts.length} icon={<ClipboardPen className="size-4" />} tone="blue" hint="Drafted by the Planning agent" delay={0.15} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          {(data.drafts.length > 0 || data.reviews.length > 0 || data.incoming.length > 0 || rejected.length > 0 || data.releases.length > 0) && (
            <Card>
              <CardHeader title="Needs your decision" subtitle="Agents never act clinically without you" icon={<ClipboardPen className="size-4" />} />
              <div className="space-y-2 px-5 pb-5">
                {data.releases.map((r) => (
                  <Link key={r.id} to={`/doctor/patients/${r.patientId}`} className="flex items-center gap-3 rounded-xl border border-amber-100 bg-amber-50/50 px-3 py-2.5 transition hover:border-amber-200">
                    <ArrowRightLeft className="size-4 text-amber-600" />
                    <div className="min-w-0 flex-1 text-sm"><b>{r.fromNurseName}</b> requests release from <b>{r.patient?.user.name}</b> — review handoff & assign the next nurse</div>
                    <span className="text-xs text-ink-500">{ago(r.createdAt)}</span>
                  </Link>
                ))}
                {data.incoming.map((r) => (
                  <Link key={r.id} to="/doctor/referrals?tab=incoming" className="flex items-center gap-3 rounded-xl border border-indigo-100 bg-indigo-50/40 px-3 py-2.5 transition hover:border-indigo-200">
                    <Inbox className="size-4 text-indigo-600" />
                    <div className="min-w-0 flex-1 text-sm"><b>{r.patient.doctor.name}</b> referred <b>{r.patient.user.name}</b> to you for {r.referralType.toLowerCase()}{r.revision ? " (revised)" : ""} — accept or reject</div>
                    <span className="text-xs text-ink-500">{ago(r.updatedAt)}</span>
                  </Link>
                ))}
                {rejected.map((r) => (
                  <Link key={r.id} to={`/doctor/referrals?focus=${r.id}`} className="flex items-center gap-3 rounded-xl border border-rose-100 bg-rose-50/50 px-3 py-2.5 transition hover:border-rose-200">
                    <Send className="size-4 text-rose-600" />
                    <div className="min-w-0 flex-1 text-sm"><b>{r.patient.user.name}</b> — {r.referralType} referral {r.status === "DECLINED" ? "rejected" : "has no specialist"}; revise & resend</div>
                    <span className="text-xs text-ink-500">{ago(r.updatedAt)}</span>
                  </Link>
                ))}
                {data.drafts.map((d) => (
                  <Link key={d.id} to={`/doctor/patients/${d.patientId}?tab=plan`} className="flex items-center gap-3 rounded-xl border border-violet-100 bg-violet-50/40 px-3 py-2.5 transition hover:border-violet-200">
                    <ClipboardPen className="size-4 text-violet-600" />
                    <div className="min-w-0 flex-1 text-sm"><b>{d.patient.user.name}</b> — {d.kind === "INITIAL" ? "discharge care plan" : "care-plan amendment"} ready for review</div>
                    <span className="text-xs text-ink-500">{ago(d.createdAt)}</span>
                  </Link>
                ))}
                {data.reviews.map((r) => (
                  <button key={r.id} onClick={() => setDoc(r)} className="flex w-full items-center gap-3 rounded-xl border border-sky-100 bg-sky-50/40 px-3 py-2.5 text-left transition hover:border-sky-200">
                    <FileText className="size-4 text-sky-600" />
                    <div className="min-w-0 flex-1 text-sm"><b>{r.patient.user.name}</b> — {r.title} uploaded, pending your review</div>
                    <span className="text-xs text-ink-500">{ago(r.createdAt)}</span>
                  </button>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <CardHeader title="My patients" subtitle="Risk is recalculated by the Monitoring agent as alerts open and close" icon={<Users className="size-4" />} action={<Link to="/doctor/patients" className="text-xs font-medium text-brand-600 hover:underline">View all</Link>} />
            <div className="px-5 pb-4">
              <PatientTable patients={data.patients} base="/doctor/patients" />
            </div>
          </Card>

          <Card>
            <CardHeader title="Referral pipeline" subtitle="Hover for details · click to open" action={<Link to="/doctor/referrals" className="text-xs font-medium text-brand-600 hover:underline">All referrals</Link>} icon={<Send className="size-4" />} />
            <div className="px-5 pb-5">
              {!data.referrals.length && <EmptyState icon={<Send className="size-5" />} title="No referrals yet" />}
              <div className="grid gap-2 sm:grid-cols-2">
                {data.referrals.slice(0, 6).map((r, i) => <PipelineCard key={r.id} r={r} delay={i * 0.04} />)}
              </div>
            </div>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader title="Escalated to you" subtitle="Level 2+ alerts across your patients" icon={<TriangleAlert className="size-4" />} action={<Link to="/doctor/alerts" className="text-xs font-medium text-brand-600 hover:underline">All alerts</Link>} />
            <div className="space-y-3 px-5 pb-5">
              {!mine.length && <EmptyState icon={<TriangleAlert className="size-5" />} title="Nothing escalated" text="Nurse-level alerts are handled by the care team first." />}
              {mine.slice(0, 4).map((a) => <AlertCard key={a.id} alert={a} onChange={reload} showPatient />)}
            </div>
          </Card>
          <Card>
            <CardHeader title="Agent activity" subtitle="Live, audit-logged" icon={<Activity className="size-4" />} />
            <div className="max-h-[560px] overflow-y-auto px-5 pb-5">
              <ActivityFeed events={data.events} showPatient limit={30} />
            </div>
          </Card>
        </div>
      </div>
      <DocumentModal doc={doc} onClose={() => setDoc(null)} canReview onReviewed={reload} />
    </div>
  );
}
