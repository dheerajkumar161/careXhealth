import { AnimatePresence, motion } from "framer-motion";
import {
  Activity, ArrowLeft, BrainCircuit, ImagePlus, Loader2, X, CalendarClock, ClipboardCheck, ClipboardList, FileText, FlaskConical, HeartPulse, LayoutGrid, Pill, Send, ShieldAlert, Sparkles, Stethoscope, Wand2,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useSearchParams } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Avatar, Badge, Button, Card, CardHeader, EmptyState, Field, Markdown, Modal, PageSkeleton, Tabs, Textarea, statusTone } from "./ui";
import { AgentOverlay } from "./animations";
import { CarePlanEditor, CarePlanView, PlanHistory } from "./clinical/CarePlan";
import { PendingReleaseBanner, ReassignNurseButton, ReleaseDecisionPanel, ReleaseHistory, RequestReleaseButton } from "./clinical/NurseHandover";
import { ActivityFeed, AlertList, AppointmentRow, DocumentList, DocumentModal, DoseList, ObservationForm, ReferralTracker, VitalsGrid } from "./clinical/widgets";
import { api, withMinDuration } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { fileToDataUrl } from "@/lib/image";
import { age, cn, fmtDate, fmtWhen, titleCase } from "@/lib/format";
import type { Doc, PatientRecord, PlanItem, Task } from "@/types";

type TabId = "overview" | "plan" | "execution" | "monitoring" | "documents" | "activity";

const EXAMPLE = "Patient underwent right total knee replacement. Take Tab Cefuroxime 500mg twice daily for 7 days. Check CBC after 5 days. Follow up after 2 weeks. Physiotherapy required three times a week for 4 weeks. Refer to dietitian for weight management. Avoid strenuous activity. Notify nurse if temperature exceeds 101°F.";

const TASK_ICON: Record<string, typeof Pill> = { MEDICATION: Pill, INVESTIGATION: FlaskConical, FOLLOW_UP: Stethoscope, REFERRAL: Send, MONITORING: Activity };

type Attached = { id: string; name: string; dataUrl: string };
const MAX_ATTACHMENTS = 4;

