import { Card, PageHeader, PageSkeleton } from "@/components/ui";
import { PatientTable, type PatientSummary } from "@/components/PatientTable";
import { useApi } from "@/hooks/useApi";

export default function NursePatients() {
  const { data } = useApi<{ patients: PatientSummary[] }>("/api/overview");
  if (!data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader eyebrow="Nurse workspace" title="My patients" subtitle="Patients assigned to you for post-discharge follow-up." />
      <Card className="p-5">
        <PatientTable patients={data.patients} base="/nurse/patients" />
      </Card>
    </div>
  );
}
