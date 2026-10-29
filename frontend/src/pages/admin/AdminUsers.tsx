import { Users } from "lucide-react";
import { toast } from "sonner";
import { Badge, Button, Card, PageHeader, PageSkeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { api } from "@/services/api";
import { ROLE_LABEL, type Role } from "@/lib/constants";
import { fmtDate } from "@/lib/format";
import { useT } from "@/i18n";

type U = { id: string; name: string; email: string; role: Role; department?: string | null; language: string; createdAt: string };

export default function AdminUsers() {
  const t = useT();
  const { data, error } = useApi<{ users: U[] }>("/api/admin/users");
  if (error) return <p className="text-sm text-rose-600">{error}</p>;
  if (!data) return <PageSkeleton />;
  return (
    <div>
      <PageHeader title={t("Users")} subtitle={`${data.users.length} accounts`} eyebrow={<Users className="size-4" />} />
      <Card className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-xs text-ink-500">
            <tr>{["Name", "Email", "Role", "Department", "Language", "Created", ""].map((h) => <th key={h} className="px-4 py-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {data.users.map((u) => (
              <tr key={u.id} className="border-b border-line/60 last:border-0">
                <td className="px-4 py-2.5 font-medium">{u.name}</td>
                <td className="px-4 py-2.5 text-ink-500">{u.email}</td>
                <td className="px-4 py-2.5"><Badge tone="blue">{ROLE_LABEL[u.role] ?? u.role}</Badge></td>
                <td className="px-4 py-2.5 text-ink-500">{u.department ?? "—"}</td>
                <td className="px-4 py-2.5 uppercase text-ink-500">{u.language}</td>
                <td className="px-4 py-2.5 text-xs text-ink-500">{fmtDate(u.createdAt, "d MMM yyyy")}</td>
                <td className="px-4 py-2.5 text-right">
                  <Button size="sm" variant="secondary" onClick={async () => { await api(`/api/admin/users/${u.id}/revoke-sessions`, { method: "POST", body: {} }); toast.success(`${u.name} signed out everywhere`); }}>
                    Sign out everywhere
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
