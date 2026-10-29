import { Outlet } from "react-router-dom";
import { Home, ClipboardCheck, CalendarDays, FileText, MessageCircleHeart, Settings } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function PatientLayout() {
  return (
    <AppShell
      nav={[
        { href: "/patient", label: "Today", icon: Home, exact: true },
        { href: "/patient/plan", label: "My care plan", icon: ClipboardCheck },
        { href: "/patient/appointments", label: "Appointments", icon: CalendarDays },
        { href: "/patient/documents", label: "Documents", icon: FileText },
        { href: "/patient/assistant", label: "Care assistant", icon: MessageCircleHeart },
        { href: "/patient/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