function PlanComposer({ patientId, kind, onDone }: { patientId: string; kind: "INITIAL" | "AMENDMENT"; onDone: () => void }) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<Attached[]>([]);
  const [dragging, setDragging] = useState(false);
  const [preparing, setPreparing] = useState(false);
  const [preview, setPreview] = useState<Attached | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function addFiles(list: FileList | File[]) {
    const images = Array.from(list).filter((f) => f.type.startsWith("image/"));
    if (!images.length) return toast.error("Attach images only — a photo or scan of the note, prescription or order");
    const room = MAX_ATTACHMENTS - files.length;
    if (room <= 0) return toast.error(`You can attach up to ${MAX_ATTACHMENTS} images`);
    setPreparing(true);
    try {
      const added: Attached[] = [];
      for (const f of images.slice(0, room)) added.push({ id: `${f.name}-${f.size}-${Date.now()}`, name: f.name || "pasted-image.jpg", dataUrl: await fileToDataUrl(f) });
      setFiles((cur) => [...cur, ...added]);
      if (images.length > room) toast.warning(`Only the first ${room} image(s) were added`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not read that image");
    } finally {
      setPreparing(false);
    }
  }

  function onPaste(e: React.ClipboardEvent) {
    const pasted = Array.from(e.clipboardData.items).filter((i) => i.type.startsWith("image/")).map((i) => i.getAsFile()).filter((f): f is File => !!f);
    if (pasted.length) {
      e.preventDefault();
      addFiles(pasted);
    }
  }

  const canSubmit = files.length > 0 || text.trim().length >= 10;

  async function submit() {
    setBusy(true);
    try {
      await withMinDuration(api(`/api/patients/${patientId}/care-plans`, { body: { instructions: text, kind, attachments: files.map(({ name, dataUrl }) => ({ name, dataUrl })) } }), files.length ? 4200 : 3600);
      toast.success(kind === "INITIAL" ? "Draft care plan ready for your review" : "Amendment drafted — review and approve");
      setText("");
      setFiles([]);
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Planning failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line bg-gradient-to-r from-brand-50 via-white to-white px-5 py-4">
        <div className="flex items-center gap-2">
          <div className="grid size-9 place-items-center rounded-xl bg-violet-100 text-violet-600"><BrainCircuit className="size-4" /></div>
          <div>
            <h3 className="text-[15px] font-semibold">{kind === "INITIAL" ? "Discharge instructions" : "Clinical decision / order change"}</h3>
            <p className="text-xs text-ink-500">
              {kind === "INITIAL"
                ? "Type the instructions, attach a photo or scan of the discharge note / prescription, or both. The Care Planning agent reads everything, structures it, and waits for your approval."
                : "Type or attach the decision, e.g. “Stop Cefuroxime. Start Tab Amoxiclav 625mg twice daily for 5 days. Repeat CBC in 3 days.”"}
            </p>
          </div>
        </div>
      </div>
      <div
        className={cn("relative p-5 transition", dragging && "bg-brand-50/60")}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }}
        onDrop={(e) => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
      >
        <Textarea rows={kind === "INITIAL" ? 6 : 3} value={text} onChange={(e) => setText(e.target.value)} onPaste={onPaste} placeholder={kind === "INITIAL" ? `${EXAMPLE}\n\n…or attach / paste a photo of the handwritten note.` : "Enter your decision, or attach an image…"} />

        {/* Attachments */}
        <div className="mt-3 flex flex-wrap items-stretch gap-2">
          <AnimatePresence>
            {files.map((f) => (
              <motion.div key={f.id} layout initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.9 }} className="group relative h-24 w-24 overflow-hidden rounded-xl border border-line bg-slate-50">
                                <img src={f.dataUrl} alt={f.name} className="size-full cursor-zoom-in object-cover" onClick={() => setPreview(f)} />
                <span className="absolute inset-x-0 bottom-0 truncate bg-gradient-to-t from-black/60 to-transparent px-1.5 pb-1 pt-3 text-[10px] text-white">{f.name}</span>
                <button onClick={() => setFiles((cur) => cur.filter((x) => x.id !== f.id))} className="absolute right-1 top-1 grid size-5 place-items-center rounded-full bg-white/90 text-ink-700 shadow opacity-0 transition group-hover:opacity-100 hover:text-rose-600" aria-label={`Remove ${f.name}`}>
                  <X className="size-3" />
                </button>
              </motion.div>
            ))}
          </AnimatePresence>
          {files.length < MAX_ATTACHMENTS && (
            <button onClick={() => inputRef.current?.click()} disabled={preparing} className="flex h-24 w-full min-w-[220px] flex-1 items-center justify-center gap-3 rounded-xl border-2 border-dashed border-line bg-white px-4 text-left text-xs text-ink-500 transition hover:border-brand-300 hover:bg-brand-50/40 sm:w-auto">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600">{preparing ? <Loader2 className="size-4 animate-spin" /> : <ImagePlus className="size-4" />}</span>
              <span>
                <b className="block text-ink-900">Attach a photo or scan</b>
                Discharge note, prescription or order — click, drag & drop, or paste (Ctrl+V). Up to {MAX_ATTACHMENTS} images.
              </span>
            </button>
          )}
          <input ref={inputRef} type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }} />
        </div>
        {dragging && <div className="pointer-events-none absolute inset-3 grid place-items-center rounded-2xl border-2 border-dashed border-brand-400 bg-brand-50/80 text-sm font-semibold text-brand-700">Drop images to attach</div>}

        <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
          {kind === "INITIAL" ? (
            <button onClick={() => setText(EXAMPLE)} className="text-xs font-medium text-brand-600 hover:underline">Use example note</button>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {["No change — continue current plan.", "Repeat CBC in 3 days.", "Refer to home nursing for daily wound dressing for 1 week."].map((s) => (
                <button key={s} onClick={() => setText((t) => (t ? t + " " : "") + s)} className="rounded-full bg-slate-50 px-2.5 py-1 text-[11px] text-ink-700 ring-1 ring-line hover:ring-brand-300">{s}</button>
              ))}
            </div>
          )}
          <Button onClick={submit} disabled={!canSubmit || preparing} icon={<Wand2 className="size-4" />}>
            {kind === "INITIAL" ? "Generate care plan" : "Draft amendment"}{files.length ? ` (${files.length} image${files.length > 1 ? "s" : ""})` : ""}
          </Button>
        </div>
      </div>
      <Modal open={!!preview} onClose={() => setPreview(null)} size="lg" title={preview?.name}>
                {preview && <img src={preview.dataUrl} alt={preview.name} className="w-full rounded-xl" />}
      </Modal>
      <AgentOverlay
        open={busy}
        kind="planning"
        agent="Care Planning & Coordination Agent"
        title={kind === "INITIAL" ? "Understanding discharge instructions" : "Structuring your decision"}
        steps={[
          ...(files.length ? [`Reading ${files.length} attached image${files.length > 1 ? "s" : ""} (vision)`, "Expanding prescription shorthand"] : []),
          ...(kind === "INITIAL"
            ? ["Extracting medications, tests & follow-ups", "Identifying referral requirements", "Defining red flags & monitoring rules", "Suggesting diet, exercise & restrictions", "Preparing draft for doctor review"]
            : ["Comparing with the active plan", "Creating structured changes"]),
        ]}
      />
    </Card>
  );
}

