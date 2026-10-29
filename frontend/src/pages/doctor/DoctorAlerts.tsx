import { useEffect, useState } from "react";
import { Card, PageHeader, PageSkeleton, Tabs } from "@/components/ui";
import { AlertList } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import type { Alert } from "@/types";

export default function DoctorAlerts() {
  const { data, reload } = useApi<{ alerts: Alert[] }>("/api/overview", { poll: 15000 });
  const [tab, setTab] = useState<"escalated" | "all">("escalated");
  useEffect(() => {
    const h = () => reload();
    window.addEventListener("agents:cycle", h);
    return () => window.removeEventListener("agents:cycle", h);
  }, [reload]);
  if (!data) return <PageSkeleton />;
  const escalated = data.alerts.filter((a) => a.escalationLevel >= 2);
  return (
    <div>
      <PageHeader eyebrow="Monitoring & Escalation" title="Alerts & escalations" subtitle="Level 1 alerts go to the assigned nurse. Anything unacknowledged, or flagged for a doctor, escalates to you." />
      <div className="mb-4">
        <Tabs value={tab} onChange={setTab} tabs={[{ id: "escalated", label: "Escalated to me", count: escalated.length }, { id: "all", label: "All open alerts", count: data.alerts.length }]} />
      </div>
      <Card className="p-5">
        <AlertList alerts={tab === "escalated" ? escalated : data.alerts} onChange={reload} showPatient emptyText="No alerts here" />
      </Card>
    </div>
  );
}
