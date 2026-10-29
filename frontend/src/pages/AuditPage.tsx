import { useState } from "react";
import { ScrollText } from "lucide-react";
import { Badge, Card, EmptyState, PageHeader, PageSkeleton, Select } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { fmtDate } from "@/lib/format";
import { useT } from "@/i18n";

type Entry = { id: string; at: string; actorId?: string | null; actorName?: string | null; actorRole?: string | null; action: string; entityType?: string | null; entityId?: string | null; patientId?: string | null; detail?: string | null; ip?: string | null };

const tone = (a: string) => (a.includes("FAILED") || a.includes("LOCKED") || a === "SESSIONS_REVOKED" ? "red" : a.startsWith("PLAN_") ? "violet" : a.startsWith("DOCUMENT") || a === "RECORD_VIEW" ? "blue" : "gray") as "red" | "violet" | "blue" | "gray";

/** Immutable audit trail — administrators see everything, doctors see activity on their own patients. */
export default function AuditPage() {
  const t = useT();
  const [action, setAction] = useState("");
  const { data, error } = useApi<{ entries: Entry[] }>(`/api/audit?limit=200${action ? `&action=${action}` : ""}`, { poll: 20000 });
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!data) return <PageSkeleton />;
  const actions = ["", "LOGIN", "LOGIN_FAILED", "LOGIN_LOCKED", "LOGOUT", "PASSWORD_CHANGE", "PROFILE_UPDATE", "PLAN_APPROVE", "PLAN_REJECT", "RECORD_VIEW", "DOCUMENT_DOWNLOAD", "ALERT_ACKNOWLEDGE", "ALERT_RESOLVE"];
  return (
    <div>
      <PageHeader title={t("Audit log")} subtitle="Who did what, when — append-only." actions={
        <Select value={action} onChange={(e) => setAction(e.target.value)} className="w-52" aria-label="Filter by action">
          {actions.map((a) => <option key={a} value={a}>{a || "All actions"}</option>)}
        </Select>
      } />
      <Card className="overflow-x-auto">
        {!data.entries.length ? (
          <EmptyState icon={<ScrollText className="size-5" />} title="No audit entries yet" />
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line text-xs text-ink-500">
              <tr>{["When", "Who", "Action", "Target", "Detail", "IP"].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.entries.map((e) => (
                <tr key={e.id} className="border-b border-line/60 last:border-0">
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-ink-500">{fmtDate(e.at, "d MMM, h:mm:ss a")}</td>
                  <td className="px-4 py-2.5">{e.actorName ?? <span className="text-ink-400">—</span>}{e.actorRole && <span className="ml-1 text-[11px] text-ink-400">{e.actorRole}</span>}</td>
                  <td className="px-4 py-2.5"><Badge tone={tone(e.action)}>{e.action}</Badge></td>
                  <td className="px-4 py-2.5 text-xs text-ink-500">{e.entityType ?? ""}{e.entityId ? ` ${e.entityId.slice(0, 8)}…` : ""}</td>
                  <td className="max-w-xs truncate px-4 py-2.5 text-xs text-ink-500" title={e.detail ?? ""}>{e.detail}</td>
                  <td className="px-4 py-2.5 text-xs text-ink-400">{e.ip}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
