import { AnimatePresence, motion } from "framer-motion";
import { AlertOctagon, Check, CheckCircle2, FileText, Inbox, RotateCcw, Send, Sparkles, Wand2, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, Field, Input, Markdown, Modal, PageHeader, PageSkeleton, Select, Tabs, Textarea, statusTone } from "@/components/ui";
import { AgentOverlay } from "@/components/animations";
import { ReferralTracker } from "@/components/clinical/widgets";
import { CATEGORY_META } from "@/components/clinical/meta";
import { SessionActions } from "@/components/ProviderShared";
import { api, withMinDuration } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { age, cn, fmtDate, fmtWhen, titleCase } from "@/lib/format";
import type { Appointment, Referral } from "@/types";

type Pkg = { id: string; title: string; content: string } | null;
type PatientLite = { id: string; mrn: string; diagnosis: string; procedure?: string | null; dateOfBirth: string; gender: string; user: { name: string; phone?: string | null }; doctor: { name: string; title?: string | null } };
type R = Referral & {
  patientId: string;
  patient: PatientLite;
  package: Pkg;
  declineReason?: string | null;
  declinedByName?: string | null;
  noteToSpecialist?: string | null;
  revision: number;
  updatedAt: string;
};
type Incoming = R & { rejectedByMe: boolean };
type Specialist = { id: string; name: string; organization: string; specialties: string; type: string; hasPortal: boolean };
type Data = { incoming: Incoming[]; outgoing: R[]; specialists: Specialist[] };

type RevForm = { referralType: string; reason: string; sessions: number; frequencyPerWeek: number; durationWeeks: number; preferredStartWithinDays: number; urgency: string; noteToSpecialist: string };
type PlanChange = { category: string; action: string; title: string; details: Record<string, unknown>; include: boolean };

// ───────────── Incoming (I am the specialist) ─────────────

