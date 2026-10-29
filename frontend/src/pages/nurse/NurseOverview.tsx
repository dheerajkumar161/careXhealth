import { Activity, CalendarClock, ClipboardList, HeartPulse, Pill, TriangleAlert, Users } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, Markdown, Modal, PageHeader, PageSkeleton, StatCard, statusTone } from "@/components/ui";
import { ActivityFeed, AlertCard } from "@/components/clinical/widgets";
import { IncomingHandoffCard } from "@/components/clinical/NurseHandover";
import { AgentOverlay } from "@/components/animations";
import type { PatientSummary } from "@/components/PatientTable";
import { api, withMinDuration } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { ago, fmtDate, titleCase } from "@/lib/format";
import type { AgentEvent, Alert, Appointment, Doc, Dose, ReleaseRequest } from "@/types";

type Overview = {
  patients: PatientSummary[];
  alerts: Alert[];
  appointmentsToday: (Appointment & { patient: { user: { name: string } } })[];
  dosesToday: (Dose & { patientId: string; patient: { user: { name: string } } })[];
  handoffs: (Doc & { patient: { user: { name: string } }; createdBy?: { name: string } | null })[];
  events: AgentEvent[];
  incomingHandoffs?: ReleaseRequest[];
};

export default function NurseHome() {
  const { data, reload } = useApi<Overview>("/api/overview", { poll: 15000 });
  const { data: me } = useApi<{ user: { name: string } }>("/api/auth/me");
  const [busy, setBusy] = useState(false);
  const [shift, setShift] = useState<Doc[] | null>(null);
  useEffect(() => {
    const h = () => reload();
    window.addEventListener("agents:cycle", h);
    return () => window.removeEventListener("agents:cycle", h);
  }, [reload]);

  if (!data) return <PageSkeleton />;
  const open = data.alerts.filter((a) => a.status !== "RESOLVED");
  const unack = open.filter((a) => !a.acknowledgedAt);
  const missedToday = data.dosesToday.filter((d) => d.status === "MISSED" || d.status === "SKIPPED");

  async function shiftHandoff() {
    setBusy(true);
    try {
      const docs = await withMinDuration(Promise.all(data!.patients.filter((p) => p.status !== "ADMITTED").map((p) => api<{ document: Doc }>(`/api/patients/${p.id}/intelligence`, { body: { kind: "HANDOFF" } }).then((r) => r.document))), 3200);
      setShift(docs);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Handoff failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Nurse workspace"
        title={`Shift overview — ${me?.user.name.split(" ")[0] ?? ""}`}
        subtitle="Your patients, the alert queue and today’s care activities in one place."
        actions={<Button icon={<ClipboardList className="size-4" />} onClick={shiftHandoff}>Generate shift handoff</Button>}
      />
      {!!data.incomingHandoffs?.length && (
        <Card className="mb-6">
          <CardHeader title="Handoffs awaiting your acceptance" subtitle="The doctor chose you to take over these patients" icon={<ClipboardList className="size-4" />} />
          <div className="space-y-3 px-5 pb-5">
            {data.incomingHandoffs.map((r) => <IncomingHandoffCard key={r.id} request={r} onDone={reload} />)}
          </div>
        </Card>
      )}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Assigned patients" value={data.patients.length} icon={<Users className="size-4" />} />
        <StatCard label="Unacknowledged alerts" value={unack.length} icon={<TriangleAlert className="size-4" />} tone={unack.length ? "red" : "green"} hint={`${open.length} open in total`} delay={0.05} />
        <StatCard label="Appointments today" value={data.appointmentsToday.length} icon={<CalendarClock className="size-4" />} tone="blue" delay={0.1} />
        <StatCard label="Missed / skipped doses today" value={missedToday.length} icon={<Pill className="size-4" />} tone={missedToday.length ? "amber" : "green"} delay={0.15} />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader title="Alert queue" subtitle="Acknowledge within the escalation window or it escalates to the doctor" icon={<TriangleAlert className="size-4" />} action={<Link to="/nurse/alerts" className="text-xs font-medium text-brand-600 hover:underline">Full queue</Link>} />
            <div className="space-y-3 px-5 pb-5">
              {!open.length && <EmptyState icon={<TriangleAlert className="size-5" />} title="Queue is clear" />}
              {open.slice(0, 5).map((a) => <AlertCard key={a.id} alert={a} onChange={reload} showPatient />)}
            </div>
          </Card>
          <Card>
            <CardHeader title="My patients" icon={<HeartPulse className="size-4" />} />
            <div className="grid gap-3 px-5 pb-5 sm:grid-cols-2">
              {data.patients.map((p) => (
                <Link key={p.id} to={`/nurse/patients/${p.id}`} className="rounded-2xl border border-line p-4 transition hover:border-brand-200 hover:shadow-[var(--shadow-card)]">
                  <div className="flex items-center gap-3">
                    <Avatar name={p.user.name} tone={p.riskLevel === "HIGH" ? "amber" : "brand"} />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{p.user.name}</div>
                      <div className="truncate text-xs text-ink-500">{p.procedure || p.diagnosis}</div>
                    </div>
                    {p.pendingRelease ? <Badge tone="amber">Release pending</Badge> : <Badge tone={statusTone(p.riskLevel)}>{titleCase(p.riskLevel)}</Badge>}
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-center text-[11px]">
                    <div className="rounded-lg bg-slate-50 py-1.5"><div className="font-semibold text-ink-900">{p.openAlerts}</div><div className="text-ink-500">alerts</div></div>
                    <div className="rounded-lg bg-slate-50 py-1.5"><div className="font-semibold text-ink-900">{p.adherence === null ? "—" : `${p.adherence}%`}</div><div className="text-ink-500">adherence</div></div>
                    <div className="rounded-lg bg-slate-50 py-1.5"><div className="font-semibold text-ink-900">{titleCase(p.status)}</div><div className="text-ink-500">status</div></div>
                  </div>
                </Link>
              ))}
            </div>
          </Card>
        </div>
        <div className="space-y-6">
          <Card>
            <CardHeader title="Today's schedule" icon={<CalendarClock className="size-4" />} />
            <div className="space-y-2 px-5 pb-5">
              {!data.appointmentsToday.length && <p className="text-sm text-ink-500">No appointments today.</p>}
              {data.appointmentsToday.map((a) => (
                <div key={a.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2">
                  <span className="w-14 text-xs font-semibold">{fmtDate(a.startsAt, "h:mm a")}</span>
                  <div className="min-w-0 flex-1 text-xs"><div className="truncate font-medium">{a.patient.user.name}</div><div className="truncate text-ink-500">{a.title}</div></div>
                  <Badge tone={statusTone(a.status)}>{titleCase(a.status)}</Badge>
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <CardHeader title="Recent handoffs" icon={<ClipboardList className="size-4" />} action={<Link to="/nurse/handoffs" className="text-xs font-medium text-brand-600 hover:underline">All</Link>} />
            <div className="space-y-2 px-5 pb-5">
              {!data.handoffs.length && <p className="text-sm text-ink-500">No handoffs yet.</p>}
              {data.handoffs.slice(0, 4).map((h) => (
                <button key={h.id} onClick={() => setShift([h])} className="flex w-full items-center justify-between rounded-xl border border-line px-3 py-2 text-left text-xs hover:border-brand-200">
                  <span><b className="text-ink-900">{h.patient.user.name}</b> · {h.createdBy?.name}</span>
                  <span className="text-ink-500">{ago(h.createdAt)}</span>
                </button>
              ))}
            </div>
          </Card>
          <Card>
            <CardHeader title="Agent activity" icon={<Activity className="size-4" />} />
            <div className="max-h-[420px] overflow-y-auto px-5 pb-5"><ActivityFeed events={data.events} showPatient limit={20} /></div>
          </Card>
        </div>
      </div>

      <AgentOverlay open={busy} kind="handoff" agent="Clinical Intelligence & Handoff Agent" title="Preparing shift handoff" steps={["Gathering every assigned patient's record", "Summarising status, vitals & adherence", "Listing alerts, pending tasks & appointments", "Writing action items for the incoming nurse"]} />
      <Modal open={!!shift} onClose={() => setShift(null)} size="lg" title={shift && shift.length > 1 ? "Shift handoff" : shift?.[0]?.title} subtitle="AI-generated from live records — verify before acting">
        <div className="space-y-6">
          {shift?.map((d, i) => (
            <div key={d.id} className={i ? "border-t border-line pt-6" : ""}>
              <Markdown>{d.content}</Markdown>
            </div>
          ))}
        </div>
      </Modal>
    </div>
  );
}
