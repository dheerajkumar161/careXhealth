import { useState } from "react";
import { HeartPulse } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/services/api";

/** Caregiver accepts a patient's invite link: /join?token=… */
export default function JoinPage() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api<{ redirect: string }>("/api/auth/accept-invite", { body: { token, name, password } });
      window.location.assign(r.redirect);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not accept the invite");
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen place-items-center px-4">
      <Card className="w-full max-w-md p-6">
        <div className="mb-4 flex items-center gap-2.5">
          <div className="grid size-10 place-items-center rounded-xl bg-brand-600 text-white"><HeartPulse className="size-5" /></div>
          <div className="font-display text-lg font-bold">CareXHealth</div>
        </div>
        <h1 className="text-xl font-bold">Join as a caregiver</h1>
        <p className="mt-1 text-sm text-ink-500">A patient has invited you to follow their recovery (read-only). Create your account to continue.</p>
        {!token && <p className="mt-4 text-sm text-rose-600">This link is missing its invite code.</p>}
        <form onSubmit={submit} className="mt-5 space-y-4">
          <Field label="Your name"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
          <Field label="Choose a password" hint="At least 10 characters with a letter and a number. If you already have a caregiver account, enter its password."><Input type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" /></Field>
          <Button type="submit" className="w-full" loading={busy} disabled={!token}>Accept invite</Button>
        </form>
      </Card>
    </div>
  );
}
