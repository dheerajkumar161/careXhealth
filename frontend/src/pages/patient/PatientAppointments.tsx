import { CalendarClock } from "lucide-react";
import { Card, CardHeader, EmptyState, PageHeader, PageSkeleton } from "@/components/ui";
import { AppointmentRow, ReferralTracker } from "@/components/clinical/widgets";
import { useApi } from "@/hooks/useApi";
import type { PatientRecord } from "@/types";

export default function PatientAppointments() {
  const { data } = useApi<PatientRecord>("/api/overview");
  if (!data) return <PageSkeleton />;
  const now = new Date();
  const list = data.appointments.filter((a) => a.status !== "CANCELLED");
  const upcoming = list.filter((a) => new Date(a.startsAt) >= now && a.status !== "MISSED");
  const past = list.filter((a) => !upcoming.includes(a)).reverse();
  return (
    <div>
      <PageHeader eyebrow="Booked for you automatically" title="Appointments" subtitle="Tests, follow-ups and therapy sessions are booked by your care team’s scheduling agent. Missed sessions are rebooked for you." />
      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card>
            <CardHeader title={`Upcoming (${upcoming.length})`} icon={<CalendarClock className="size-4" />} />
            <div className="space-y-2 px-5 pb-5">
              {!upcoming.length && <EmptyState icon={<CalendarClock className="size-5" />} title="Nothing upcoming" />}
              {upcoming.map((a) => <AppointmentRow key={a.id} a={a} />)}
            </div>
          </Card>
          {!!past.length && (
            <Card>
              <CardHeader title="Past" icon={<CalendarClock className="size-4" />} />
              <div className="space-y-2 px-5 pb-5">{past.map((a) => <AppointmentRow key={a.id} a={a} />)}</div>
            </Card>
          )}
        </div>
        <div className="space-y-4">
          <h3 className="text-sm font-semibold text-ink-700">Extra care arranged for you</h3>
          {!data.referrals.length && <p className="text-sm text-ink-500">No referrals.</p>}
          {data.referrals.map((r) => <ReferralTracker key={r.id} referral={r} />)}
        </div>
      </div>
    </div>
  );
}
