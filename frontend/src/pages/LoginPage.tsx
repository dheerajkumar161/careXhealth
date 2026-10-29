import { motion } from "framer-motion";
import { Activity, ArrowRight, BrainCircuit, CalendarClock, FileStack, FlaskConical, HeartPulse, Lock, Mail, ShieldCheck, Stethoscope, User, Users } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { Link } from "react-router-dom";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { Button, Input } from "@/components/ui";
import { api } from "@/services/api";
import { cn } from "@/lib/format";

const ROLES = [
  { id: "DOCTOR", label: "Doctor", icon: Stethoscope, demo: "ananya.rao@carexhealth.health" },
  { id: "NURSE", label: "Nurse", icon: HeartPulse, demo: "priya.nair@carexhealth.health" },
  { id: "PATIENT", label: "Patient", icon: User, demo: "arjun.sharma@example.com" },
  { id: "TEST_CENTER", label: "Test Center", icon: FlaskConical, demo: "reports@citydiagnostics.in" },
  { id: "ADMIN", label: "Admin", icon: ShieldCheck, demo: "admin@carexhealth.health" },
] as const;

const DEMOS: Record<string, { email: string; who: string }[]> = {
  DOCTOR: [
    { email: "ananya.rao@carexhealth.health", who: "Dr. Ananya Rao · Orthopedics (referring)" },
    { email: "kavya.menon@carexhealth.health", who: "Dr. Kavya Menon · Physiotherapy (receives referrals)" },
  ],
  NURSE: [
    { email: "priya.nair@carexhealth.health", who: "Priya Nair · Ortho ward" },
    { email: "rahul.verma@carexhealth.health", who: "Rahul Verma · Ortho ward" },
  ],
  PATIENT: [{ email: "arjun.sharma@example.com", who: "Arjun Sharma · Knee replacement" }],
  TEST_CENTER: [{ email: "reports@citydiagnostics.in", who: "City Diagnostics · Test center" }],
  ADMIN: [{ email: "admin@carexhealth.health", who: "Hospital Admin · audit & users" }],
};

const AGENTS = [
  { icon: BrainCircuit, name: "Care Planning", c: "text-violet-600 bg-violet-50" },
  { icon: CalendarClock, name: "Execution & Scheduling", c: "text-sky-600 bg-sky-50" },
  { icon: Activity, name: "Monitoring & Escalation", c: "text-rose-600 bg-rose-50" },
  { icon: FileStack, name: "Communication & Docs", c: "text-amber-600 bg-amber-50" },
  { icon: Users, name: "Clinical Intelligence", c: "text-emerald-600 bg-emerald-50" },
];

