import { Card, PageHeader, PageSkeleton } from "@/components/ui";
import { PatientTable, RegisterPatient, type PatientSummary } from "@/components/PatientTable";
import { useApi } from "@/hooks/useApi";

export default function DoctorPatients() {
  const { data, reload } = useApi<{ patients: PatientSummary[] }>("/api/overview");
  if (!data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader eyebrow="Doctor workspace" title="Patients" subtitle="Patients under your care. Open a record to write a discharge plan, review results or make decisions." actions={<RegisterPatient onCreated={reload} />} />
      <Card className="p-5">
        <PatientTable patients={data.patients} base="/doctor/patients" />
      </Card>
    </div>
  );
}
