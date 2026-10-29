import { ClipboardList } from "lucide-react";
import { useState } from "react";
import { Card, EmptyState, Markdown, PageHeader, PageSkeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { cn, fmtDate } from "@/lib/format";
import type { Doc } from "@/types";

type H = Doc & { patient: { user: { name: string } }; createdBy?: { name: string } | null };

export default function Handoffs() {
  const { data } = useApi<{ handoffs: H[] }>("/api/overview");
  const [sel, setSel] = useState<string | null>(null);
  if (!data) return <PageSkeleton />;
  const current = data.handoffs.find((h) => h.id === sel) ?? data.handoffs[0];
  return (
    <div>
      <PageHeader eyebrow="Clinical Intelligence" title="Nurse handoffs" subtitle="Concise, AI-generated shift handoffs so the incoming nurse doesn't have to search through pages of records." />
      {!data.handoffs.length ? (
        <Card className="p-5"><EmptyState icon={<ClipboardList className="size-5" />} title="No handoffs yet" text="Generate one from the shift overview or any patient record." /></Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
          <Card className="p-2">
            {data.handoffs.map((h) => (
              <button key={h.id} onClick={() => setSel(h.id)} className={cn("w-full rounded-xl px-3 py-2.5 text-left transition", current?.id === h.id ? "bg-brand-50 ring-1 ring-brand-100" : "hover:bg-slate-50")}>
                <div className="text-sm font-medium">{h.patient.user.name}</div>
                <div className="text-xs text-ink-500">{fmtDate(h.createdAt, "EEE d MMM, h:mm a")} · {h.createdBy?.name}</div>
              </button>
            ))}
          </Card>
          <Card className="p-6">{current && <Markdown>{current.content}</Markdown>}</Card>
        </div>
      )}
    </div>
  );
}
