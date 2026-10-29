import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown, Info, Plus, ShieldAlert, Sparkles, Trash2, TriangleAlert, Wand2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button, Card, Field, Input, Select, Textarea } from "../ui";
import { AgentOverlay } from "../animations";
import { CATEGORY_META, CATEGORY_ORDER, METRIC_OPTIONS, autoTitle } from "./meta";
import { api, withMinDuration } from "@/services/api";
import { cn, fmtDate } from "@/lib/format";
import type { CarePlan, Doc, PlanItem, SafetyFinding } from "@/types";
import { SourceStrip } from "./SourceImages";

function DetailChips({ item }: { item: PlanItem }) {
  const d = item.details;
  const chips: string[] = [];
  switch (item.category) {
    case "MEDICATION":
      if (d.dose) chips.push(String(d.dose));
      chips.push(`${d.timesPerDay ?? 1}× / day`, `${d.durationDays ?? "?"} days`);
      if (d.instructions) chips.push(String(d.instructions));
      break;
    case "INVESTIGATION":
      chips.push(`Day ${d.dayOffset ?? "?"}`);
      if (d.instructions) chips.push(String(d.instructions));
      break;
    case "FOLLOW_UP":
      chips.push(`In ${d.dayOffset ?? "?"} days`, d.withTreatingDoctor !== false && !d.specialty ? "Treating doctor" : String(d.specialty ?? ""));
      break;
    case "REFERRAL":
      chips.push(String(d.reason ?? ""), `${d.sessions ?? 1} session(s)`);
      if (Number(d.sessions) > 1) chips.push(`${d.frequencyPerWeek}/week · ${d.durationWeeks} wk`);
      chips.push(`Start ≤ ${d.preferredStartWithinDays ?? 7} days`);
      if (d.urgency && d.urgency !== "ROUTINE") chips.push(String(d.urgency));
      break;
    case "RED_FLAG":
      chips.push(String(d.action ?? "").replace("_", " ").toLowerCase(), `${String(d.severity ?? "").toLowerCase()} severity`);
      break;
  }
  const list = chips.filter(Boolean);
  if (!list.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-1">
      {list.map((c, i) => (
        <span key={i} className="rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] text-ink-500 ring-1 ring-line">
          {c}
        </span>
      ))}
    </div>
  );
}

/** Read-only structured care plan, grouped the way the discharge plan is presented to clinicians. */
export function CarePlanView({ items, compact, onRemove }: { items: (PlanItem & { planKind?: string })[]; compact?: boolean; onRemove?: (item: PlanItem) => void }) {
  const groups = CATEGORY_ORDER.map((c) => ({ c, list: items.filter((i) => i.category === c && i.included) })).filter((g) => g.list.length);
  return (
    <div className={cn("grid gap-3", compact ? "sm:grid-cols-2" : "md:grid-cols-2 xl:grid-cols-3")}>
      {groups.map(({ c, list }, gi) => {
        const m = CATEGORY_META[c];
        return (
          <motion.div key={c} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: gi * 0.04 }} className="rounded-2xl border border-line bg-white p-4">
            <div className="mb-2.5 flex items-center gap-2">
              <span className={cn("grid size-7 place-items-center rounded-lg ring-1", m.bg, m.color, m.ring)}>
                <m.icon className="size-3.5" />
              </span>
              <span className="text-[13px] font-semibold">{m.label}</span>
              <span className="ml-auto text-[11px] text-ink-400">{list.length}</span>
            </div>
            <ul className="space-y-2.5">
              {list.map((i) => (
                <li key={i.id} className="group/item text-[13px] leading-snug">
                  <div className="flex items-start gap-1.5">
                    <span className={cn("flex-1 text-ink-900", i.action === "DISCONTINUE" && "line-through text-ink-500")}>{i.title}</span>
                    {i.source === "AI_SUGGESTED" && <Sparkles className="mt-0.5 size-3 shrink-0 text-violet-500" aria-label="AI-suggested, doctor approved" />}
                    {onRemove && (
                      <button onClick={() => onRemove(i)} title="Remove from active plan" className="-mt-0.5 rounded-md p-1 text-ink-400 opacity-40 transition hover:bg-rose-50 hover:text-rose-600 group-hover/item:opacity-100">
                        <Trash2 className="size-3.5" />
                      </button>
                    )}
                  </div>
                  {!compact && <DetailChips item={i} />}
                </li>
              ))}
            </ul>
          </motion.div>
        );
      })}
    </div>
  );
}

