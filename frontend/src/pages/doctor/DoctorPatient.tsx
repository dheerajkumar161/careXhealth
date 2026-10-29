import { useParams } from "react-router-dom";
import { Suspense } from "react";
import { PatientWorkspace } from "@/components/PatientWorkspace";

export default function DoctorPatient() {
  const { id = "" } = useParams();
  return (
    <Suspense>
      <PatientWorkspace id={id} role="DOCTOR" />
    </Suspense>
  );
}