function TaskBoard({ tasks }: { tasks: Task[] }) {
  if (!tasks.length) return <EmptyState icon={<ClipboardList className="size-5" />} title="No tasks yet" text="Tasks appear once a care plan is approved." />;
  const visible = tasks.filter((t) => t.status !== "CANCELLED");
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {visible.map((t, i) => {
        const Icon = TASK_ICON[t.type] ?? ClipboardList;
        return (
          <motion.div key={t.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="flex items-center gap-3 rounded-xl border border-line bg-white px-3 py-2.5">
            <div className="grid size-8 shrink-0 place-items-center rounded-lg bg-slate-50 text-ink-500 ring-1 ring-line"><Icon className="size-4" /></div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-medium">{t.title}</div>
              <div className="text-[11px] text-ink-500">{titleCase(t.type)}{t.dueDate ? ` · ${fmtWhen(t.dueDate)}` : ""}</div>
            </div>
            <Badge tone={statusTone(t.status)}>{titleCase(t.status)}</Badge>
          </motion.div>
        );
      })}
    </div>
  );
}

export function PatientWorkspace({ id, role }: { id: string; role: "DOCTOR" | "NURSE" }) {
  const [params] = useSearchParams();
  const { data, reload, error } = useApi<PatientRecord>(`/api/patients/${id}`, { poll: 30000 });
  const [tab, setTab] = useState<TabId>((params.get("tab") as TabId) || "overview");
  const tabParam = params.get("tab") as TabId | null;
  const docParam = params.get("doc");
  useEffect(() => {
    if (tabParam) setTab(tabParam);
  }, [tabParam]);
  const [doc, setDoc] = useState<Doc | null>(null);
  const [intel, setIntel] = useState<null | "HANDOFF" | "SUMMARY">(null);
  const [intelDoc, setIntelDoc] = useState<Doc | null>(null);
  const [dayFilter, setDayFilter] = useState<"today" | "week">("today");
  const [removing, setRemoving] = useState<PlanItem | null>(null);
  const [removeReason, setRemoveReason] = useState("");
  const [removeBusy, setRemoveBusy] = useState(false);

  useEffect(() => {
    const h = () => reload();
    window.addEventListener("agents:cycle", h);
    return () => window.removeEventListener("agents:cycle", h);
  }, [reload]);

  // Deep link from a notification: open that document once the record has loaded
  useEffect(() => {
    if (!docParam || !data) return;
    const target = data.documents.find((d) => d.id === docParam);
    if (target) setDoc(target);
  }, [docParam, data?.documents.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const activeItems = useMemo(() => (data?.plans ?? []).filter((p) => p.status === "ACTIVE").flatMap((p) => p.items.map((i) => ({ ...i, planKind: p.kind }))), [data]);

  if (error) return <EmptyState icon={<ShieldAlert className="size-5" />} title="Unable to open this record" text={error} action={<Link to={`/${role.toLowerCase()}`}><Button variant="secondary">Back</Button></Link>} />;
  if (!data) return <PageSkeleton />;

  const { patient } = data;
  const draft = data.plans.find((p) => p.status === "DRAFT");
  const hasActive = data.plans.some((p) => p.status === "ACTIVE");
  const openAlerts = data.alerts.filter((a) => a.status !== "RESOLVED");
  const upcoming = data.appointments.filter((a) => new Date(a.startsAt) >= new Date() && ["BOOKED", "TENTATIVE"].includes(a.status));
  const today = new Date().toDateString();
  const doses = data.doses.filter((d) => d.status !== "CANCELLED" && (dayFilter === "today" ? new Date(d.scheduledAt).toDateString() === today : true));
  const base = role === "DOCTOR" ? "/doctor" : "/nurse";
  const pendingRelease = data.releaseRequests.find((r) => r.status === "PENDING" || r.status === "AWAITING_NURSE");

  async function removeItem() {
    if (!removing) return;
    setRemoveBusy(true);
    try {
      const res = await withMinDuration(api<{ cancelled: string[] }>(`/api/care-plan-items/${removing.id}`, { method: "DELETE", body: { reason: removeReason } }), 1800);
      toast.success(`Removed “${removing.title}”`, { description: res.cancelled.length ? `Cancelled: ${res.cancelled.join(", ")}` : "Nothing was scheduled for it" });
      setRemoving(null);
      setRemoveReason("");
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not remove");
    } finally {
      setRemoveBusy(false);
    }
  }

  async function runIntel(kind: "HANDOFF" | "SUMMARY") {
    setIntel(kind);
    try {
      const res = await withMinDuration(api<{ document: Doc }>(`/api/patients/${id}/intelligence`, { body: { kind } }), 3000);
      setIntelDoc(res.document);
      reload();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setIntel(null);
    }
  }

  return (
    <div>
      <Link to={`${base}/patients`} className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-ink-500 hover:text-ink-900">
        <ArrowLeft className="size-3.5" /> All patients
      </Link>

      {/* Header */}
      <Card className="mb-5 overflow-hidden">
        <div className="flex flex-col gap-5 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-4">
            <Avatar name={patient.user.name} size={56} tone={patient.riskLevel === "HIGH" ? "amber" : "brand"} />
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-xl font-bold">{patient.user.name}</h1>
                <Badge tone={statusTone(patient.status)} dot>{titleCase(patient.status)}</Badge>
                <Badge tone={statusTone(patient.riskLevel)}>{titleCase(patient.riskLevel)} risk</Badge>
              </div>
              <p className="mt-0.5 text-sm text-ink-500">
                {age(patient.dateOfBirth)}y · {patient.gender} · MRN {patient.mrn}{patient.bloodGroup ? ` · ${patient.bloodGroup}` : ""}
              </p>
              <p className="mt-1 text-sm font-medium text-ink-900">{patient.diagnosis}{patient.procedure ? <span className="font-normal text-ink-500"> — {patient.procedure}</span> : null}</p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs sm:grid-cols-4 lg:text-right">
            <div><div className="text-ink-400">Doctor</div><div className="font-medium">{patient.doctor.name}</div></div>
            <div><div className="text-ink-400">Nurse</div><div className="font-medium">{patient.nurse?.name ?? "—"}</div></div>
            <div><div className="text-ink-400">Discharged</div><div className="font-medium">{fmtDate(patient.dischargeDate)}</div></div>
            <div><div className="text-ink-400">Allergies</div><div className={cn("font-medium", patient.allergies && "text-rose-600")}>{patient.allergies || "None known"}</div></div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 border-t border-line bg-slate-50/60 px-5 py-3">
          <span className="mr-1 text-xs font-medium text-ink-500">Clinical Intelligence:</span>
          <Button size="sm" variant="secondary" icon={<ClipboardList className="size-3.5" />} onClick={() => runIntel("HANDOFF")}>Generate nurse handoff</Button>
          <Button size="sm" variant="secondary" icon={<Sparkles className="size-3.5" />} onClick={() => runIntel("SUMMARY")}>Recovery summary</Button>
          {((role === "DOCTOR" && !patient.nurse) || (role === "NURSE" && patient.nurse?.id === data.viewer.id && !pendingRelease)) && (
            <div className="ml-auto flex items-center gap-2">
              <span className="text-xs font-medium text-ink-500">Care team:</span>
              {role === "NURSE" && <RequestReleaseButton patientId={id} currentNurseId={data.viewer.id} onDone={reload} />}
              {role === "DOCTOR" && <ReassignNurseButton patientId={id} onDone={reload} />}
            </div>
          )}
        </div>
      </Card>

      {pendingRelease && role === "DOCTOR" && pendingRelease.status === "AWAITING_NURSE" && <PendingReleaseBanner request={pendingRelease} onDone={reload} />}
      {pendingRelease && role === "DOCTOR" && pendingRelease.status === "PENDING" && <ReleaseDecisionPanel request={pendingRelease} onDone={reload} />}
      {pendingRelease && role === "NURSE" && <PendingReleaseBanner request={pendingRelease} onDone={reload} />}

      <div className="mb-5">
        <Tabs<TabId>
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "overview", label: "Overview", icon: <LayoutGrid className="size-4" /> },
            { id: "plan", label: "Care plan", icon: <ClipboardCheck className="size-4" />, count: draft ? 1 : 0 },
            { id: "execution", label: "Schedule & tasks", icon: <CalendarClock className="size-4" /> },
            { id: "monitoring", label: "Monitoring", icon: <HeartPulse className="size-4" />, count: openAlerts.length },
            { id: "documents", label: "Documents", icon: <FileText className="size-4" />, count: data.documents.filter((d) => d.reviewStatus === "PENDING_REVIEW").length },
            { id: "activity", label: "Agent activity", icon: <Activity className="size-4" /> },
          ]}
        />
      </div>

      <AnimatePresence mode="wait">
        <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.18 }}>
          {tab === "overview" && (
            <div className="grid gap-5 xl:grid-cols-3">
              <div className="space-y-5 xl:col-span-2">
                {!hasActive && !draft && (
                  <Card className="p-5">
                    <EmptyState icon={<BrainCircuit className="size-5" />} title="No care plan yet" text={role === "DOCTOR" ? "Write the discharge instructions and the Care Planning agent will structure them." : "The treating doctor has not yet approved a discharge plan."} action={role === "DOCTOR" ? <Button onClick={() => setTab("plan")}>Write discharge plan</Button> : undefined} />
                  </Card>
                )}
                {draft && role === "DOCTOR" && (
                  <button onClick={() => setTab("plan")} className="flex w-full items-center gap-3 rounded-2xl border border-violet-200 bg-violet-50/60 p-4 text-left">
                    <Sparkles className="size-5 text-violet-600" />
                    <span className="flex-1 text-sm"><b>Draft care plan ready.</b> Review the Planning agent’s structure and approve to activate execution.</span>
                    <Button size="sm">Review</Button>
                  </button>
                )}
                <Card>
                  <CardHeader title="Latest vitals" icon={<HeartPulse className="size-4" />} subtitle={`Medication adherence (7 days): ${data.adherence === null ? "—" : data.adherence + "%"}`} />
                  <div className="px-5 pb-5"><VitalsGrid observations={data.observations} rules={data.rules ?? []} /></div>
                </Card>
                {hasActive && (
                  <Card>
                    <CardHeader title="Active care plan" icon={<ClipboardCheck className="size-4" />} action={<Button size="sm" variant="ghost" onClick={() => setTab("plan")}>Details</Button>} />
                    <div className="px-5 pb-5"><CarePlanView items={activeItems} compact /></div>
                  </Card>
                )}
              </div>
              <div className="space-y-5">
                <Card>
                  <CardHeader title="Active alerts" icon={<ShieldAlert className="size-4" />} />
                  <div className="px-5 pb-5"><AlertList alerts={data.alerts.slice(0, 5)} onChange={reload} /></div>
                </Card>
                {data.releaseRequests.some((r) => r.status !== "PENDING" && r.status !== "AWAITING_NURSE") && (
                  <Card>
                    <CardHeader title="Nurse assignment history" subtitle="Release requests and reassignments, each with a handoff" icon={<ClipboardList className="size-4" />} />
                    <div className="px-5 pb-5"><ReleaseHistory requests={data.releaseRequests} /></div>
                  </Card>
                )}
                <Card>
                  <CardHeader title="Upcoming" icon={<CalendarClock className="size-4" />} />
                  <div className="space-y-2 px-5 pb-5">
                    {!upcoming.length && <p className="text-sm text-ink-500">Nothing scheduled.</p>}
                    {upcoming.slice(0, 5).map((a) => <AppointmentRow key={a.id} a={a} />)}
                  </div>
                </Card>
              </div>
            </div>
          )}

          {tab === "plan" && (
            <div className="space-y-5">
              {draft && role === "DOCTOR" && <CarePlanEditor key={draft.id} plan={draft} onDone={reload} sources={data.documents.filter((d) => d.type === "SOURCE_NOTE" && (d.data as { carePlanId?: string } | null)?.carePlanId === draft.id)} />}
              {draft && role === "NURSE" && <Card className="p-5 text-sm text-ink-700">A draft plan is awaiting the doctor’s approval.</Card>}
              {!draft && role === "DOCTOR" && <PlanComposer patientId={id} kind={hasActive ? "AMENDMENT" : "INITIAL"} onDone={reload} />}
              {hasActive && (
                <Card>
                  <CardHeader title="Active care plan" subtitle={role === "DOCTOR" ? "Doctor-approved. AI-suggested items carry a ✦ mark. Use the bin icon to remove an item — the agents cancel its doses, bookings or referral." : "Doctor-approved. AI-suggested items carry a ✦ mark."} icon={<ClipboardCheck className="size-4" />} />
                  <div className="px-5 pb-5"><CarePlanView items={activeItems} onRemove={role === "DOCTOR" ? setRemoving : undefined} /></div>
                </Card>
              )}
              {data.plans.some((p) => p.status !== "DRAFT") && (
                <Card>
                  <CardHeader title="Plan history" subtitle="Closed loop: every doctor decision becomes a versioned amendment" icon={<FileText className="size-4" />} />
                  <div className="px-5 pb-5"><PlanHistory plans={data.plans} /></div>
                </Card>
              )}
            </div>
          )}

          {tab === "execution" && (
            <div className="grid gap-5 xl:grid-cols-3">
              <div className="space-y-5 xl:col-span-2">
                <Card>
                  <CardHeader title="Care tasks" subtitle="Created and tracked by the Execution agent" icon={<ClipboardList className="size-4" />} />
                  <div className="px-5 pb-5"><TaskBoard tasks={data.tasks} /></div>
                </Card>
                {data.referrals.length > 0 && (
                  <div className="space-y-3">
                    <h3 className="flex items-center gap-2 text-sm font-semibold"><Send className="size-4 text-amber-600" /> Referrals & external care</h3>
                    {data.referrals.map((r) => <ReferralTracker key={r.id} referral={r} onOpenDoc={(docId) => setDoc(data.documents.find((d) => d.id === docId) ?? null)} />)}
                  </div>
                )}
              </div>
              <div className="space-y-5">
                <Card>
                  <CardHeader title="Medication schedule" icon={<Pill className="size-4" />} action={
                    <div className="flex rounded-lg bg-slate-100 p-0.5 text-[11px] font-medium">
                      {(["today", "week"] as const).map((f) => (
                        <button key={f} onClick={() => setDayFilter(f)} className={cn("rounded-md px-2 py-1", dayFilter === f ? "bg-white shadow-sm" : "text-ink-500")}>{f === "today" ? "Today" : "±7 days"}</button>
                      ))}
                    </div>
                  } />
                  <div className="max-h-[420px] overflow-y-auto px-5 pb-5"><DoseList doses={doses} canRecord={role === "NURSE"} onChange={reload} /></div>
                </Card>
                <Card>
                  <CardHeader title="Appointments" icon={<CalendarClock className="size-4" />} />
                  <div className="max-h-[480px] space-y-2 overflow-y-auto px-5 pb-5">
                    {!data.appointments.length && <p className="text-sm text-ink-500">None booked.</p>}
                    {data.appointments.filter((a) => a.status !== "CANCELLED").map((a) => <AppointmentRow key={a.id} a={a} />)}
                  </div>
                </Card>
              </div>
            </div>
          )}

          {tab === "monitoring" && (
            <div className="grid gap-5 xl:grid-cols-3">
              <div className="space-y-5 xl:col-span-2">
                <Card>
                  <CardHeader title="Alerts & escalations" subtitle="Unacknowledged alerts escalate nurse → doctor → emergency automatically" icon={<ShieldAlert className="size-4" />} />
                  <div className="px-5 pb-5"><AlertList alerts={data.alerts} onChange={reload} /></div>
                </Card>
                <Card>
                  <CardHeader title="Vitals trend" icon={<HeartPulse className="size-4" />} />
                  <div className="px-5 pb-5"><VitalsGrid observations={data.observations} rules={data.rules ?? []} /></div>
                </Card>
                <Card>
                  <CardHeader title="Observation log" icon={<Activity className="size-4" />} />
                  <div className="max-h-[360px] overflow-y-auto px-5 pb-5">
                    <table className="w-full text-sm">
                      <tbody>
                        {data.observations.map((o) => (
                          <tr key={o.id} className="border-t border-line first:border-0">
                            <td className="py-2 pr-3 text-xs text-ink-500">{fmtWhen(o.recordedAt)}</td>
                            <td className="py-2 pr-3 text-xs font-medium">{titleCase(o.type)}</td>
                            <td className="py-2 pr-3">{o.value !== null && o.value !== undefined ? `${o.value}${o.value2 ? "/" + o.value2 : ""} ${o.unit ?? ""}` : <span className="text-ink-700">{o.text}</span>}</td>
                            <td className="py-2 pr-3 text-xs text-ink-500">{o.recordedBy?.name ?? o.source.toLowerCase()}</td>
                            <td className="py-2 text-right">{o.flagged && <Badge tone="red">flagged</Badge>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </div>
              <div className="space-y-5">
                <Card>
                  <CardHeader title="Record observation" subtitle="Evaluated instantly by the Monitoring agent" icon={<Stethoscope className="size-4" />} />
                  <div className="px-5 pb-5"><ObservationForm patientId={id} onDone={reload} clinician /></div>
                </Card>
                <Card>
                  <CardHeader title="Active monitoring rules" subtitle="Doctor-defined red flags + system safety nets" icon={<ShieldAlert className="size-4" />} />
                  <div className="space-y-2 px-5 pb-5">
                    {!data.rules.length && <p className="text-sm text-ink-500">Rules are registered when a plan is approved.</p>}
                    {data.rules.map((r) => (
                      <div key={r.id} className="rounded-xl border border-line px-3 py-2">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-[13px] font-medium">{r.description}</span>
                          <Badge tone={r.source === "SYSTEM_DEFAULT" ? "gray" : "brand"}>{r.source === "SYSTEM_DEFAULT" ? "System" : "Doctor"}</Badge>
                        </div>
                        <div className="mt-0.5 text-[11px] text-ink-500">{r.action.replace("_", " ").toLowerCase()} · {r.severity.toLowerCase()}</div>
                      </div>
                    ))}
                  </div>
                </Card>
              </div>
            </div>
          )}

          {tab === "documents" && (
            <Card>
              <CardHeader title="Clinical documents" subtitle="Generated, packaged and routed by the Communication & Documentation agent" icon={<FileText className="size-4" />} />
              <div className="px-5 pb-5"><DocumentList docs={data.documents} onOpen={setDoc} /></div>
            </Card>
          )}

          {tab === "activity" && (
            <Card>
              <CardHeader title="Agent activity" subtitle="Every agent, service and clinician action — fully auditable" icon={<Activity className="size-4" />} />
              <div className="px-5 pb-5"><ActivityFeed events={data.events} limit={150} /></div>
            </Card>
          )}
        </motion.div>
      </AnimatePresence>

      <DocumentModal doc={doc} onClose={() => setDoc(null)} canReview={role === "DOCTOR"} onReviewed={reload} />
      <Modal
        open={!!removing}
        onClose={() => setRemoving(null)}
        size="sm"
        title="Remove from active care plan"
        subtitle={removing?.title}
        footer={<><Button variant="ghost" onClick={() => setRemoving(null)}>Keep it</Button><Button variant="danger" loading={removeBusy} disabled={removeReason.trim().length < 3} onClick={removeItem}>Remove & cancel activity</Button></>}
      >
        <p className="mb-3 text-sm text-ink-700">The Execution agent will cancel everything set in motion for this item — pending doses, booked tests or appointments, the referral, or its monitoring rule — and the patient will be notified.</p>
        <Field label="Reason (recorded in the audit log)">
          <Textarea rows={3} autoFocus value={removeReason} onChange={(e) => setRemoveReason(e.target.value)} placeholder="e.g. Course no longer needed — switched to oral antibiotics" />
        </Field>
      </Modal>
      <AgentOverlay
        open={!!intel}
        kind={intel === "HANDOFF" ? "handoff" : "document"}
        agent="Clinical Intelligence & Handoff Agent"
        title={intel === "HANDOFF" ? "Preparing nurse handoff" : "Summarising recovery"}
        steps={["Collecting EHR, care plan & recent events", "Reviewing vitals, adherence & reports", "Checking alerts, pending tasks & appointments", "Writing concise clinical context"]}
      />
      <Modal open={!!intelDoc} onClose={() => setIntelDoc(null)} title={intelDoc?.title} subtitle={intelDoc?.engine ? `Clinical Intelligence agent · ${intelDoc.engine === "rules" ? "rule engine" : intelDoc.engine}` : undefined} size="lg">
        {intelDoc && <Markdown>{intelDoc.content}</Markdown>}
      </Modal>
    </div>
  );
}
