import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowUpRight, BellRing, CalendarDays, Check, CheckCircle2, CircleDashed, Clock, Eye, FileText, FlaskConical, Hand, HeartPulse, MapPin, Pill, Send, ShieldAlert, Thermometer, TriangleAlert, FileDown, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, EmptyState, Field, Input, Markdown, Modal, Select, Textarea, severityTone, statusTone } from "../ui";
import { AgentOverlay, PillAnim } from "../animations";
import { AGENT_META } from "./meta";
import { SourceViewer } from "./SourceImages";
import { api, withMinDuration, documentPdfUrl } from "@/services/api";
import { demoMode } from "@/lib/demo";
import { ago, cn, fmtDate, fmtWhen, titleCase } from "@/lib/format";
import type { AgentEvent, Alert, Appointment, Doc, Dose, Observation, Referral, Rule } from "@/types";
import { VitalChart } from "./VitalChart";

// ───────────── Alerts ─────────────

const LEVEL = { 1: "Nurse", 2: "Doctor", 3: "Emergency" } as Record<number, string>;

export function AlertCard({ alert, onChange, showPatient }: { alert: Alert; onChange: () => void; showPatient?: boolean }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [note, setNote] = useState("");
  const [expanded, setExpanded] = useState(false);

  async function act(action: "ACKNOWLEDGE" | "RESOLVE" | "ESCALATE", n?: string) {
    setBusy(action);
    try {
      await api(`/api/alerts/${alert.id}`, { method: "PATCH", body: { action, note: n } });
      toast.success(action === "ACKNOWLEDGE" ? "Alert acknowledged" : action === "RESOLVE" ? "Alert resolved" : "Alert escalated");
      setResolving(false);
      onChange();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  const critical = alert.severity === "CRITICAL" && alert.status !== "RESOLVED";
  return (
    <motion.div layout initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className={cn("relative overflow-hidden rounded-2xl border bg-white p-4", critical ? "border-rose-200" : alert.status === "RESOLVED" ? "border-line opacity-70" : "border-line")}>
      <span className={cn("absolute inset-y-0 left-0 w-1", alert.severity === "CRITICAL" ? "bg-rose-500" : alert.severity === "HIGH" ? "bg-amber-400" : alert.severity === "MEDIUM" ? "bg-sky-400" : "bg-slate-300")} />
      <div className="flex items-start gap-3">
        <div className={cn("relative grid size-9 shrink-0 place-items-center rounded-xl", critical ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-600")}>
          {critical && <span className="absolute inset-0 rounded-xl bg-rose-300 animate-[var(--animate-pulse-ring)]" />}
          <TriangleAlert className="relative size-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={severityTone(alert.severity)}>{alert.severity}</Badge>
            <Badge tone={statusTone(alert.status)} dot>{titleCase(alert.status)}</Badge>
            <Badge tone="gray">L{alert.escalationLevel} · {LEVEL[alert.escalationLevel]}</Badge>
            <span className="text-[11px] text-ink-400">{ago(alert.createdAt)}</span>
          </div>
          <div className="mt-1.5 text-sm font-semibold text-ink-900">
            {showPatient && alert.patient && <span className="text-brand-700">{alert.patient.user.name} · </span>}
            {alert.title}
          </div>
          <p className="mt-0.5 text-xs leading-relaxed text-ink-500">{alert.message}</p>
          {alert.status !== "RESOLVED" && alert.escalateAfter && !alert.acknowledgedAt && (
            <p className="mt-1.5 flex items-center gap-1 text-[11px] font-medium text-amber-700">
              <Clock className="size-3" /> Auto-escalates {new Date(alert.escalateAfter) > new Date() ? `in ${ago(alert.escalateAfter).replace(" ago", "")}` : "on next agent cycle"} if not acknowledged
            </p>
          )}
          {alert.resolution && <p className="mt-1.5 text-xs text-emerald-700">✓ {alert.resolution}</p>}
          <button onClick={() => setExpanded((e) => !e)} className="mt-1.5 text-[11px] font-medium text-ink-500 hover:text-ink-900">
            {expanded ? "Hide" : "Show"} history ({alert.history.length})
          </button>
          <AnimatePresence>
            {expanded && (
              <motion.ol initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-2 space-y-1 overflow-hidden border-l border-line pl-3">
                {alert.history.map((h, i) => (
                  <li key={i} className="text-[11px] text-ink-500">
                    <span className="text-ink-700">{h.event}</span>
                    {h.by && ` — ${h.by}`} · {fmtWhen(h.at)}
                  </li>
                ))}
              </motion.ol>
            )}
          </AnimatePresence>
        </div>
      </div>
      {alert.status !== "RESOLVED" && (
        <div className="mt-3 flex flex-wrap gap-2 pl-12">
          {!alert.acknowledgedAt && (
            <Button size="sm" variant="soft" icon={<Hand className="size-3.5" />} loading={busy === "ACKNOWLEDGE"} onClick={() => act("ACKNOWLEDGE")}>
              Acknowledge
            </Button>
          )}
          <Button size="sm" variant="secondary" icon={<Check className="size-3.5" />} onClick={() => setResolving(true)}>
            Resolve
          </Button>
          {alert.escalationLevel < 3 && (
            <Button size="sm" variant="ghost" className="text-rose-600 hover:bg-rose-50" icon={<ArrowUpRight className="size-3.5" />} loading={busy === "ESCALATE"} onClick={() => act("ESCALATE")}>
              Escalate to {LEVEL[alert.escalationLevel + 1]}
            </Button>
          )}
        </div>
      )}
      <Modal open={resolving} onClose={() => setResolving(false)} title="Resolve alert" subtitle={alert.title} size="sm" footer={<><Button variant="ghost" onClick={() => setResolving(false)}>Cancel</Button><Button loading={busy === "RESOLVE"} onClick={() => act("RESOLVE", note)}>Resolve</Button></>}>
        <Field label="Resolution / action taken">
          <Textarea rows={4} autoFocus value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Called patient, advised paracetamol per plan, temperature recheck in 2 h — 99.2°F." />
        </Field>
      </Modal>
    </motion.div>
  );
}

export function AlertList({ alerts, onChange, showPatient, emptyText = "No active alerts" }: { alerts: Alert[]; onChange: () => void; showPatient?: boolean; emptyText?: string }) {
  const [showResolved, setShowResolved] = useState(false);
  const open = alerts.filter((a) => a.status !== "RESOLVED");
  const resolved = alerts.filter((a) => a.status === "RESOLVED");
  return (
    <div className="space-y-3">
      {!open.length && <EmptyState icon={<ShieldAlert className="size-5" />} title={emptyText} text="The Monitoring agent is watching vitals, symptoms, adherence and results against the doctor-approved rules." />}
      <AnimatePresence>{open.map((a) => <AlertCard key={a.id} alert={a} onChange={onChange} showPatient={showPatient} />)}</AnimatePresence>
      {!!resolved.length && (
        <button onClick={() => setShowResolved((s) => !s)} className="text-xs font-medium text-ink-500 hover:text-ink-900">
          {showResolved ? "Hide" : "Show"} {resolved.length} resolved alert(s)
        </button>
      )}
      {showResolved && resolved.map((a) => <AlertCard key={a.id} alert={a} onChange={onChange} showPatient={showPatient} />)}
    </div>
  );
}

// ───────────── Referral tracker ─────────────

const REF_STEPS = ["CREATED", "SENT", "ACCEPTED", "SCHEDULED", "IN_TREATMENT", "COMPLETED"];

export function ReferralTracker({ referral, onOpenDoc }: { referral: Referral; onOpenDoc?: (id: string) => void }) {
  const reached = new Set(referral.timeline.map((t) => t.status));
  const currentIdx = REF_STEPS.indexOf(referral.status);
  const active = referral.appointments.filter((a) => a.status !== "CANCELLED");
  const done = active.filter((a) => a.status === "COMPLETED").length;
  const missed = active.filter((a) => a.status === "MISSED").length;
  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h4 className="font-semibold">{referral.referralType}</h4>
            <Badge tone={statusTone(referral.status)} dot>{titleCase(referral.status)}</Badge>
            {referral.urgency !== "ROUTINE" && <Badge tone="red">{referral.urgency}</Badge>}
          </div>
          <p className="mt-0.5 text-xs text-ink-500">{referral.reason}</p>
          {referral.provider && (
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-700">
              <MapPin className="size-3 text-ink-400" /> {referral.provider.name} · {referral.provider.organization}
            </p>
          )}
        </div>
        <div className="text-right">
          <div className="font-display text-xl font-bold">{done}<span className="text-sm font-medium text-ink-400">/{referral.sessions}</span></div>
          <div className="text-[11px] text-ink-500">sessions completed{missed ? ` · ${missed} missed` : ""}</div>
        </div>
      </div>

      <div className="mt-4 flex items-center">
        {REF_STEPS.map((s, i) => {
          const ok = reached.has(s) || i < currentIdx;
          const cur = s === referral.status;
          return (
            <div key={s} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <motion.div initial={{ scale: 0.6 }} animate={{ scale: 1 }} transition={{ delay: i * 0.06 }} className={cn("grid size-6 place-items-center rounded-full text-white", ok ? "bg-brand-500" : "bg-slate-200", cur && "ring-4 ring-brand-100")}>
                  {ok ? <Check className="size-3.5" strokeWidth={3} /> : <span className="size-1.5 rounded-full bg-white" />}
                </motion.div>
                <span className={cn("hidden whitespace-nowrap text-[10px] sm:block", ok ? "text-ink-700" : "text-ink-400")}>{titleCase(s)}</span>
              </div>
              {i < REF_STEPS.length - 1 && <div className={cn("mx-1 h-0.5 flex-1 rounded-full sm:mb-4", reached.has(REF_STEPS[i + 1]) || i + 1 <= currentIdx ? "bg-brand-400" : "bg-slate-200")} />}
            </div>
          );
        })}
      </div>

      {active.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5">
          {active.map((a) => (
            <span key={a.id} title={`${a.title} — ${fmtWhen(a.startsAt)} · ${a.status}`} className={cn("grid size-7 place-items-center rounded-lg text-[10px] font-semibold ring-1", a.status === "COMPLETED" ? "bg-emerald-50 text-emerald-700 ring-emerald-200" : a.status === "MISSED" ? "bg-rose-50 text-rose-700 ring-rose-200" : a.status === "TENTATIVE" ? "bg-violet-50 text-violet-600 ring-violet-200 ring-dashed" : "bg-white text-ink-700 ring-line")}>
              {a.sequence ?? "•"}
            </span>
          ))}
        </div>
      )}

      <details className="mt-3">
        <summary className="cursor-pointer select-none text-xs font-medium text-ink-500 hover:text-ink-900">Workflow timeline</summary>
        <ol className="mt-2 space-y-1.5 border-l border-line pl-3">
          {referral.timeline.map((t, i) => (
            <li key={i} className="text-[11px] text-ink-500">
              <b className="text-ink-700">{titleCase(t.status)}</b> — {t.note} · {fmtWhen(t.at)}
            </li>
          ))}
        </ol>
      </details>
      {referral.packageDocumentId && onOpenDoc && (
        <Button size="sm" variant="outline" className="mt-3" icon={<FileText className="size-3.5" />} onClick={() => onOpenDoc(referral.packageDocumentId!)}>
          View referral package
        </Button>
      )}
    </Card>
  );
}

// ───────────── Appointments ─────────────

const APPT_ICON: Record<string, LucideIcon> = { TEST: FlaskConical, FOLLOW_UP: HeartPulse, THERAPY: Hand, SPECIALIST: Send };

export function AppointmentRow({ a, right }: { a: Appointment; right?: React.ReactNode }) {
  const Icon = APPT_ICON[a.kind] ?? CalendarDays;
  const date = new Date(a.startsAt);
  return (
    <div className="flex items-center gap-3 rounded-xl border border-line bg-white px-3 py-2.5">
      <div className="grid w-12 shrink-0 place-items-center rounded-lg bg-slate-50 py-1 ring-1 ring-line">
        <span className="text-[10px] font-semibold uppercase text-brand-600">{fmtDate(date, "MMM")}</span>
        <span className="font-display text-lg font-bold leading-none">{fmtDate(date, "d")}</span>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm font-medium">
          <Icon className="size-3.5 shrink-0 text-ink-400" />
          <span className="truncate">{a.title}</span>
        </div>
        <div className="mt-0.5 truncate text-xs text-ink-500">
          {fmtDate(date, "EEE, h:mm a")} · {a.provider.name}
        </div>
      </div>
      {right ?? <Badge tone={statusTone(a.status)}>{titleCase(a.status)}</Badge>}
    </div>
  );
}

// ───────────── Medication schedule ─────────────

export function DoseList({ doses, canRecord, onChange }: { doses: Dose[]; canRecord?: boolean; onChange?: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState<string | null>(null);
  async function record(id: string, status: "TAKEN" | "SKIPPED") {
    setBusy(id);
    try {
      await api(`/api/doses/${id}`, { method: "PATCH", body: { status } });
      if (status === "TAKEN") {
        setCelebrate(id);
        setTimeout(() => setCelebrate(null), 1400);
      } else toast("Dose marked as skipped — your nurse will be informed if this becomes a pattern.");
      onChange?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not record dose");
    } finally {
      setBusy(null);
    }
  }
  if (!doses.length) return <EmptyState icon={<Pill className="size-5" />} title="No doses scheduled" />;
  const now = Date.now();
  return (
    <div className="space-y-2">
      {doses.map((d) => {
        const due = new Date(d.scheduledAt).getTime();
        const actionable = canRecord && d.status === "PENDING" && (demoMode() || due <= now + 2 * 3_600_000);
        return (
          <div key={d.id} className={cn("relative flex items-center gap-3 rounded-xl border px-3 py-2.5 transition", d.status === "TAKEN" ? "border-emerald-100 bg-emerald-50/40" : d.status === "MISSED" ? "border-rose-100 bg-rose-50/40" : "border-line bg-white")}>
            <div className="w-16 shrink-0 text-xs font-semibold text-ink-700">{fmtDate(d.scheduledAt, "h:mm a")}</div>
            <div className={cn("grid size-8 shrink-0 place-items-center rounded-lg", d.status === "TAKEN" ? "bg-emerald-100 text-emerald-600" : "bg-sky-50 text-sky-600")}>
              <Pill className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium leading-snug">{d.medication} <span className="text-ink-500">{d.dose}</span></div>
              {d.recordedAt && <div className="text-[11px] text-ink-500">Recorded {fmtWhen(d.recordedAt)}</div>}
            </div>
            {celebrate === d.id ? (
              <PillAnim size={32} />
            ) : actionable ? (
              <div className="flex gap-1.5">
                <Button size="sm" variant="ghost" onClick={() => record(d.id, "SKIPPED")} disabled={!!busy}>Skip</Button>
                <Button size="sm" loading={busy === d.id} onClick={() => record(d.id, "TAKEN")} icon={<Check className="size-3.5" />}>Taken</Button>
              </div>
            ) : (
              <Badge tone={statusTone(d.status)}>{titleCase(d.status)}</Badge>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ───────────── Vitals ─────────────

const VITAL_TYPES = [
  { type: "TEMPERATURE", label: "Temperature", unit: "°F", icon: Thermometer },
  { type: "BP", label: "Blood pressure", unit: "mmHg", icon: HeartPulse },
  { type: "HEART_RATE", label: "Heart rate", unit: "bpm", icon: HeartPulse },
  { type: "SPO2", label: "SpO₂", unit: "%", icon: CircleDashed },
  { type: "PAIN", label: "Pain", unit: "/10", icon: TriangleAlert },
  { type: "BLOOD_GLUCOSE", label: "Glucose", unit: "mg/dL", icon: CircleDashed },
];

function Sparkline({ values, flagged }: { values: number[]; flagged?: boolean }) {
  if (values.length < 2) return <div className="h-8" />;
  const min = Math.min(...values), max = Math.max(...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * 100},${28 - ((v - min) / (max - min || 1)) * 24}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" className="h-8 w-full" preserveAspectRatio="none">
      <motion.polyline points={pts} fill="none" stroke={flagged ? "#e11d48" : "#6366f1"} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 0.9 }} />
    </svg>
  );
}

export function VitalsGrid({ observations, rules = [] }: { observations: Observation[]; rules?: Rule[] }) {
  const [chart, setChart] = useState<(typeof VITAL_TYPES)[number] | null>(null);
  const tiles = VITAL_TYPES.map((v) => {
    const list = observations.filter((o) => o.type === v.type).sort((a, b) => +new Date(a.recordedAt) - +new Date(b.recordedAt));
    return { ...v, list, latest: list[list.length - 1] };
  }).filter((t) => t.latest);
  if (!tiles.length) return <EmptyState icon={<HeartPulse className="size-5" />} title="No vitals recorded yet" />;
  return (
    <>
    <Modal open={!!chart} onClose={() => setChart(null)} title={chart ? `${chart.label} trend` : ""} size="lg">
      {chart && <VitalChart type={chart.type} unit={chart.unit} observations={observations} rules={rules} />}
    </Modal>
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
      {tiles.map((t) => (
        <button key={t.type} type="button" onClick={() => setChart(t)} title="Open trend chart" className={cn("rounded-xl border p-3 text-left transition hover:shadow-md", t.latest.flagged ? "border-rose-200 bg-rose-50/40" : "border-line bg-white")}>
          <div className="flex items-center justify-between text-[11px] font-medium text-ink-500">
            <span className="flex items-center gap-1"><t.icon className="size-3" /> {t.label}</span>
            {t.latest.flagged && <Badge tone="red">flagged</Badge>}
          </div>
          <div className="mt-1 font-display text-xl font-bold">
            {t.latest.value}{t.latest.value2 ? `/${t.latest.value2}` : ""}<span className="ml-0.5 text-xs font-medium text-ink-400">{t.unit}</span>
          </div>
          <Sparkline values={t.list.map((o) => o.value ?? 0)} flagged={t.latest.flagged} />
          <div className="text-[10px] text-ink-400">{ago(t.latest.recordedAt)} · {t.latest.source.toLowerCase()}</div>
        </button>
      ))}
    </div>
    </>
  );
}

export function ObservationForm({ patientId, onDone, clinician }: { patientId: string; onDone: () => void; clinician?: boolean }) {
  const [type, setType] = useState("TEMPERATURE");
  const [v1, setV1] = useState("");
  const [v2, setV2] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const textual = type === "SYMPTOM" || type === "NURSE_NOTE";
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await withMinDuration(api<{ alerts: number }>(`/api/patients/${patientId}/observations`, { body: { type, value: v1 ? Number(v1) : undefined, value2: v2 ? Number(v2) : undefined, text: text || undefined } }), 1600);
      if (res.alerts) toast.warning("Reading flagged by the Monitoring agent", { description: "The care team has been alerted." });
      else toast.success("Recorded — within your plan's thresholds");
      setV1(""); setV2(""); setText("");
      onDone();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Type" className="col-span-2 sm:col-span-1">
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {VITAL_TYPES.map((v) => <option key={v.type} value={v.type}>{v.label} ({v.unit})</option>)}
            <option value="WEIGHT">Weight (kg)</option>
            <option value="SYMPTOM">Symptom / problem</option>
            {clinician && <option value="NURSE_NOTE">Nurse observation note</option>}
          </Select>
        </Field>
        {!textual && (
          <div className="col-span-2 flex gap-2 sm:col-span-1">
            <Field label={type === "BP" ? "Systolic" : "Value"} className="flex-1">
              <Input type="number" step="0.1" required value={v1} onChange={(e) => setV1(e.target.value)} placeholder={type === "TEMPERATURE" ? "98.6" : ""} />
            </Field>
            {type === "BP" && (
              <Field label="Diastolic" className="flex-1">
                <Input type="number" required value={v2} onChange={(e) => setV2(e.target.value)} />
              </Field>
            )}
          </div>
        )}
      </div>
      {textual && (
        <Field label={type === "SYMPTOM" ? "Describe what you're feeling" : "Observation"}>
          <Textarea rows={3} required value={text} onChange={(e) => setText(e.target.value)} placeholder={type === "SYMPTOM" ? "e.g. Mild swelling around the knee since morning" : "e.g. Wound site clean, mild erythema, no discharge"} />
        </Field>
      )}
      <Button type="submit" loading={busy} className="w-full">Record & check</Button>
      <AgentOverlay open={busy} kind="monitoring" agent="Monitoring & Escalation Agent" title="Checking against your care plan" steps={["Recording observation in EHR", "Comparing with doctor-approved thresholds", "Deciding whether to alert the care team"]} />
    </form>
  );
}

// ───────────── Documents ─────────────

const DOC_LABEL: Record<string, { label: string; tone: "brand" | "violet" | "amber" | "blue" | "green" | "gray" }> = {
  PATIENT_INSTRUCTIONS: { label: "Recovery plan", tone: "brand" },
  LAB_REPORT: { label: "Lab report", tone: "violet" },
  REFERRAL_PACKAGE: { label: "Referral package", tone: "amber" },
  NURSE_HANDOFF: { label: "Nurse handoff", tone: "blue" },
  CLINICAL_SUMMARY: { label: "Clinical summary", tone: "green" },
  SOURCE_NOTE: { label: "Source image", tone: "gray" },
};

export function DocumentList({ docs, onOpen }: { docs: Doc[]; onOpen: (d: Doc) => void }) {
  if (!docs.length) return <EmptyState icon={<FileText className="size-5" />} title="No documents yet" />;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {docs.map((d, i) => (
        <motion.button key={d.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} onClick={() => onOpen(d)} className="group flex items-center gap-3 rounded-xl border border-line bg-white px-3 py-3 text-left transition hover:border-brand-200 hover:shadow-[var(--shadow-card)]">
          <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-slate-50 text-ink-500 ring-1 ring-line transition group-hover:bg-brand-50 group-hover:text-brand-600">
            <FileText className="size-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{d.title}</div>
            <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-ink-500">
              <Badge tone={DOC_LABEL[d.type]?.tone ?? "gray"}>{DOC_LABEL[d.type]?.label ?? titleCase(d.type)}</Badge>
              {d.reviewStatus && <Badge tone={statusTone(d.reviewStatus)}>{titleCase(d.reviewStatus)}</Badge>}
              <span>{fmtDate(d.createdAt, "d MMM, h:mm a")}</span>
            </div>
          </div>
          <Eye className="size-4 text-ink-400 opacity-0 transition group-hover:opacity-100" />
        </motion.button>
      ))}
    </div>
  );
}

export function DocumentModal({ doc, onClose, canReview, onReviewed }: { doc: Doc | null; onClose: () => void; canReview?: boolean; onReviewed?: () => void }) {
  const [busy, setBusy] = useState(false);
  if (doc?.type === "SOURCE_NOTE") return <SourceViewer doc={doc} onClose={onClose} />;
  return (
    <Modal
      open={!!doc}
      onClose={onClose}
      size="lg"
      title={doc?.title}
      subtitle={doc ? `${DOC_LABEL[doc.type]?.label ?? titleCase(doc.type)} · ${fmtDate(doc.createdAt, "d MMM yyyy, h:mm a")}${doc.engine ? ` · generated with ${doc.engine === "rules" ? "rule engine" : doc.engine}` : ""}` : ""}
      footer={
        doc ? (
          <>
            <a href={documentPdfUrl(doc.id)} target="_blank" rel="noreferrer" className="mr-auto inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-ink-700 ring-1 ring-line transition hover:bg-slate-50">
              <FileDown className="size-4" /> PDF
            </a>
            {canReview && doc.reviewStatus === "PENDING_REVIEW" && (
          <Button
            loading={busy}
            icon={<CheckCircle2 className="size-4" />}
            onClick={async () => {
              setBusy(true);
              try {
                await api(`/api/documents/${doc.id}`, { method: "PATCH", body: {} });
                toast.success("Marked as reviewed");
                onReviewed?.();
                onClose();
              } catch (e) {
                toast.error(e instanceof Error ? e.message : "Failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            Mark as reviewed
          </Button>
            )}
          </>
        ) : undefined
      }
    >
      {doc && <Markdown>{doc.content}</Markdown>}
    </Modal>
  );
}

// ───────────── Agent activity feed ─────────────

export function ActivityFeed({ events, showPatient, limit = 50 }: { events: AgentEvent[]; showPatient?: boolean; limit?: number }) {
  const [filter, setFilter] = useState<string>("ALL");
  const list = useMemo(() => events.filter((e) => filter === "ALL" || e.agent === filter).slice(0, limit), [events, filter, limit]);
  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-1.5">
        {["ALL", "PLANNING", "EXECUTION", "MONITORING", "COMMUNICATION", "INTELLIGENCE", "SERVICE", "HUMAN"].map((a) => (
          <button key={a} onClick={() => setFilter(a)} className={cn("rounded-full px-2.5 py-1 text-[11px] font-medium ring-1 transition", filter === a ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-ink-500 ring-line hover:text-ink-900")}>
            {a === "ALL" ? "All agents" : AGENT_META[a].label}
          </button>
        ))}
      </div>
      {!list.length && <EmptyState icon={<BellRing className="size-5" />} title="No agent activity yet" />}
      <ol className="relative space-y-3 before:absolute before:bottom-2 before:left-[7px] before:top-2 before:w-px before:bg-line">
        {list.map((e, i) => {
          const m = AGENT_META[e.agent] ?? AGENT_META.SERVICE;
          return (
            <motion.li key={e.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.02, 0.4) }} className="relative flex gap-3 pl-0">
              <span className={cn("relative z-10 mt-1.5 size-[15px] shrink-0 rounded-full ring-4 ring-white", e.level === "CRITICAL" ? "bg-rose-500" : e.level === "WARNING" ? "bg-amber-400" : m.dot)} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className={cn("rounded-md px-1.5 py-0.5 text-[10px] font-semibold ring-1", m.color)}>{m.label}</span>
                  {showPatient && e.patient && <span className="text-[11px] font-medium text-ink-700">{e.patient.user.name}</span>}
                  <span className="text-[11px] text-ink-400">{ago(e.createdAt)}</span>
                </div>
                <div className="mt-0.5 text-[13px] font-medium text-ink-900">{e.action}</div>
                {e.detail && <div className="text-xs text-ink-500">{e.detail}</div>}
              </div>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}

