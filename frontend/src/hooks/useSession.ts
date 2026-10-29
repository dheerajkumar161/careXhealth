import { useEffect, useState } from "react";
import type { Role } from "@/lib/constants";
import { setDemoMode } from "@/lib/demo";
import { setLang } from "@/i18n";

export type Me = {
  user: {
    id: string;
    name: string;
    email: string;
    role: Role;
    department?: string | null;
    title?: string | null;
    phone?: string | null;
    address?: string | null;
    language: string;
    notifyEmail?: boolean;
    notifySms?: boolean;
    providerProfile?: { organization: string; type: string; location?: string } | null;
    patientProfile?: { id: string; mrn: string; emergencyContact?: string | null; address?: string | null } | null;
  };
  languages: { code: string; name: string; native: string }[];
  ai: { configured: boolean; available: boolean; primary: "groq" | "ollama" | "rules"; model: string | null; chain: string[]; visionModel: string | null };
  demoMode: boolean;
};

/** Current session from /api/auth/me; `null` when signed out (no redirect side effects — the guards decide). */
export function useSession() {
  const [state, setState] = useState<{ me: Me | null; loading: boolean }>({ me: null, loading: true });
  useEffect(() => {
    let alive = true;
    fetch("/api/auth/me", { credentials: "same-origin", cache: "no-store" })
      .then(async (r) => (r.ok ? ((await r.json()) as Me) : null))
      .catch(() => null)
      .then((me) => {
        if (!alive) return;
        if (me) {
          setDemoMode(me.demoMode);
          setLang(me.user.language);
        }
        setState({ me, loading: false });
      });
    return () => {
      alive = false;
    };
  }, []);
  return state;
}
