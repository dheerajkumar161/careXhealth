import { Check } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge, Button, statusTone } from "./ui";
import { api } from "@/services/api";
import { titleCase } from "@/lib/format";
import { demoMode } from "@/lib/demo";
import type { Appointment, Doc, Provider, Referral } from "@/types";

type PatientLite = { id: string; mrn: string; diagnosis: string; procedure?: string | null; dateOfBirth: string; gender: string; user: { name: string; phone?: string | null }; doctor?: { name: string } };
type Panel = { code: string; name: string; prep?: string; params: { key: string; label: string; unit: string; low?: number; high?: number }[] };
export type ProviderOverview = {
  provider: Provider & { type: string };
  isLab: boolean;
  referrals: (Referral & { patient: PatientLite; declinedByMe: boolean })[];
  appointments: (Appointment & { patient: PatientLite; panel: Panel | null })[];
  documents: Doc[];
};

export function SessionActions({ a, onDone }: { a: Appointment; onDone: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const due = demoMode() || new Date(a.startsAt).getTime() <= Date.now() + 12 * 3_600_000;
  if (a.status !== "BOOKED") return <Badge tone={statusTone(a.status)}>{titleCase(a.status)}</Badge>;
  if (!due) return <Badge tone="blue">Booked</Badge>;
  async function act(action: "COMPLETE" | "MISS") {
    setBusy(action);
    try {
      await api(`/api/appointments/${a.id}`, { method: "PATCH", body: { action } });
      toast.success(action === "COMPLETE" ? "Session marked completed" : "Marked missed — the Execution agent is finding a replacement slot");
      onDone();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(null);
    }
  }
  return (
    <div className="flex gap-1.5">
      <Button size="sm" variant="ghost" className="text-rose-600 hover:bg-rose-50" loading={busy === "MISS"} onClick={() => act("MISS")}>Missed</Button>
      <Button size="sm" loading={busy === "COMPLETE"} onClick={() => act("COMPLETE")} icon={<Check className="size-3.5" />}>Attended</Button>
    </div>
  );
}

