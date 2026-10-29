import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Card, PageHeader, PageSkeleton } from "@/components/ui";
import { DocumentList, DocumentModal } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import type { Doc, PatientRecord } from "@/types";

function PatientDocumentsInner() {
  const { data } = useApi<PatientRecord>("/api/overview");
  const [doc, setDoc] = useState<Doc | null>(null);
  const docParam = useSearchParams()[0].get("doc");
  useEffect(() => {
    const target = docParam && data?.documents.find((d) => d.id === docParam);
    if (target) setDoc(target);
  }, [docParam, data]);
  if (!data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader eyebrow="Your records" title="Documents" subtitle="Your recovery plan and test reports. Your doctor reviews every report and will contact you if anything needs to change." />
      <Card className="p-5"><DocumentList docs={data.documents} onOpen={setDoc} /></Card>
      <DocumentModal doc={doc} onClose={() => setDoc(null)} />
    </div>
  );
}

export default function PatientDocuments() {
  return (
    <Suspense>
      <PatientDocumentsInner />
    </Suspense>
  );
}
