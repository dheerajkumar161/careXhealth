import { Outlet } from "react-router-dom";
import { FlaskConical, CalendarDays, Settings } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function ProviderLayout() {
  return (
    <AppShell
      nav={[
        { href: "/provider", label: "Tests", icon: FlaskConical, exact: true },
        { href: "/provider/schedule", label: "Schedule", icon: CalendarDays },
        { href: "/provider/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
