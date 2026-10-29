import { CalendarDays } from "lucide-react";
import { Avatar, Card, EmptyState, PageHeader, PageSkeleton } from "@/components/ui";
import { useApi } from "@/hooks/useApi";
import { fmtDate } from "@/lib/format";
import { SessionActions, type ProviderOverview } from "@/components/ProviderShared";

export default function ProviderSchedule() {
  const { data, reload } = useApi<ProviderOverview>("/api/overview", { poll: 30000 });
  if (!data) return <PageSkeleton />;
  const from = new Date();
  from.setHours(0, 0, 0, 0);
  from.setDate(from.getDate() - 3);
  const list = data.appointments.filter((a) => new Date(a.startsAt) >= from && !["CANCELLED", "TENTATIVE"].includes(a.status));
  const days = new Map<string, typeof list>();
  for (const a of list) {
    const k = new Date(a.startsAt).toDateString();
    days.set(k, [...(days.get(k) ?? []), a]);
  }
  return (
    <div>
      <PageHeader eyebrow={data.provider.organization} title="Schedule" subtitle="Confirmed bookings from CareXHealth. Mark attendance after each session; missed sessions are rebooked automatically." />
      {!days.size && <Card className="p-5"><EmptyState icon={<CalendarDays className="size-5" />} title="No bookings" /></Card>}
      <div className="space-y-5">
        {[...days.entries()].map(([k, appts]) => {
          const isToday = k === new Date().toDateString();
          return (
            <div key={k}>
              <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                {fmtDate(appts[0].startsAt, "EEEE, d MMMM")}
                {isToday && <span className="rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold text-white">Today</span>}
              </div>
              <Card className="divide-y divide-line">
                {appts.map((a) => (
                  <div key={a.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                    <span className="w-16 text-sm font-semibold text-ink-700">{fmtDate(a.startsAt, "h:mm a")}</span>
                    <Avatar name={a.patient.user.name} size={32} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium">{a.patient.user.name}</div>
                      <div className="text-xs text-ink-500">{a.title}</div>
                    </div>
                    {a.kind !== "TEST" ? <SessionActions a={a} onDone={reload} /> : <span className="text-xs text-ink-500">{a.status.toLowerCase()}</span>}
                  </div>
                ))}
              </Card>
            </div>
          );
        })}
      </div>
    </div>
  );
}
