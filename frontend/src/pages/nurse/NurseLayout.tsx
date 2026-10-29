import { Outlet } from "react-router-dom";
import { LayoutDashboard, Users, TriangleAlert, ClipboardList, Settings } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function NurseLayout() {
  return (
    <AppShell
      allowCycle
      nav={[
        { href: "/nurse", label: "Shift overview", icon: LayoutDashboard, exact: true },
        { href: "/nurse/patients", label: "My patients", icon: Users },
        { href: "/nurse/alerts", label: "Alert queue", icon: TriangleAlert },
        { href: "/nurse/handoffs", label: "Handoffs", icon: ClipboardList },
        { href: "/nurse/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