function IncomingRequest({ r, onDone }: { r: Incoming; onDone: () => void }) {
  const [view, setView] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<null | "ACCEPT" | "DECLINE">(null);
  const proposed = r.appointments.filter((a) => a.status === "TENTATIVE");

  async function respond(action: "ACCEPT" | "DECLINE") {
    setBusy(action);
    try {
      await withMinDuration(api(`/api/referrals/${r.id}`, { method: "PATCH", body: { action, note: action === "DECLINE" ? reason : undefined } }), 2400);
      toast.success(action === "ACCEPT" ? "Accepted — sessions confirmed with the patient" : "Rejected — the referring doctor has your reason");
      setRejecting(false);
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <motion.div layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-start justify-between gap-3 p-5">
          <div className="flex items-center gap-3">
            <Avatar name={r.patient.user.name} size={44} />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold">{r.patient.user.name}</span>
                {r.urgency !== "ROUTINE" && <Badge tone="red">{r.urgency}</Badge>}
                {r.revision > 0 && <Badge tone="violet"><RotateCcw className="size-3" /> Revised v{r.revision + 1}</Badge>}
              </div>
              <div className="text-xs text-ink-500">{age(r.patient.dateOfBirth)}y {r.patient.gender} · {r.patient.procedure || r.patient.diagnosis}</div>
              <div className="text-xs text-ink-500">Referred by <b className="text-ink-700">{r.patient.doctor.name}</b> · {fmtWhen(r.updatedAt)}</div>
            </div>
          </div>
          <Badge tone="indigo" dot>Awaiting your decision</Badge>
        </div>
        {r.revision > 0 && (
          <div className="mx-5 mb-4 rounded-xl border border-violet-100 bg-violet-50/60 p-3 text-xs text-violet-900">
            <b>Resubmitted after your feedback.</b> You said: “{r.declineReason}”{r.noteToSpecialist && <><br /><b>Changes made:</b> {r.noteToSpecialist}</>}
          </div>
        )}
        <div className="grid gap-4 border-y border-line bg-slate-50/60 px-5 py-4 sm:grid-cols-3">
          <div><div className="text-[11px] text-ink-400">Service</div><div className="text-sm font-medium">{r.referralType}</div></div>
          <div><div className="text-[11px] text-ink-400">Reason</div><div className="text-sm font-medium">{r.reason}</div></div>
          <div><div className="text-[11px] text-ink-400">Requested</div><div className="text-sm font-medium">{r.sessions} session(s){r.sessions > 1 ? ` · ${r.frequencyPerWeek}/week for ${r.durationWeeks} wk` : ""}</div></div>
        </div>
        {proposed.length > 0 && (
          <div className="px-5 py-4">
            <div className="mb-2 text-xs font-medium text-ink-500">Slots held in your calendar</div>
            <div className="flex flex-wrap gap-1.5">
              {proposed.map((a) => <span key={a.id} className="rounded-lg bg-violet-50 px-2 py-1 text-[11px] font-medium text-violet-700 ring-1 ring-violet-100">#{a.sequence} {fmtDate(a.startsAt, "EEE d MMM, h:mm a")}</span>)}
            </div>
          </div>
        )}
        <div className="flex flex-wrap justify-between gap-2 border-t border-line px-5 py-3">
          <Button variant="outline" size="sm" icon={<FileText className="size-3.5" />} onClick={() => setView(true)} disabled={!r.package}>View patient details</Button>
          <div className="flex gap-2">
            <Button variant="ghost" size="sm" className="text-rose-600 hover:bg-rose-50" icon={<X className="size-3.5" />} onClick={() => setRejecting(true)}>Reject</Button>
            <Button size="sm" icon={<Check className="size-3.5" />} onClick={() => respond("ACCEPT")}>Accept patient</Button>
          </div>
        </div>
      </Card>
      <Modal open={view} onClose={() => setView(false)} size="lg" title={r.package?.title} subtitle="Prepared by the Communication & Documentation agent">
        {r.package && <Markdown>{r.package.content}</Markdown>}
      </Modal>
      <Modal
        open={rejecting}
        onClose={() => setRejecting(false)}
        size="sm"
        title="Reject referral"
        subtitle="Your reason goes back to the referring doctor so they can revise the plan and resend."
        footer={<><Button variant="ghost" onClick={() => setRejecting(false)}>Cancel</Button><Button variant="danger" disabled={reason.trim().length < 5} loading={busy === "DECLINE"} onClick={() => respond("DECLINE")}>Reject with reason</Button></>}
      >
        <Field label="Reason for rejection (required)">
          <Textarea rows={4} autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Need a post-op knee X-ray before starting. Also 3×/week is not possible — I can do 2 sessions per week." />
        </Field>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {["Need a recent X-ray report before starting", "Can only offer 2 sessions per week", "Please start after 2 weeks — wound still healing", "Outside my specialty"].map((s) => (
            <button key={s} onClick={() => setReason((t) => (t ? `${t} ${s}.` : `${s}.`))} className="rounded-full bg-slate-50 px-2.5 py-1 text-[11px] text-ink-700 ring-1 ring-line hover:ring-rose-200">{s}</button>
          ))}
        </div>
      </Modal>
      <AgentOverlay open={busy === "ACCEPT"} kind="booking" agent="Care Execution & Scheduling Agent" title="Confirming the schedule" steps={["Recording your acceptance", "Converting held slots into bookings", "Notifying the patient & referring doctor"]} />
    </motion.div>
  );
}

function InCare({ r, onDone }: { r: Incoming; onDone: () => void }) {
  const sessions = r.appointments.filter((a) => a.status !== "CANCELLED" && a.status !== "TENTATIVE");
  const done = sessions.filter((a) => a.status === "COMPLETED").length;
  return (
    <Card>
      <CardHeader title={`${r.patient.user.name} — ${r.referralType}`} subtitle={`${r.reason} · ${done}/${r.sessions} completed · referred by ${r.patient.doctor.name}`} icon={<CheckCircle2 className="size-4" />} action={<Badge tone={statusTone(r.status)} dot>{titleCase(r.status)}</Badge>} />
      <div className="space-y-2 px-5 pb-5">
        {sessions.map((a) => (
          <div key={a.id} className="flex items-center gap-3 rounded-xl border border-line px-3 py-2">
            <span className="grid size-7 place-items-center rounded-lg bg-slate-50 text-[11px] font-semibold ring-1 ring-line">{a.sequence}</span>
            <div className="min-w-0 flex-1 text-sm">{fmtWhen(a.startsAt)}{a.rescheduledFromId && <span className="ml-1.5 text-[11px] text-amber-600">rescheduled</span>}</div>
            <SessionActions a={a as Appointment} onDone={onDone} />
          </div>
        ))}
      </div>
    </Card>
  );
}

// ───────────── Outgoing (I referred my patient) ─────────────

function ReviseModal({ r, specialists, open, onClose, onDone }: { r: R; specialists: Specialist[]; open: boolean; onClose: () => void; onDone: () => void }) {
  const [form, setForm] = useState<RevForm>({ referralType: r.referralType, reason: r.reason, sessions: r.sessions, frequencyPerWeek: r.frequencyPerWeek, durationWeeks: r.durationWeeks, preferredStartWithinDays: r.preferredStartWithinDays, urgency: r.urgency, noteToSpecialist: "" });
  const [providerId, setProviderId] = useState("");
  const [changes, setChanges] = useState<PlanChange[]>([]);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [engine, setEngine] = useState<"ollama" | "rules">("rules");
  const [revising, setRevising] = useState(false);
  const [sending, setSending] = useState(false);
  const set = (k: keyof RevForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: ["sessions", "frequencyPerWeek", "durationWeeks", "preferredStartWithinDays"].includes(k) ? Number(e.target.value) : e.target.value }));

  async function autoRevise() {
    setRevising(true);
    try {
      const { proposal } = await withMinDuration(api<{ proposal: { explanation: string; referral: RevForm; carePlanChanges: Omit<PlanChange, "include">[]; engine: "ollama" | "rules" } }>(`/api/referrals/${r.id}/revise`, { method: "POST" }), 3000);
      setForm(proposal.referral);
      setChanges(proposal.carePlanChanges.map((c) => ({ ...c, include: true })));
      setExplanation(proposal.explanation);
      setEngine(proposal.engine);
      toast.success("Agent revision ready — review before resending");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Auto-revise failed");
    } finally {
      setRevising(false);
    }
  }

  async function resend() {
    setSending(true);
    try {
      const res = await withMinDuration(
        api<{ routed: boolean }>(`/api/referrals/${r.id}/resend`, {
          body: { referral: form, providerId: providerId || undefined, carePlanChanges: changes.filter((c) => c.include).map(({ include: _i, ...c }) => c), engine },
        }),
        3200,
      );
      if (res.routed) toast.success("Revised referral sent");
      else toast.warning("Saved, but no specialist had capacity — choose another specialist");
      onClose();
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Resend failed");
    } finally {
      setSending(false);
    }
  }

  const matching = specialists.filter((s) => s.specialties.toLowerCase().split(",").some((x) => form.referralType.toLowerCase().includes(x.trim()) || x.includes(form.referralType.toLowerCase().slice(0, 5))));
  const others = specialists.filter((s) => !matching.includes(s));

  return (
    <>
      <Modal
        open={open}
        onClose={onClose}
        size="lg"
        title={`Revise & resend — ${r.referralType}`}
        subtitle={`${r.patient.user.name}${r.declineReason ? ` · rejected by ${r.declinedByName}` : " · no specialist matched"}`}
        footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button onClick={resend} icon={<Send className="size-4" />} disabled={form.referralType.trim().length < 2 || form.reason.trim().length < 3}>Apply changes & resend</Button></>}
      >
        {r.declineReason && (
          <div className="mb-4 rounded-xl border border-rose-100 bg-rose-50/70 p-3 text-sm text-rose-900">
            <div className="mb-0.5 text-[11px] font-semibold uppercase tracking-wide text-rose-600">Specialist’s reason</div>“{r.declineReason}”
          </div>
        )}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-violet-100 bg-gradient-to-r from-violet-50 to-white p-3">
          <div className="text-xs text-violet-900"><b>Let the Care Planning agent revise it.</b> It reads the rejection, updates the referral and proposes any care-plan changes needed.</div>
          <Button size="sm" variant="secondary" icon={<Wand2 className="size-3.5 text-violet-600" />} onClick={autoRevise} disabled={!r.declineReason}>Auto-revise with agent</Button>
        </div>
        {explanation && (
          <p className="mb-4 flex items-start gap-2 rounded-xl bg-brand-50 p-3 text-xs text-brand-900"><Sparkles className="mt-0.5 size-3.5 shrink-0" /> {explanation}</p>
        )}

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Service" className="col-span-2"><Input value={form.referralType} onChange={set("referralType")} /></Field>
          <Field label="Urgency">
            <Select value={form.urgency} onChange={set("urgency")}><option>ROUTINE</option><option>PRIORITY</option><option>URGENT</option></Select>
          </Field>
          <Field label="Start within (days)"><Input type="number" min={0} value={form.preferredStartWithinDays} onChange={set("preferredStartWithinDays")} /></Field>
          <Field label="Reason" className="col-span-2 sm:col-span-4"><Input value={form.reason} onChange={set("reason")} /></Field>
          <Field label="Sessions"><Input type="number" min={1} value={form.sessions} onChange={set("sessions")} /></Field>
          <Field label="Per week"><Input type="number" min={1} max={7} value={form.frequencyPerWeek} onChange={set("frequencyPerWeek")} /></Field>
          <Field label="Weeks"><Input type="number" min={1} value={form.durationWeeks} onChange={set("durationWeeks")} /></Field>
          <Field label="Send to">
            <Select value={providerId} onChange={(e) => setProviderId(e.target.value)}>
              <option value="">Auto-match best specialist</option>
              {matching.length > 0 && <optgroup label="Matching specialty">{matching.map((s) => <option key={s.id} value={s.id}>{s.name}{s.hasPortal ? "" : " (off-platform)"}</option>)}</optgroup>}
              {others.length > 0 && <optgroup label="Other specialists">{others.map((s) => <option key={s.id} value={s.id}>{s.name} · {s.specialties.split(",")[0]}</option>)}</optgroup>}
            </Select>
          </Field>
          <Field label="Note to the specialist (what you changed)" className="col-span-2 sm:col-span-4">
            <Textarea rows={2} value={form.noteToSpecialist} onChange={set("noteToSpecialist")} placeholder="e.g. Reduced to 2 sessions/week as requested; X-ray booked for tomorrow and will be attached." />
          </Field>
        </div>

        {changes.length > 0 && (
          <div className="mt-5">
            <div className="mb-2 text-xs font-semibold text-ink-700">Care-plan changes proposed by the agent</div>
            <div className="space-y-1.5">
              {changes.map((c, i) => {
                const m = CATEGORY_META[c.category] ?? CATEGORY_META.CARE_INSTRUCTION;
                return (
                  <label key={i} className={cn("flex items-center gap-3 rounded-xl border px-3 py-2 text-sm transition", c.include ? "border-brand-200 bg-brand-50/40" : "border-line opacity-60")}>
                    <input type="checkbox" checked={c.include} onChange={(e) => setChanges((l) => l.map((x, j) => (j === i ? { ...x, include: e.target.checked } : x)))} className="size-4 accent-[#4f46e5]" />
                    <m.icon className={cn("size-4", m.color)} />
                    <span className="flex-1">{c.action !== "ADD" && <b>{c.action} · </b>}{c.title}</span>
                    <Badge tone="gray">{m.label}</Badge>
                  </label>
                );
              })}
            </div>
            <p className="mt-1.5 text-[11px] text-ink-500">Checked items are added to the active care plan as an approved amendment and executed (e.g. tests booked) before the referral is resent.</p>
          </div>
        )}
      </Modal>
      <AgentOverlay open={revising} kind="planning" agent="Care Planning & Coordination Agent" title="Revising the referral" steps={["Reading the specialist's rejection reason", "Reviewing the patient's active care plan", "Adjusting the referral request", "Proposing care-plan changes"]} />
      <AgentOverlay open={sending} kind="send" agent="Care Execution & Scheduling Agent" title="Resending the referral" steps={["Applying care-plan changes", "Updating the referral & care plan", "Holding new slots with the specialist", "Rebuilding the referral package", "Routing the revised request"]} />
    </>
  );
}

