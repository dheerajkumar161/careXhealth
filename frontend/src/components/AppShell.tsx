import { AnimatePresence, motion } from "framer-motion";
import { Bell, BellRing, CalendarCheck2, FileText, HeartPulse, LogOut, Menu, RefreshCw, Sparkles, TriangleAlert, Users, X, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { setLang, useT } from "@/i18n";
import AutoTranslate from "@/i18n/AutoTranslate";
import { useLocation, useNavigate } from "react-router-dom";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Avatar, Badge } from "./ui";
import { api } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { ago, cn } from "@/lib/format";
import { ROLE_HOME, ROLE_LABEL } from "@/lib/constants";
import type { Me } from "@/hooks/useSession";
import { setDemoMode } from "@/lib/demo";
import { demoMode } from "@/lib/demo";

export type NavItem = { href: string; label: string; icon: LucideIcon; exact?: boolean };

type Notif = { id: string; type: string; title: string; body: string; link?: string; read: boolean; createdAt: string };

const NOTIF_ICON: Record<string, LucideIcon> = { ALERT: TriangleAlert, APPOINTMENT: CalendarCheck2, DOCUMENT: FileText, REFERRAL: Users, REMINDER: BellRing, CARE_PLAN: Sparkles };

function Notifications() {
  const t = useT();
  const { data, reload, setData } = useApi<{ items: Notif[]; unread: number }>("/api/notifications", { poll: 60000 }); // SSE below pushes changes; polling is only the fallback
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"new" | "seen">("new");
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const prevUnread = useRef<number | null>(null);

  // Live updates: the server pushes an event when a notification/alert arrives (falls back to the 60 s poll if SSE is unavailable)
  useEffect(() => {
    if (typeof EventSource === "undefined") return;
    const es = new EventSource("/api/stream");
    const onNotification = () => {
      reload();
      window.dispatchEvent(new Event("agents:cycle")); // dashboards listening for fresh data refresh immediately
    };
    es.addEventListener("notification", onNotification);
    return () => es.close();
  }, [reload]);

  useEffect(() => {
    if (!data) return;
    if (prevUnread.current !== null && data.unread > prevUnread.current) {
      const n = data.items.find((i) => !i.read);
      if (n)
        (n.type === "ALERT" ? toast.warning : toast.info)(n.title, {
          description: n.body,
          duration: 8000,
          action: n.link ? { label: "Open", onClick: () => openItem(n) } : undefined,
        });
    }
    prevUnread.current = data.unread;
  }, [data]);

  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  // Optimistically move items to "Seen" so the change is visible immediately
  function markLocal(ids: string[] | "all") {
    setData((d) => (d ? { unread: ids === "all" ? 0 : Math.max(d.unread - ids.length, 0), items: d.items.map((i) => (ids === "all" || ids.includes(i.id) ? { ...i, read: true } : i)) } : d));
  }

  async function openItem(n: Notif) {
    if (!n.read) {
      markLocal([n.id]);
      await api("/api/notifications", { body: { id: n.id } });
    }
    setOpen(false);
    reload();
    if (n.link) navigate(n.link);
  }

  async function markSeen(e: React.MouseEvent, n: Notif) {
    e.stopPropagation();
    markLocal([n.id]);
    await api("/api/notifications", { body: { id: n.id } });
  }

  const fresh = data?.items.filter((i) => !i.read) ?? [];
  const seen = data?.items.filter((i) => i.read) ?? [];
  const list = tab === "new" ? fresh : seen;

  return (
    <div className="relative" ref={ref}>
      <button onClick={() => { setOpen((o) => !o); setTab(fresh.length ? "new" : "seen"); }} className="relative grid size-10 place-items-center rounded-xl border border-line bg-white text-ink-700 transition hover:bg-slate-50" aria-label="Notifications">
        <motion.span animate={data?.unread ? { rotate: [0, -14, 12, -8, 0] } : {}} transition={{ duration: 0.6, repeat: data?.unread ? Infinity : 0, repeatDelay: 4 }}>
          <Bell className="size-[18px]" />
        </motion.span>
        {!!data?.unread && <span className="absolute -right-1 -top-1 grid min-w-5 h-5 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white ring-2 ring-white">{data.unread > 99 ? "99+" : data.unread}</span>}
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -6, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -6 }} className="absolute right-0 z-40 mt-2 w-[min(400px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-white shadow-[var(--shadow-lift)]">
            <div className="flex items-center justify-between px-4 pt-3">
              <span className="text-sm font-semibold">{t("Notifications")}</span>
              {!!fresh.length && (
                <button onClick={async () => { markLocal("all"); await api("/api/notifications", { body: { all: true } }); setTab("seen"); }} className="text-xs font-medium text-brand-600 hover:underline">
                  {t("Mark all as seen")}
                </button>
              )}
            </div>
            <div className="mt-2 flex gap-1 border-b border-line px-3">
              {([["new", t("New"), fresh.length], ["seen", t("Seen"), seen.length]] as const).map(([id, label, count]) => (
                <button key={id} onClick={() => setTab(id)} className={cn("relative px-3 pb-2 pt-1 text-xs font-semibold transition", tab === id ? "text-ink-900" : "text-ink-400 hover:text-ink-700")}>
                  {label}
                  <span className={cn("ml-1.5 rounded-full px-1.5 py-0.5 text-[10px]", id === "new" && count ? "bg-rose-500 text-white" : "bg-slate-100 text-ink-500")}>{count}</span>
                  {tab === id && <motion.span layoutId="notif-tab" className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-brand-600" />}
                </button>
              ))}
            </div>
            <div className="max-h-[440px] overflow-y-auto">
              {!list.length && <p className="px-4 py-10 text-center text-sm text-ink-500">{tab === "new" ? t("You're all caught up.") : t("Nothing seen yet.")}</p>}
              <AnimatePresence initial={false}>
                {list.map((n) => {
                  const Icon = NOTIF_ICON[n.type] ?? Bell;
                  const isNew = !n.read;
                  return (
                    <motion.div key={n.id} layout initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -24, height: 0 }} transition={{ duration: 0.2 }}>
                      <button onClick={() => openItem(n)} className={cn("group relative flex w-full gap-3 border-b border-line/70 px-4 py-3 text-left transition", isNew ? "bg-brand-50/60 hover:bg-brand-50" : "bg-white hover:bg-slate-50")}>
                        {isNew && <span className={cn("absolute inset-y-0 left-0 w-1", n.type === "ALERT" ? "bg-rose-500" : "bg-brand-500")} />}
                        <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg", !isNew ? "bg-slate-100 text-ink-400" : n.type === "ALERT" ? "bg-rose-100 text-rose-600" : "bg-brand-100 text-brand-700")}>
                          <Icon className="size-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className={cn("block text-[13px]", isNew ? "font-semibold text-ink-900" : "font-normal text-ink-500")}>{n.title}</span>
                          <span className={cn("mt-0.5 line-clamp-2 block text-xs", isNew ? "text-ink-700" : "text-ink-400")}>{n.body}</span>
                          <span className="mt-1 block text-[11px] text-ink-400">{ago(n.createdAt)}</span>
                        </span>
                        {isNew && (
                          <span onClick={(e) => markSeen(e, n)} title="Mark as seen" className="mt-0.5 h-fit rounded-md px-1.5 py-0.5 text-[10px] font-semibold text-brand-700 opacity-0 ring-1 ring-brand-200 transition group-hover:opacity-100 hover:bg-white">
                            Seen
                          </span>
                        )}
                      </button>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function AgentPulse({ me, onCycle }: { me: Me | null; onCycle?: () => void }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  return (
    <button
      disabled={busy || !onCycle}
      onClick={async () => {
        if (!onCycle) return;
        setBusy(true);
        try {
          await onCycle();
        } finally {
          setBusy(false);
        }
      }}
      title={onCycle ? "Run an agent monitoring cycle now" : undefined}
      className="hidden md:flex items-center gap-2 rounded-xl border border-line bg-white px-3 h-10 text-xs font-medium text-ink-700 transition enabled:hover:bg-slate-50"
    >
      <span className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
        <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
      </span>
      {t("Agents live")}
      <span title={me ? `LLM chain: ${me.ai.chain.join(" → ")}` : undefined}>
        <Badge tone={me?.ai.available ? "brand" : "gray"}>{me?.ai.available ? `${me.ai.primary === "groq" ? "Groq" : "Ollama"} · ${me.ai.model?.split("/").pop()}` : "Rule engine"}</Badge>
      </span>
      {onCycle && <RefreshCw className={cn("size-3.5 text-ink-400", busy && "animate-spin")} />}
    </button>
  );
}

export function AppShell({ nav, children, allowCycle }: { nav: NavItem[]; children: ReactNode; allowCycle?: boolean }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const t = useT();
  const { data: me } = useApi<Me>("/api/auth/me");
  if (me) setDemoMode(me.demoMode);
  // Apply the saved language once per session load (not on every render, or it would undo a change made in Settings)
  const savedLang = me?.user.language;
  useEffect(() => {
    if (savedLang) setLang(savedLang);
  }, [savedLang]);
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    setMobile(false);
  }, [pathname]);

  async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    navigate("/login", { replace: true });
  }

  async function cycle() {
    const r = await api<{ reminders: number; escalated: number; patientsChecked: number }>("/api/agents/cycle", { method: "POST" });
    toast.success("Agent cycle complete", { description: `${r.patientsChecked} patients checked · ${r.reminders} reminders · ${r.escalated} escalations` });
    window.dispatchEvent(new Event("agents:cycle"));
  }

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="grid size-9 place-items-center rounded-xl bg-brand-600 text-white shadow-md shadow-brand-600/25">
          <HeartPulse className="size-[18px]" />
        </div>
        <div>
          <div className="font-display text-[15px] font-bold leading-tight">CareXHealth</div>
          <div className="text-[11px] text-ink-500">{me ? ROLE_LABEL[me.user.role] : " "} {t("workspace")}</div>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {nav.map((n) => {
          const active = n.exact ? pathname === n.href : pathname === n.href || pathname.startsWith(n.href + "/");
          return (
            <Link key={n.href} to={n.href} className={cn("relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors", active ? "text-brand-700" : "text-ink-500 hover:bg-slate-50 hover:text-ink-900")}>
              {active && <motion.span layoutId="nav-active" className="absolute inset-0 rounded-xl bg-brand-50 ring-1 ring-brand-100" transition={{ type: "spring", damping: 30, stiffness: 380 }} />}
              <n.icon className="relative size-[18px]" />
              <span className="relative">{t(n.label)}</span>
            </Link>
          );
        })}
      </nav>
      <div className="m-3 rounded-2xl border border-line bg-slate-50/70 p-3">
        <div className="flex items-center gap-3">
          <Link to={`${me ? ROLE_HOME[me.user.role] : ""}/settings`} className="flex min-w-0 flex-1 items-center gap-3" title={t("Profile & settings")}>
            <Avatar name={me?.user.name ?? "··"} size={36} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{me?.user.name ?? "…"}</div>
              <div className="truncate text-[11px] text-ink-500">{me?.user.providerProfile?.organization ?? me?.user.title ?? me?.user.email}</div>
            </div>
          </Link>
          <button onClick={logout} className="rounded-lg p-2 text-ink-500 transition hover:bg-white hover:text-rose-600" title={t("Sign out")}>
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 border-r border-line bg-white lg:block">{sidebar}</aside>
      <AnimatePresence>
        {mobile && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-slate-900/30 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMobile(false)} />
            <motion.aside className="fixed inset-y-0 left-0 z-50 w-72 bg-white lg:hidden" initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }} transition={{ type: "spring", damping: 30, stiffness: 300 }}>
              <button className="absolute right-3 top-5 rounded-lg p-1.5 text-ink-500" onClick={() => setMobile(false)}>
                <X className="size-4" />
              </button>
              {sidebar}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between gap-3 border-b border-line bg-white/80 px-4 backdrop-blur-md sm:px-8">
          <button className="rounded-lg p-2 text-ink-700 lg:hidden" onClick={() => setMobile(true)}>
            <Menu className="size-5" />
          </button>
          <div className="hidden text-sm text-ink-500 lg:block">{new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}</div>
          <div className="flex items-center gap-2">
            <AgentPulse me={me} onCycle={allowCycle ? cycle : undefined} />
            <Notifications />
          </div>
        </header>
        {demoMode() && (
          <div className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-center text-xs font-medium text-amber-800 sm:px-8">
            Demo mode — time windows are relaxed so you can record doses, sessions and results ahead of schedule.
          </div>
        )}
        <main className="mx-auto max-w-[1400px] px-4 py-6 sm:px-8 sm:py-8"><AutoTranslate>{children}</AutoTranslate></main>
      </div>
    </div>
  );
}
