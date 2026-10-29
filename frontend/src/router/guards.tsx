import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSession } from "@/hooks/useSession";
import { ROLE_HOME, type Role } from "@/lib/constants";

function Loading() {
  return <div className="grid min-h-screen place-items-center text-sm text-ink-500">Loading…</div>;
}

/** Replaces the Next.js middleware: each role only reaches its own dashboard area. */
export function RequireRole({ roles }: { roles: Role[] }) {
  const { me, loading } = useSession();
  const location = useLocation();
  if (loading) return <Loading />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname + location.search)}`} replace />;
  if (!roles.includes(me.user.role)) return <Navigate to={ROLE_HOME[me.user.role]} replace />;
  return <Outlet />;
}

/** Login / sign-up: a signed-in user goes straight to their dashboard. */
export function PublicOnly() {
  const { me, loading } = useSession();
  if (loading) return <Loading />;
  if (me) return <Navigate to={ROLE_HOME[me.user.role]} replace />;
  return <Outlet />;
}