function Outgoing({ r, specialists, onDone, focused }: { r: R; specialists: Specialist[]; onDone: () => void; focused: boolean }) {
  const [revise, setRevise] = useState(false);
  const [pkg, setPkg] = useState(false);
  const needsAction = r.status === "DECLINED" || r.status === "CREATED";
  useEffect(() => {
    if (focused) document.getElementById(`ref-${r.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focused, r.id]);
  return (
    <div id={`ref-${r.id}`} className={cn("rounded-2xl transition", focused && "ring-4 ring-brand-200")}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <a href={`/doctor/patients/${r.patientId}?tab=execution`} className="text-xs font-semibold text-brand-700 hover:underline">{r.patient.user.name}</a>
        {r.revision > 0 && <Badge tone="violet"><RotateCcw className="size-3" /> Revision v{r.revision + 1}</Badge>}
      </div>
      {needsAction && (
        <div className="mb-2 rounded-2xl border border-rose-200 bg-rose-50/70 p-4">
          <div className="flex items-start gap-3">
            <AlertOctagon className="mt-0.5 size-5 shrink-0 text-rose-600" />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-rose-900">{r.status === "DECLINED" ? `Rejected by ${r.declinedByName ?? "specialist"}` : "No specialist available"}</div>
              <p className="mt-0.5 text-sm text-rose-800">{r.status === "DECLINED" ? `“${r.declineReason}”` : "No specialist with capacity matched this referral. Choose one and resend."}</p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="secondary" icon={<RotateCcw className="size-3.5" />} onClick={() => setRevise(true)}>Edit & resend</Button>
            {r.status === "DECLINED" && <Button size="sm" icon={<Wand2 className="size-3.5" />} onClick={() => setRevise(true)}>Auto-revise with agent</Button>}
          </div>
        </div>
      )}
      <ReferralTracker referral={r} onOpenDoc={r.package ? () => setPkg(true) : undefined} />
      <ReviseModal r={r} specialists={specialists} open={revise} onClose={() => setRevise(false)} onDone={onDone} />
      <Modal open={pkg} onClose={() => setPkg(false)} size="lg" title={r.package?.title}>{r.package && <Markdown>{r.package.content}</Markdown>}</Modal>
    </div>
  );
}

function ReferralsHub() {
  const [params] = useSearchParams();
  const focus = params.get("focus");
  const { data, reload } = useApi<Data>("/api/referrals", { poll: 20000 });
  const tabParam = params.get("tab");
  const [tab, setTab] = useState<"incoming" | "outgoing">(tabParam === "incoming" ? "incoming" : "outgoing");
  useEffect(() => {
    if (tabParam === "incoming") setTab("incoming");
    else if (tabParam === "outgoing" || focus) setTab("outgoing");
  }, [tabParam, focus]);
  if (!data) return <PageSkeleton />;

  const pending = data.incoming.filter((r) => r.status === "SENT" && !r.rejectedByMe);
  const inCare = data.incoming.filter((r) => ["ACCEPTED", "SCHEDULED", "IN_TREATMENT"].includes(r.status) && !r.rejectedByMe);
  const closed = data.incoming.filter((r) => r.status === "COMPLETED" || r.rejectedByMe);
  const needAction = data.outgoing.filter((r) => r.status === "DECLINED" || r.status === "CREATED");

  return (
    <div>
      <PageHeader
        eyebrow="Doctor-to-doctor referrals"
        title="Referrals"
        subtitle="Send patients to specialist doctors, and accept or reject the patients referred to you. Rejections come back with a reason so the plan can be revised and resent."
      />
      <div className="mb-5">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "outgoing", label: "Sent by me", icon: <Send className="size-4" />, count: needAction.length },
            { id: "incoming", label: "Requests to me", icon: <Inbox className="size-4" />, count: pending.length },
          ]}
        />
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
          {tab === "outgoing" && (
            <div className="space-y-4">
              {!data.outgoing.length && <Card className="p-5"><EmptyState icon={<Send className="size-5" />} title="No referrals sent yet" text="Add a referral to a patient's care plan (e.g. “Physiotherapy three times a week for 4 weeks”) — the agents find a specialist and send the request." /></Card>}
              <div className="grid gap-5 lg:grid-cols-2">
                {[...needAction, ...data.outgoing.filter((r) => !needAction.includes(r))].map((r) => <Outgoing key={r.id} r={r} specialists={data.specialists} onDone={reload} focused={focus === r.id} />)}
              </div>
            </div>
          )}
          {tab === "incoming" && (
            <div className="space-y-6">
              <section className="space-y-3">
                <h3 className="text-sm font-semibold text-ink-700">Awaiting your decision ({pending.length})</h3>
                {!pending.length && <Card className="p-5"><EmptyState icon={<Inbox className="size-5" />} title="No pending requests" text="Referral requests from other doctors for your specialty appear here." /></Card>}
                {pending.map((r) => <IncomingRequest key={r.id} r={r} onDone={reload} />)}
              </section>
              {inCare.length > 0 && (
                <section className="space-y-3">
                  <h3 className="text-sm font-semibold text-ink-700">Patients in your care ({inCare.length})</h3>
                  {inCare.map((r) => <InCare key={r.id} r={r} onDone={reload} />)}
                </section>
              )}
              {closed.length > 0 && (
                <section className="space-y-2">
                  <h3 className="text-sm font-semibold text-ink-700">Closed</h3>
                  {closed.map((r) => (
                    <div key={r.id} className="flex items-center justify-between rounded-xl border border-line bg-white px-4 py-2.5 text-sm">
                      <span>{r.patient.user.name} · {r.referralType} <span className="text-ink-500">from {r.patient.doctor.name}</span></span>
                      <Badge tone={r.rejectedByMe ? "gray" : "green"}>{r.rejectedByMe ? "Rejected by you" : "Completed"}</Badge>
                    </div>
                  ))}
                </section>
              )}
            </div>
          )}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export default function DoctorReferrals() {
  return (
    <Suspense>
      <ReferralsHub />
    </Suspense>
  );
}
