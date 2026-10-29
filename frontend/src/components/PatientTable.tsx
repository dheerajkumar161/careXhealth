import { motion } from "framer-motion";
import { ChevronRight, Search, UserPlus } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { toast } from "sonner";
import { Avatar, Badge, Button, Field, Input, Modal, Select, statusTone } from "./ui";
import { api } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { age, cn, fmtWhen, titleCase } from "@/lib/format";
import type { UserLite } from "@/types";

function riskTitle(p: { riskScore?: number; riskFactors?: { points: number; label: string }[] | string | null }) {
  let f = p.riskFactors;
  if (typeof f === "string") {
    try { f = JSON.parse(f); } catch { f = null; }
  }
  return Array.isArray(f) && f.length ? `Risk score ${p.riskScore ?? 0}/100\n` + f.map((x) => `+${x.points} ${x.label}`).join("\n") : "No risk factors";
}

export type PatientSummary = {
  id: string; riskScore?: number; riskFactors?: { points: number; label: string }[] | string | null; mrn: string; diagnosis: string; procedure?: string | null; status: string; riskLevel: string; dateOfBirth: string; gender: string;
  user: UserLite; nurse?: UserLite | null; doctor: UserLite; openAlerts: number; criticalAlerts: number; adherence: number | null;
  nextAppointment: { title: string; startsAt: string } | null; draftPlan: { kind: string } | null; pendingReviews: number; pendingRelease?: boolean;
};

function AdherenceBar({ value }: { value: number | null }) {
  if (value === null) return <span className="text-xs text-ink-400">—</span>;
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
        <motion.div initial={{ width: 0 }} animate={{ width: `${value}%` }} transition={{ duration: 0.8 }} className={cn("h-full rounded-full", value >= 85 ? "bg-emerald-500" : value >= 65 ? "bg-amber-400" : "bg-rose-500")} />
      </div>
      <span className="text-xs font-medium text-ink-700">{value}%</span>
    </div>
  );
}

