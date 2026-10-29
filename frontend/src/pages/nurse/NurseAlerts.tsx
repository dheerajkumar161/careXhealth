import { useEffect } from "react";
import { Card, PageHeader, PageSkeleton } from "@/components/ui";
import { AlertList } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import type { Alert } from "@/types";

export default function NurseAlerts() {
  const { data, reload } = useApi<{ alerts: Alert[] }>("/api/overview", { poll: 15000 });
  useEffect(() => {
    const h = () => reload();
    window.addEventListener("agents:cycle", h);
    return () => window.removeEventListener("agents:cycle", h);
  }, [reload]);
  if (!data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader eyebrow="Monitoring & Escalation" title="Alert queue" subtitle="Alerts raised by the Monitoring agent for your patients. Acknowledge, act, and document the resolution." />
      <Card className="p-5">
        <AlertList alerts={data.alerts} onChange={reload} showPatient emptyText="No open alerts for your patients" />
      </Card>
    </div>
  );
}