// ───────────── Editor ─────────────

const num = (v: string) => (v === "" ? "" : Number(v));

function DetailEditor({ item, onChange }: { item: PlanItem; onChange: (d: Record<string, unknown>) => void }) {
  const d = item.details;
  const set = (k: string, v: unknown) => onChange({ ...d, [k]: v });
  const n = (k: string, label: string, w = "") => (
    <Field label={label} className={w}>
      <Input type="number" min={0} value={String(d[k] ?? "")} onChange={(e) => set(k, num(e.target.value))} />
    </Field>
  );
  const t = (k: string, label: string, w = "") => (
    <Field label={label} className={w}>
      <Input value={String(d[k] ?? "")} onChange={(e) => set(k, e.target.value)} />
    </Field>
  );
  switch (item.category) {
    case "MEDICATION":
      return <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">{t("name", "Medicine", "col-span-2")}{t("dose", "Dose")}{n("timesPerDay", "Times / day")}{n("durationDays", "Days")}{t("instructions", "Instructions", "col-span-2 sm:col-span-5")}</div>;
    case "INVESTIGATION":
      return <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{t("test", "Test", "col-span-2")}{n("dayOffset", "Day after discharge")}{t("instructions", "Prep / notes")}</div>;
    case "FOLLOW_UP":
      return <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">{t("specialty", "Specialty (blank = treating doctor)")}{n("dayOffset", "Days after discharge")}{t("reason", "Reason")}</div>;
    case "REFERRAL":
      return (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {t("referralType", "Referral to (service)", "col-span-2")}
          <Field label="Urgency">
            <Select value={String(d.urgency ?? "ROUTINE")} onChange={(e) => set("urgency", e.target.value)}>
              <option>ROUTINE</option>
              <option>PRIORITY</option>
              <option>URGENT</option>
            </Select>
          </Field>
          {n("preferredStartWithinDays", "Start within (days)")}
          {t("reason", "Reason", "col-span-2 sm:col-span-4")}
          {n("sessions", "Sessions")}
          {n("frequencyPerWeek", "Per week")}
          {n("durationWeeks", "Weeks")}
        </div>
      );
    case "MONITORING":
      return (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Reading">
            <Select value={String(d.metric ?? "TEMPERATURE")} onChange={(e) => set("metric", e.target.value)}>
              {METRIC_OPTIONS.filter((m) => m[0] !== "SYMPTOM").map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </Select>
          </Field>
          {n("timesPerDay", "Times / day")}
        </div>
      );
    case "RED_FLAG":
      return (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Field label="Metric">
            <Select value={String(d.metric ?? "TEMPERATURE")} onChange={(e) => onChange({ ...d, metric: e.target.value, operator: e.target.value === "SYMPTOM" ? "CONTAINS" : d.operator === "CONTAINS" ? ">" : d.operator })}>
              {METRIC_OPTIONS.map(([v, l]) => (
                <option key={v} value={v}>{l}</option>
              ))}
            </Select>
          </Field>
          {d.metric === "SYMPTOM" ? (
            <Field label="Keywords (comma separated)" className="col-span-1 sm:col-span-3">
              <Input value={Array.isArray(d.keywords) ? (d.keywords as string[]).join(", ") : String(d.keywords ?? "")} onChange={(e) => set("keywords", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
            </Field>
          ) : (
            <>
              <Field label="Condition">
                <Select value={String(d.operator ?? ">")} onChange={(e) => set("operator", e.target.value)}>
                  {[">", ">=", "<", "<="].map((o) => <option key={o}>{o}</option>)}
                </Select>
              </Field>
              {n("threshold", "Threshold")}
              <div />
            </>
          )}
          <Field label="Action">
            <Select value={String(d.action ?? "NOTIFY_NURSE")} onChange={(e) => set("action", e.target.value)}>
              <option value="NOTIFY_NURSE">Notify nurse</option>
              <option value="NOTIFY_DOCTOR">Notify doctor</option>
              <option value="EMERGENCY">Emergency escalation</option>
            </Select>
          </Field>
          <Field label="Severity">
            <Select value={String(d.severity ?? "HIGH")} onChange={(e) => set("severity", e.target.value)}>
              {["LOW", "MEDIUM", "HIGH", "CRITICAL"].map((o) => <option key={o}>{o}</option>)}
            </Select>
          </Field>
        </div>
      );
    default:
      return (
        <Field label="Instruction">
          <Textarea rows={2} value={String(d.text ?? item.title)} onChange={(e) => onChange({ ...d, text: e.target.value })} />
        </Field>
      );
  }
}

const DEFAULTS: Record<string, Record<string, unknown>> = {
  MEDICATION: { name: "", dose: "", timesPerDay: 1, durationDays: 7, instructions: "" },
  INVESTIGATION: { test: "", dayOffset: 3 },
  FOLLOW_UP: { specialty: "", withTreatingDoctor: true, dayOffset: 14, reason: "Post-discharge review" },
  REFERRAL: { referralType: "", reason: "", sessions: 1, frequencyPerWeek: 1, durationWeeks: 1, preferredStartWithinDays: 7, urgency: "ROUTINE" },
  MONITORING: { metric: "TEMPERATURE", timesPerDay: 2 },
  RED_FLAG: { metric: "TEMPERATURE", operator: ">", threshold: 100.4, action: "NOTIFY_NURSE", severity: "HIGH" },
};

/** Prescribing-safety review (allergies, interactions, duplicates, dose ceilings). Blocking findings need a written override reason. */
function SafetyPanel({ findings, overrides, setOverrides }: { findings: SafetyFinding[]; overrides: Record<string, string>; setOverrides: (o: Record<string, string>) => void }) {
  if (!findings.length) return null;
  const blocks = findings.filter((f) => f.severity === "BLOCK");
  return (
    <div className={cn("mx-5 mb-4 rounded-2xl border p-4", blocks.length ? "border-rose-200 bg-rose-50/70" : "border-amber-200 bg-amber-50/70")} role="alert">
      <div className={cn("mb-2 flex items-center gap-2 text-sm font-semibold", blocks.length ? "text-rose-800" : "text-amber-800")}>
        {blocks.length ? <ShieldAlert className="size-4" /> : <TriangleAlert className="size-4" />}
        Prescribing safety check · {blocks.length ? `${blocks.length} must be resolved` : `${findings.length} to review`}
      </div>
      <ul className="space-y-2.5">
        {findings.map((f) => (
          <li key={f.code} className="rounded-xl bg-white/80 p-3 text-xs ring-1 ring-black/5">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={f.severity === "BLOCK" ? "red" : "amber"}>{f.severity === "BLOCK" ? "Blocks approval" : "Warning"}</Badge>
              <span className="font-semibold text-ink-900">{f.title}</span>
              {f.items.map((i) => <span key={i} className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-ink-700">{i}</span>)}
            </div>
            <p className="mt-1.5 text-ink-700">{f.message}</p>
            {f.severity === "BLOCK" && (
              <Input
                className="mt-2 h-9 text-xs"
                placeholder="Clinical reason to proceed anyway (min 5 characters — recorded in the audit log)"
                value={overrides[f.code] ?? ""}
                onChange={(e) => setOverrides({ ...overrides, [f.code]: e.target.value })}
                aria-label={`Override reason for ${f.title}`}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Doctor reviews, edits and approves the Planning agent's draft. */
export function CarePlanEditor({ plan, onDone, sources = [] }: { plan: CarePlan; onDone: () => void; sources?: Doc[] }) {
  const [items, setItems] = useState<PlanItem[]>(plan.items);
  const [open, setOpen] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [approving, setApproving] = useState(false);
  const [adding, setAdding] = useState<string>("");
  const [safety, setSafety] = useState<SafetyFinding[]>(plan.safety ?? []);
  const [overrides, setOverrides] = useState<Record<string, string>>({});

  const update = (id: string, patch: Partial<PlanItem>) => {
    setDirty(true);
    setItems((list) =>
      list.map((i) => {
        if (i.id !== id) return i;
        const next = { ...i, ...patch };
        if (patch.details) next.title = autoTitle(i.category, patch.details) || i.title;
        return next;
      }),
    );
  };

  function addItem(category: string) {
    const id = `new-${Date.now()}`;
    const details = { ...(DEFAULTS[category] ?? { text: "" }) };
    setItems((l) => [...l, { id, category, action: "ADD", title: autoTitle(category, details) || "New instruction", details, source: "DOCTOR", included: true, sortOrder: l.length }]);
    setOpen(id);
    setAdding("");
    setDirty(true);
  }

  async function save(silent = false) {
    const invalid = items.find((i) => i.included && !i.title.trim());
    if (invalid) {
      toast.error("Every included item needs a description");
      return false;
    }
    setSaving(true);
    try {
      const saved = await api<{ plan: CarePlan }>(`/api/care-plans/${plan.id}`, {
        method: "PATCH",
        body: { items: items.map((i) => ({ id: i.id.startsWith("new-") ? undefined : i.id, category: i.category, action: i.action, title: i.title, details: i.details, included: i.included, source: i.source, rationale: i.rationale })) },
      });
      setDirty(false);
      setSafety(saved.plan.safety ?? []);
      if (!silent) toast.success("Draft saved");
      return true;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Save failed");
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function approve() {
    if (dirty && !(await save(true))) return;
    const unresolved = safety.filter((f) => f.severity === "BLOCK" && (overrides[f.code] ?? "").trim().length < 5);
    if (unresolved.length) return void toast.error("Safety alert needs attention", { description: `Remove the conflicting item or enter a clinical reason for: ${unresolved.map((f) => f.title).join(", ")}` });
    setApproving(true);
    try {
      await withMinDuration(api(`/api/care-plans/${plan.id}/approve`, { method: "POST", body: { overrides } }), 4200);
      toast.success(plan.kind === "INITIAL" ? "Care plan approved — agents are executing it" : "Amendment approved and executed");
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Approval failed");
    } finally {
      setApproving(false);
    }
  }

  async function discard() {
    if (!confirm("Discard this draft?")) return;
    await api(`/api/care-plans/${plan.id}`, { method: "PATCH", body: { status: "REJECTED" } });
    toast("Draft discarded");
    onDone();
  }

  const included = items.filter((i) => i.included);
  const ai = items.filter((i) => i.source === "AI_SUGGESTED");

  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line bg-gradient-to-r from-violet-50 via-white to-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Badge tone="violet" dot>Draft · awaiting your approval</Badge>
              <Badge tone="gray">{plan.kind === "INITIAL" ? `Care plan v${plan.version}` : "Amendment"}</Badge>
              <Badge tone="brand">
                <Wand2 className="size-3" /> {plan.engine === "rules" ? "Rule engine" : plan.engine}
              </Badge>
            </div>
            <p className="mt-2 max-w-3xl text-sm text-ink-700">{plan.summary}</p>
            <details className="mt-2 text-xs text-ink-500" open={sources.length > 0}>
              <summary className="cursor-pointer select-none font-medium text-ink-700">Original instructions{sources.length ? " & source images" : ""}</summary>
              <p className="mt-1.5 max-w-3xl whitespace-pre-line rounded-lg bg-white p-3 italic ring-1 ring-line">{plan.rawInstructions}</p>
              <SourceStrip docs={sources} />
            </details>
          </div>
          <div className="text-right text-xs text-ink-500">
            <div><b className="text-ink-900">{included.length}</b> of {items.length} items included</div>
            {!!ai.length && <div className="mt-0.5 flex items-center justify-end gap-1"><Sparkles className="size-3 text-violet-500" /> {ai.length} AI suggestions to review</div>}
          </div>
        </div>
      </div>

      <div className="divide-y divide-line">
        {CATEGORY_ORDER.map((c) => {
          const list = items.filter((i) => i.category === c);
          if (!list.length) return null;
          const m = CATEGORY_META[c];
          return (
            <div key={c} className="px-5 py-3">
              <div className="mb-1.5 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-ink-500">
                <m.icon className={cn("size-3.5", m.color)} /> {m.label}
              </div>
              <div className="space-y-1.5">
                {list.map((i) => (
                  <div key={i.id} className={cn("rounded-xl border transition", i.included ? "border-line bg-white" : "border-dashed border-line bg-slate-50/60 opacity-60", i.source === "AI_SUGGESTED" && i.included && "border-violet-200 bg-violet-50/30")}>
                    <div className="flex items-start gap-3 px-3 py-2.5">
                      <button onClick={() => update(i.id, { included: !i.included })} className={cn("mt-0.5 grid size-5 shrink-0 place-items-center rounded-md border transition", i.included ? "border-brand-500 bg-brand-500 text-white" : "border-slate-300 bg-white")} aria-label={i.included ? "Exclude" : "Include"}>
                        {i.included && <Check className="size-3.5" strokeWidth={3} />}
                      </button>
                      <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(open === i.id ? null : i.id)}>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <span className={cn("text-sm font-medium", i.action === "DISCONTINUE" && "text-rose-700")}>{i.action !== "ADD" && `${i.action} · `}{i.title}</span>
                          {i.source === "AI_SUGGESTED" && <Badge tone="violet"><Sparkles className="size-3" /> AI suggested</Badge>}
                        </div>
                        {i.rationale && <p className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-500"><Info className="size-3" /> {i.rationale}</p>}
                        {open !== i.id && <DetailChips item={i} />}
                      </button>
                      <button onClick={() => setOpen(open === i.id ? null : i.id)} className="rounded-lg p-1 text-ink-400 hover:bg-slate-100">
                        <ChevronDown className={cn("size-4 transition", open === i.id && "rotate-180")} />
                      </button>
                      <button onClick={() => { setItems((l) => l.filter((x) => x.id !== i.id)); setDirty(true); }} className="rounded-lg p-1 text-ink-400 hover:bg-rose-50 hover:text-rose-600" aria-label="Remove">
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                    <AnimatePresence initial={false}>
                      {open === i.id && (
                        <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                          <div className="space-y-3 border-t border-line px-3 py-3 pl-11">
                            <DetailEditor item={i} onChange={(details) => update(i.id, { details })} />
                            <Field label="Display title">
                              <Input value={i.title} onChange={(e) => { setDirty(true); setItems((l) => l.map((x) => (x.id === i.id ? { ...x, title: e.target.value } : x))); }} />
                            </Field>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>

      <SafetyPanel findings={safety} overrides={overrides} setOverrides={setOverrides} />
      <div className="flex flex-col gap-3 border-t border-line bg-slate-50/60 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Select value={adding} onChange={(e) => e.target.value && addItem(e.target.value)} className="h-9 w-56 text-xs">
            <option value="">+ Add an item…</option>
            {CATEGORY_ORDER.map((c) => (
              <option key={c} value={c}>{CATEGORY_META[c].label}</option>
            ))}
          </Select>
          <Plus className="size-4 text-ink-400" />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="ghost" onClick={discard}>Discard</Button>
          <Button variant="secondary" onClick={() => save()} loading={saving} disabled={!dirty}>Save draft</Button>
          <Button onClick={approve} icon={<Check className="size-4" />}>Approve & activate</Button>
        </div>
      </div>

      <AgentOverlay
        open={approving}
        kind="booking"
        agent="Care Execution & Scheduling Agent"
        title="Activating the approved care plan"
        steps={[
          "Care Planning agent hands off requirements",
          "Generating medication schedules & reminders",
          "Booking tests with the Test Center service",
          "Booking follow-ups via the Scheduling service",
          "Matching referral providers & holding slots",
          "Building referral packages & routing them",
          "Registering red-flag rules with Monitoring",
          "Sending patient-friendly plan to the patient",
        ]}
      />
    </Card>
  );
}

export function PlanHistory({ plans }: { plans: CarePlan[] }) {
  const past = plans.filter((p) => p.status !== "DRAFT");
  if (!past.length) return null;
  return (
    <div className="space-y-2">
      {past.map((p) => (
        <div key={p.id} className="flex items-center justify-between rounded-xl border border-line bg-white px-4 py-2.5 text-sm">
          <div className="min-w-0">
            <span className="font-medium">{p.kind === "INITIAL" ? `Care plan v${p.version}` : `Amendment (v${p.version})`}</span>
            <span className="ml-2 truncate text-xs text-ink-500">“{p.rawInstructions.slice(0, 90)}{p.rawInstructions.length > 90 ? "…" : ""}”</span>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-ink-500">
            {fmtDate(p.approvedAt ?? p.createdAt, "d MMM, h:mm a")}
            <Badge tone={p.status === "ACTIVE" ? "green" : "gray"}>{p.status.toLowerCase()}</Badge>
          </div>
        </div>
      ))}
    </div>
  );
}
