import { ClipboardCheck } from "lucide-react";
import { Card, EmptyState, Markdown, PageHeader, PageSkeleton } from "@/components/ui";
import { CarePlanView } from "@/components/clinical/CarePlan";
import { useApi } from "@/hooks/useApi";
import { fmtDate } from "@/lib/format";
import type { PatientRecord } from "@/types";

export default function PatientPlan() {
  const { data } = useApi<PatientRecord>("/api/overview");
  if (!data) return <PageSkeleton />;
  const plans = data.plans.filter((p) => p.status === "ACTIVE");
  const instructions = data.documents.find((d) => d.type === "PATIENT_INSTRUCTIONS");
  const items = plans.flatMap((p) => p.items);
  return (
    <div>
      <PageHeader eyebrow="Approved by your doctor" title="My care plan" subtitle={plans[0] ? `Last updated ${fmtDate(plans[plans.length - 1].approvedAt, "d MMM yyyy, h:mm a")}` : undefined} />
      {!plans.length ? (
        <Card className="p-5"><EmptyState icon={<ClipboardCheck className="size-5" />} title="Your plan isn’t ready yet" text="Your doctor is preparing it. You’ll get a notification as soon as it’s approved." /></Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1.2fr_1fr]">
          <Card className="p-6">{instructions ? <Markdown>{instructions.content}</Markdown> : <p className="text-sm text-ink-500">Preparing your easy-to-read plan…</p>}</Card>
          <div>
            <h3 className="mb-3 text-sm font-semibold text-ink-700">At a glance</h3>
            <CarePlanView items={items} compact />
          </div>
        </div>
      )}
    </div>
  );
}