export function PatientTable({ patients, base }: { patients: PatientSummary[]; base: "/doctor/patients" | "/nurse/patients" }) {
  const [q, setQ] = useState("");
  const list = patients.filter((p) => `${p.user.name} ${p.mrn} ${p.diagnosis}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div>
      <div className="relative mb-3">
        <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
        <Input placeholder="Search by name, MRN or diagnosis" value={q} onChange={(e) => setQ(e.target.value)} className="pl-9" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-ink-400">
              <th className="px-3 py-2">Patient</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Risk</th>
              <th className="px-3 py-2">Adherence (7d)</th>
              <th className="px-3 py-2">Next</th>
              <th className="px-3 py-2">Attention</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.map((p, i) => (
              <motion.tr key={p.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }} className="group border-t border-line transition hover:bg-slate-50/70">
                <td className="px-3 py-3">
                  <Link to={`${base}/${p.id}`} className="flex items-center gap-3">
                    <Avatar name={p.user.name} size={34} tone={p.riskLevel === "HIGH" ? "amber" : "brand"} />
                    <div className="min-w-0">
                      <div className="font-medium text-ink-900 group-hover:text-brand-700">{p.user.name}</div>
                      <div className="max-w-[240px] truncate text-xs text-ink-500">{age(p.dateOfBirth)}y {p.gender[0]} · {p.procedure || p.diagnosis}</div>
                    </div>
                  </Link>
                </td>
                <td className="px-3 py-3"><Badge tone={statusTone(p.status)} dot>{titleCase(p.status)}</Badge></td>
                <td className="px-3 py-3" title={riskTitle(p)}><Badge tone={statusTone(p.riskLevel)}>{titleCase(p.riskLevel)}{p.riskScore ? ` · ${p.riskScore}` : ""}</Badge></td>
                <td className="px-3 py-3"><AdherenceBar value={p.adherence} /></td>
                <td className="px-3 py-3 text-xs text-ink-700">{p.nextAppointment ? <><div className="max-w-[180px] truncate font-medium">{p.nextAppointment.title}</div><div className="text-ink-500">{fmtWhen(p.nextAppointment.startsAt)}</div></> : <span className="text-ink-400">—</span>}</td>
                <td className="px-3 py-3">
                  <div className="flex flex-wrap gap-1">
                    {p.openAlerts > 0 && <Badge tone={p.criticalAlerts ? "red" : "amber"}>{p.openAlerts} alert{p.openAlerts > 1 ? "s" : ""}</Badge>}
                    {p.draftPlan && <Badge tone="violet">Draft plan</Badge>}
                    {p.pendingReviews > 0 && <Badge tone="blue">{p.pendingReviews} report</Badge>}
                    {p.pendingRelease && <Badge tone="amber">Nurse release requested</Badge>}
                    {p.status === "ADMITTED" && !p.draftPlan && <Badge tone="gray">Needs discharge plan</Badge>}
                    {!p.openAlerts && !p.draftPlan && !p.pendingReviews && !p.pendingRelease && p.status !== "ADMITTED" && <span className="text-xs text-ink-400">—</span>}
                  </div>
                </td>
                <td className="px-3 py-3 text-right">
                  <Link to={`${base}/${p.id}`} className="inline-grid size-8 place-items-center rounded-lg text-ink-400 hover:bg-white hover:text-brand-600">
                    <ChevronRight className="size-4" />
                  </Link>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
        {!list.length && <p className="py-10 text-center text-sm text-ink-500">No patients match your search.</p>}
      </div>
    </div>
  );
}

export function RegisterPatient({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false);
  const { data } = useApi<{ nurses: { id: string; name: string; title?: string }[] }>(open ? "/api/patients" : null);
  const [f, setF] = useState({ name: "", email: "", phone: "", password: "Password@123", dateOfBirth: "", gender: "Female", diagnosis: "", procedure: "", allergies: "", comorbidities: "", nurseId: "" });
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/api/patients", { body: f });
      toast.success(`${f.name} registered`, { description: `Portal login: ${f.email}` });
      setOpen(false);
      onCreated();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not register");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Button icon={<UserPlus className="size-4" />} onClick={() => setOpen(true)}>Register patient</Button>
      <Modal open={open} onClose={() => setOpen(false)} title="Register a patient" subtitle="Creates the patient's record and portal login, and assigns their nurse." size="lg">
        <form id="reg" onSubmit={submit} className="grid grid-cols-2 gap-3">
          <Field label="Full name"><Input required value={f.name} onChange={set("name")} /></Field>
          <Field label="Email (portal login)"><Input required type="email" value={f.email} onChange={set("email")} /></Field>
          <Field label="Phone"><Input value={f.phone} onChange={set("phone")} /></Field>
          <Field label="Temporary password" hint="Min 8 characters"><Input required minLength={8} value={f.password} onChange={set("password")} /></Field>
          <Field label="Date of birth"><Input required type="date" value={f.dateOfBirth} onChange={set("dateOfBirth")} /></Field>
          <Field label="Gender">
            <Select value={f.gender} onChange={set("gender")}><option>Female</option><option>Male</option><option>Other</option></Select>
          </Field>
          <Field label="Diagnosis" className="col-span-2"><Input required value={f.diagnosis} onChange={set("diagnosis")} placeholder="e.g. Community-acquired pneumonia" /></Field>
          <Field label="Procedure (if any)" className="col-span-2"><Input value={f.procedure} onChange={set("procedure")} /></Field>
          <Field label="Allergies"><Input value={f.allergies} onChange={set("allergies")} /></Field>
          <Field label="Comorbidities"><Input value={f.comorbidities} onChange={set("comorbidities")} /></Field>
          <Field label="Assigned nurse" className="col-span-2">
            <Select value={f.nurseId} onChange={set("nurseId")}>
              <option value="">— Select nurse —</option>
              {data?.nurses.map((n) => <option key={n.id} value={n.id}>{n.name}{n.title ? ` · ${n.title}` : ""}</option>)}
            </Select>
          </Field>
          <div className="col-span-2 flex justify-end gap-2 pt-2">
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button type="submit" loading={busy}>Register patient</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
