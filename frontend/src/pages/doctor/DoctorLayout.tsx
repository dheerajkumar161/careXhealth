import { Outlet } from "react-router-dom";
import { FlaskConical, LayoutDashboard, Users, TriangleAlert, Send, Settings, ScrollText } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function DoctorLayout() {
  return (
    <AppShell
      allowCycle
      nav={[
        { href: "/doctor", label: "Overview", icon: LayoutDashboard, exact: true },
        { href: "/doctor/patients", label: "Patients", icon: Users },
        { href: "/doctor/referrals", label: "Referrals", icon: Send },
        { href: "/doctor/tests", label: "Tests", icon: FlaskConical },
        { href: "/doctor/alerts", label: "Alerts & escalations", icon: TriangleAlert },
        { href: "/doctor/audit", label: "Audit log", icon: ScrollText },
        { href: "/doctor/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
