import { Outlet } from "react-router-dom";
import { Home, ClipboardCheck, CalendarDays, FileText, Settings } from "lucide-react";
import { AppShell } from "@/components/AppShell";

/** Read-only family view: every form control and button inside is disabled (the API also refuses writes). */
export default function CaregiverLayout() {
  return (
    <AppShell
      nav={[
        { href: "/caregiver", label: "Today", icon: Home, exact: true },
        { href: "/caregiver/plan", label: "My care plan", icon: ClipboardCheck },
        { href: "/caregiver/appointments", label: "Appointments", icon: CalendarDays },
        { href: "/caregiver/documents", label: "Documents", icon: FileText },
        { href: "/caregiver/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <div className="mb-4 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2 text-xs text-sky-800">You are viewing this recovery as a caregiver — read-only. The patient can remove your access at any time.</div>
      <fieldset disabled className="m-0 min-w-0 border-0 p-0">
        <Outlet />
      </fieldset>
    </AppShell>
  );
}
