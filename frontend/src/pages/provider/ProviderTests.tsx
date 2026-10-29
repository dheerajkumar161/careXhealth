import { motion } from "framer-motion";
import { Building2, CalendarCheck2, Check, FileText, FlaskConical, Inbox, Star, Upload, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, Field, Input, Markdown, Modal, PageHeader, PageSkeleton, StatCard, Tabs, Textarea, statusTone } from "@/components/ui";
import { AgentOverlay } from "@/components/animations";
import { api, withMinDuration } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { demoMode } from "@/lib/demo";
import { age, fmtDate, fmtWhen, titleCase } from "@/lib/format";
import type { Doc } from "@/types";
import { SessionActions, type ProviderOverview } from "@/components/ProviderShared";

function LabUpload({ a, onDone }: { a: ProviderOverview["appointments"][number]; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [vals, setVals] = useState<Record<string, string>>({});
  const [findings, setFindings] = useState("");
  const [busy, setBusy] = useState(false);
  const panel = a.panel;
  async function submit() {
    setBusy(true);
    try {
      const values = Object.fromEntries(Object.entries(vals).filter(([, v]) => v !== "").map(([k, v]) => [k, Number(v)]));
      await withMinDuration(api(`/api/appointments/${a.id}/result`, { body: { values, findings: findings || undefined } }), 3200);
      toast.success("Report delivered", { description: "Stored in the patient's EHR and routed to the doctor and patient." });
      setOpen(false);
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button size="sm" icon={<Upload className="size-3.5" />} onClick={() => setOpen(true)}>Upload results</Button>
      <Modal open={open} onClose={() => setOpen(false)} size="md" title={`${panel?.name ?? a.title} — results`} subtitle={`${a.patient.user.name} · MRN ${a.patient.mrn} · collected ${fmtDate(a.startsAt, "d MMM, h:mm a")}`} footer={<><Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button><Button onClick={submit} icon={<Upload className="size-4" />}>Submit report</Button></>}>
        <div className="space-y-3">
          {panel?.params.map((p) => (
            <div key={p.key} className="grid grid-cols-[1fr_140px] items-center gap-3">
              <div>
                <div className="text-sm font-medium">{p.label}</div>
                <div className="text-[11px] text-ink-500">Ref {p.low !== undefined && p.high !== undefined ? `${p.low}–${p.high}` : p.high !== undefined ? `< ${p.high}` : `> ${p.low}`} {p.unit}</div>
              </div>
              <Input type="number" step="any" value={vals[p.key] ?? ""} onChange={(e) => setVals((v) => ({ ...v, [p.key]: e.target.value }))} placeholder={p.unit} />
            </div>
          ))}
          <Field label="Findings / impression">
            <Textarea rows={3} value={findings} onChange={(e) => setFindings(e.target.value)} placeholder={panel?.params.length ? "Optional" : "Describe the findings"} />
          </Field>
        </div>
      </Modal>
      <AgentOverlay open={busy} kind="document" agent="Communication & Documentation Agent" title="Processing the report" steps={["Identifying patient & matching the investigation", "Flagging values against reference ranges", "Storing the report in the EHR", "Notifying doctor & patient", "Monitoring agent checking for abnormal results"]} />
    </>
  );
}

export default function TestCenterHome() {
  const { data, reload } = useApi<ProviderOverview>("/api/overview", { poll: 20000 });
  if (!data) return <PageSkeleton />;
  const { provider } = data;

  const header = (
    <PageHeader
      eyebrow="Test center portal"
      title={provider.organization}
      subtitle={<span className="inline-flex flex-wrap items-center gap-2"><Building2 className="size-3.5" /> {provider.location} · <Star className="size-3.5 fill-amber-400 text-amber-400" /> {provider.rating} · {provider.specialties.split(",").map((s) => titleCase(s)).join(", ")}</span>}
    />
  );

  if (data.isLab) {
    const pending = data.appointments.filter((a) => a.kind === "TEST" && a.status === "BOOKED");
    const done = data.appointments.filter((a) => a.kind === "TEST" && a.status === "COMPLETED");
    return (
      <div>
        {header}
        <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-3">
          <StatCard label="Awaiting results" value={pending.length} icon={<FlaskConical className="size-4" />} tone="violet" />
          <StatCard label="Reports delivered" value={done.length} icon={<Check className="size-4" />} tone="green" delay={0.05} />
          <StatCard label="Today's collections" value={pending.filter((a) => new Date(a.startsAt).toDateString() === new Date().toDateString()).length} icon={<CalendarCheck2 className="size-4" />} tone="blue" delay={0.1} />
        </div>
        <Card>
          <CardHeader title="Tests to perform" subtitle="Booked automatically by the Execution agent from doctors’ care plans — upload results when ready" icon={<FlaskConical className="size-4" />} />
          <div className="space-y-2 px-5 pb-5">
            {!pending.length && <EmptyState icon={<Inbox className="size-5" />} title="No pending tests" />}
            {pending.map((a) => (
              <div key={a.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-line px-4 py-3">
                <Avatar name={a.patient.user.name} size={36} />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{a.panel?.name ?? a.title} <span className="text-ink-500">· {a.patient.user.name}</span></div>
                  <div className="text-xs text-ink-500">MRN {a.patient.mrn} · {fmtWhen(a.startsAt)}{a.panel?.prep ? ` · ${a.panel.prep}` : ""}</div>
                </div>
                {demoMode() || new Date(a.startsAt).getTime() <= Date.now() + 12 * 3_600_000 ? <LabUpload a={a} onDone={reload} /> : <Badge tone="blue">Scheduled</Badge>}
              </div>
            ))}
          </div>
        </Card>
        {!!done.length && (
          <Card className="mt-6">
            <CardHeader title="Delivered reports" icon={<Check className="size-4" />} />
            <div className="space-y-2 px-5 pb-5">
              {done.map((a) => (
                <div key={a.id} className="flex items-center justify-between rounded-xl border border-line px-4 py-2.5 text-sm">
                  <span>{a.panel?.name ?? a.title} · {a.patient.user.name}</span>
                  <span className="text-xs text-ink-500">{fmtDate(a.startsAt, "d MMM")}</span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    );
  }

  return (
    <div>
      {header}
      <Card className="p-5">
        <EmptyState icon={<FlaskConical className="size-5" />} title="This portal is for test centers" text="Referrals between doctors are handled in the doctor portal." />
      </Card>
    </div>
  );
}
