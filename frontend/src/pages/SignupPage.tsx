import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, FlaskConical, HeartPulse, Stethoscope } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { toast } from "sonner";
import { Button, Field, Input, Select } from "@/components/ui";
import { api } from "@/services/api";
import { cn } from "@/lib/format";

const ROLES = [
  { id: "DOCTOR", label: "Doctor", icon: Stethoscope, hint: "Treat patients, write care plans, send and receive referrals" },
  { id: "NURSE", label: "Nurse", icon: HeartPulse, hint: "Monitor assigned patients, handle alerts and handoffs" },
  { id: "TEST_CENTER", label: "Test Center", icon: FlaskConical, hint: "Receive test bookings and upload results" },
] as const;

const SPECIALTIES = [
  "General Medicine", "Orthopedics", "Cardiology", "Physiotherapy", "Dietetics", "Psychology", "Occupational Therapy",
  "Speech Therapy", "Home Nursing", "Wound Care", "Pulmonology", "Endocrinology", "Neurology", "General Surgery",
];

export default function SignupPage() {
  const [role, setRole] = useState<(typeof ROLES)[number]["id"]>("DOCTOR");
  const [f, setF] = useState({ name: "", email: "", password: "", phone: "", specialty: "", organization: "", location: "", inviteCode: "" });
  const [acceptsReferrals, setAccepts] = useState(true);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF((s) => ({ ...s, [k]: e.target.value }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = await api<{ redirect: string }>("/api/auth/signup", { body: { ...f, role, acceptsReferrals } });
      toast.success("Account created");
      window.location.assign(res.redirect);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sign-up failed");
      setBusy(false);
    }
  }

  return (
    <div className="dot-grid flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-50/60 via-white to-sky-50/60 p-4 sm:p-8">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-xl rounded-3xl border border-line bg-white p-6 shadow-[var(--shadow-lift)] sm:p-8">
        <Link to="/login" className="mb-5 inline-flex items-center gap-1.5 text-xs font-medium text-ink-500 hover:text-ink-900">
          <ArrowLeft className="size-3.5" /> Back to sign in
        </Link>
        <div className="flex items-center gap-2.5">
          <div className="grid size-10 place-items-center rounded-xl bg-brand-600 text-white shadow-md shadow-brand-600/25"><HeartPulse className="size-5" /></div>
          <div>
            <h1 className="text-xl font-bold">Create your CareXHealth account</h1>
            <p className="text-xs text-ink-500">Patients are registered by their treating doctor.</p>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-2">
          {ROLES.map((r) => (
            <button key={r.id} type="button" onClick={() => setRole(r.id)} className={cn("relative flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-medium transition", role === r.id ? "border-brand-300 bg-brand-50 text-brand-700" : "border-line bg-white text-ink-500 hover:border-slate-300")}>
              <r.icon className="size-5" />
              {r.label}
              {role === r.id && <motion.span layoutId="signup-role" className="absolute inset-0 rounded-xl ring-2 ring-brand-400" />}
            </button>
          ))}
        </div>
        <p className="mt-2 text-center text-xs text-ink-500">{ROLES.find((r) => r.id === role)?.hint}</p>

        <form onSubmit={submit} className="mt-6 grid grid-cols-2 gap-3">
          <Field label={role === "TEST_CENTER" ? "Contact person" : "Full name"} className="col-span-2 sm:col-span-1">
            <Input required value={f.name} onChange={set("name")} placeholder={role === "DOCTOR" ? "Dr. Firstname Lastname" : ""} />
          </Field>
          <Field label="Phone" className="col-span-2 sm:col-span-1"><Input value={f.phone} onChange={set("phone")} /></Field>
          <Field label="Work email" className="col-span-2"><Input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></Field>
          <Field label="Password" hint="At least 8 characters" className="col-span-2"><Input required type="password" minLength={8} value={f.password} onChange={set("password")} autoComplete="new-password" /></Field>

          {role === "DOCTOR" && (
            <>
              <Field label="Specialty" className="col-span-2 sm:col-span-1">
                <Select required value={f.specialty} onChange={set("specialty")}>
                  <option value="">Select…</option>
                  {SPECIALTIES.map((s) => <option key={s}>{s}</option>)}
                </Select>
              </Field>
              <Field label="Hospital / clinic" className="col-span-2 sm:col-span-1"><Input value={f.organization} onChange={set("organization")} placeholder="CareXHealth Hospital" /></Field>
              <Field label="Location" className="col-span-2"><Input value={f.location} onChange={set("location")} placeholder="Area, City" /></Field>
              <label className="col-span-2 flex items-start gap-3 rounded-xl border border-line bg-slate-50/60 p-3">
                <input type="checkbox" checked={acceptsReferrals} onChange={(e) => setAccepts(e.target.checked)} className="mt-0.5 size-4 accent-[#4f46e5]" />
                <span className="text-xs text-ink-700">
                  <b className="text-ink-900">Accept referrals from other doctors.</b> Referral requests for your specialty will arrive in your Referrals inbox for you to accept or reject.
                </span>
              </label>
            </>
          )}
          {role === "TEST_CENTER" && (
            <>
              <Field label="Test center name" className="col-span-2 sm:col-span-1"><Input required value={f.organization} onChange={set("organization")} /></Field>
              <Field label="Location" className="col-span-2 sm:col-span-1"><Input value={f.location} onChange={set("location")} /></Field>
            </>
          )}
          <Field label="Hospital invite code" hint="Only needed if your hospital has enabled one" className="col-span-2"><Input value={f.inviteCode} onChange={set("inviteCode")} /></Field>

          <Button type="submit" size="lg" loading={busy} className="col-span-2 mt-2">
            Create {ROLES.find((r) => r.id === role)?.label.toLowerCase()} account <ArrowRight className="size-4" />
          </Button>
        </form>
        <p className="mt-5 text-center text-sm text-ink-500">
          Already registered? <Link to="/login" className="font-semibold text-brand-700 hover:underline">Sign in</Link>
        </p>
      </motion.div>
    </div>
  );
}
