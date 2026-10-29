import { motion } from "framer-motion";
import { CheckCircle2, Clock, FileText, FlaskConical, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { Badge, Card, EmptyState, PageHeader, PageSkeleton, StatCard, Tabs, statusTone } from "@/components/ui";
import { DocumentModal } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import { fmtWhen, titleCase } from "@/lib/format";
import type { Doc } from "@/types";

type Flag = { label: string; value: number; unit: string; flag: string; range: string };
type Test = {
  id: string; title: string; status: string; dueDate?: string | null; meta: Record<string, unknown>;
  patient: { id: string; mrn: string; user: { name: string } };
  appointments: { id: string; startsAt: string; status: string; provider: { name: string; organization: string } }[];
  documents: (Doc & { data: { flags?: Flag[] } | null })[];
};

const GROUPS = {
  upcoming: (t: Test) => ["PENDING", "SCHEDULED"].includes(t.status) && !t.documents.length,
  review: (t: Test) => t.documents.some((d) => d.reviewStatus === "PENDING_REVIEW"),
  done: (t: Test) => t.documents.length > 0 && t.documents.every((d) => d.reviewStatus === "REVIEWED"),
  other: (t: Test) => ["FAILED", "CANCELLED", "AWAITING_RESULT"].includes(t.status) && !t.documents.length,
};

export default function DoctorTests() {
  const { data, reload } = useApi<{ tests: Test[] }>("/api/tests", { poll: 30000 });
  const [tab, setTab] = useState<keyof typeof GROUPS>("upcoming");
  const [doc, setDoc] = useState<Doc | null>(null);
  if (!data) return <PageSkeleton />;
  const list = data.tests.filter(GROUPS[tab]);

  return (
    <div>
      <PageHeader eyebrow="Investigations" title="Tests" subtitle="Every test ordered in your patients’ care plans — booked automatically with the test center, results flagged and routed back to you." />
      <div className="mb-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Booked / upcoming" value={data.tests.filter(GROUPS.upcoming).length} icon={<Clock className="size-4" />} tone="blue" />
        <StatCard label="Results to review" value={data.tests.filter(GROUPS.review).length} icon={<FileText className="size-4" />} tone="violet" delay={0.05} />
        <StatCard label="Reviewed" value={data.tests.filter(GROUPS.done).length} icon={<CheckCircle2 className="size-4" />} tone="green" delay={0.1} />
        <StatCard label="Needs attention" value={data.tests.filter(GROUPS.other).length} icon={<TriangleAlert className="size-4" />} tone="amber" delay={0.15} />
      </div>
      <div className="mb-4">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { id: "upcoming", label: "Upcoming", count: data.tests.filter(GROUPS.upcoming).length },
            { id: "review", label: "To review", count: data.tests.filter(GROUPS.review).length },
            { id: "done", label: "Reviewed" },
            { id: "other", label: "Awaiting / failed / cancelled" },
          ]}
        />
      </div>
      <Card className="divide-y divide-line">
        {!list.length && <EmptyState icon={<FlaskConical className="size-5" />} title="Nothing here" text="Tests appear when a care plan with investigations (e.g. “Check CBC after 5 days”) is approved." />}
        {list.map((t, i) => {
          const appt = t.appointments[0];
          const report = t.documents[0];
          const abnormal = report?.data?.flags?.filter((f) => f.flag !== "NORMAL") ?? [];
          return (
            <motion.div key={t.id} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="flex flex-wrap items-center gap-4 px-5 py-4">
              <div className="grid size-10 place-items-center rounded-xl bg-violet-50 text-violet-600"><FlaskConical className="size-4" /></div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{t.title}</div>
                <div className="text-xs text-ink-500">
                  <Link to={`/doctor/patients/${t.patient.id}`} className="font-medium text-brand-700 hover:underline">{t.patient.user.name}</Link> · MRN {t.patient.mrn}
                  {appt && <> · {appt.provider.organization} · {fmtWhen(appt.startsAt)}</>}
                </div>
                {abnormal.length > 0 && <div className="mt-1 text-xs text-rose-600">Abnormal: {abnormal.map((f) => `${f.label} ${f.value} ${f.unit}`).join(", ")}</div>}
              </div>
              <Badge tone={statusTone(report?.reviewStatus ?? t.status)}>{titleCase(report?.reviewStatus ?? t.status)}</Badge>
              {report && <button onClick={() => setDoc(report)} className="rounded-lg px-2.5 py-1.5 text-xs font-medium text-brand-700 ring-1 ring-brand-200 hover:bg-brand-50">Open report</button>}
            </motion.div>
          );
        })}
      </Card>
      <DocumentModal doc={doc} onClose={() => setDoc(null)} canReview onReviewed={reload} />
    </div>
  );
}
