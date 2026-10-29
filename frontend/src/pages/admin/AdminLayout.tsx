import { Outlet } from "react-router-dom";
import { ScrollText, Settings, Users } from "lucide-react";
import { AppShell } from "@/components/AppShell";

export default function AdminLayout() {
  return (
    <AppShell
      nav={[
        { href: "/admin", label: "Audit log", icon: ScrollText, exact: true },
        { href: "/admin/users", label: "Users", icon: Users },
        { href: "/admin/settings", label: "Profile & settings", icon: Settings },
      ]}
    >
      <Outlet />
    </AppShell>
  );
}