function LoginForm() {
  const [params] = useSearchParams();
  const [role, setRole] = useState<(typeof ROLES)[number]["id"]>("DOCTOR");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await api<{ redirect: string }>("/api/auth/login", { body: { email, password, role } });
      const next = params.get("next");
      // Full navigation so the new session cookie is applied before the dashboard renders
      window.location.assign(next && next.startsWith(res.redirect) ? next : res.redirect);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Sign-in failed");
      setLoading(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-gradient-to-br from-brand-50 via-white to-sky-50 lg:flex lg:flex-col lg:justify-between p-12 border-r border-line">
        <div className="dot-grid absolute inset-0 opacity-60" />
        <div className="relative flex items-center gap-2.5">
          <div className="grid size-10 place-items-center rounded-xl bg-brand-600 text-white shadow-lg shadow-brand-600/25">
            <HeartPulse className="size-5" />
          </div>
          <div>
            <div className="font-display text-lg font-bold">CareXHealth</div>
            <div className="text-xs text-ink-500">Post-discharge care orchestration</div>
          </div>
        </div>

        <div className="relative">
          <h1 className="max-w-md font-display text-4xl font-bold leading-tight text-ink-900">
            From discharge note to <span className="text-brand-600">coordinated recovery</span> — automatically.
          </h1>
          <p className="mt-4 max-w-md text-[15px] leading-relaxed text-ink-500">Five specialised agents plan, schedule, monitor, document and hand off care, while doctors stay the clinical decision-makers.</p>

          <div className="relative mt-10 max-w-md space-y-2.5">
            <motion.div className="absolute left-[26px] top-6 bottom-6 w-px bg-gradient-to-b from-violet-200 via-rose-200 to-emerald-200" initial={{ scaleY: 0 }} animate={{ scaleY: 1 }} transition={{ duration: 1.2 }} style={{ originY: 0 }} />
            {AGENTS.map((a, i) => (
              <motion.div key={a.name} initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 + i * 0.12 }} className="relative flex items-center gap-3 rounded-2xl border border-line bg-white/80 p-2.5 pr-4 backdrop-blur shadow-[var(--shadow-card)]">
                <div className={cn("grid size-9 place-items-center rounded-xl", a.c)}>
                  <a.icon className="size-[18px]" />
                </div>
                <div className="text-sm font-medium">{a.name} Agent</div>
                <motion.span className="ml-auto size-2 rounded-full bg-emerald-400" animate={{ opacity: [0.3, 1, 0.3] }} transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.3 }} />
              </motion.div>
            ))}
          </div>
        </div>

        <div className="relative flex items-center gap-2 text-xs text-ink-500">
          <ShieldCheck className="size-4 text-brand-600" /> Role-based access · Every agent action is audit-logged · Doctor approval required
        </div>
      </div>

      {/* Form */}
      <div className="flex items-center justify-center p-6 sm:p-12">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
          <div className="mb-8 lg:hidden flex items-center gap-2.5">
            <div className="grid size-10 place-items-center rounded-xl bg-brand-600 text-white"><HeartPulse className="size-5" /></div>
            <div className="font-display text-lg font-bold">CareXHealth</div>
          </div>
          <h2 className="text-2xl font-bold">Welcome back</h2>
          <p className="mt-1 text-sm text-ink-500">Choose your role and sign in to your dashboard.</p>

          <div className="mt-6 grid grid-cols-5 gap-2">
            {ROLES.map((r) => (
              <button key={r.id} type="button" onClick={() => { setRole(r.id); setEmail(""); }} className={cn("relative flex flex-col items-center gap-1.5 rounded-xl border px-2 py-3 text-xs font-medium transition", role === r.id ? "border-brand-300 bg-brand-50 text-brand-700" : "border-line bg-white text-ink-500 hover:border-slate-300")}>
                <r.icon className="size-5" />
                {r.label}
                {role === r.id && <motion.span layoutId="role-ring" className="absolute inset-0 rounded-xl ring-2 ring-brand-400" />}
              </button>
            ))}
          </div>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
              <Input type="email" required placeholder="Email address" value={email} onChange={(e) => setEmail(e.target.value)} className="h-11 pl-10" autoComplete="email" />
            </div>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-ink-400" />
              <Input type="password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} className="h-11 pl-10" autoComplete="current-password" />
            </div>
            <Button type="submit" size="lg" className="w-full" loading={loading}>
              Sign in as {ROLES.find((r) => r.id === role)?.label} <ArrowRight className="size-4" />
            </Button>
          </form>

          <p className="mt-5 text-center text-sm text-ink-500">
            New doctor, nurse or test center?{" "}
            <Link to="/signup" className="font-semibold text-brand-700 hover:underline">
              Create an account
            </Link>
          </p>

          <div className="mt-8 rounded-2xl border border-dashed border-line bg-slate-50/60 p-4">
            <div className="mb-2.5 flex items-center justify-between">
              <span className="text-xs font-semibold text-ink-700">Demo accounts</span>
              <span className="text-[11px] text-ink-500">password: <code className="rounded bg-white px-1 py-0.5 ring-1 ring-line">Password@123</code></span>
            </div>
            <div className="space-y-1.5">
              {DEMOS[role].map((d) => (
                <button key={d.email} type="button" onClick={() => { setEmail(d.email); setPassword("Password@123"); }} className="flex w-full items-center justify-between rounded-lg bg-white px-3 py-2 text-left text-xs ring-1 ring-line transition hover:ring-brand-300">
                  <span className="font-medium text-ink-900">{d.who}</span>
                  <span className="text-ink-500">{d.email}</span>
                </button>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
