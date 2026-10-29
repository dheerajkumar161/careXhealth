import { AnimatePresence, motion } from "framer-motion";
import { HeartPulse, SendHorizontal, ShieldCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Avatar, Button, Card, Markdown, PageSkeleton } from "@/components/ui";
import { api } from "@/services/api";
import { useApi } from "@/hooks/useApi";
import { cn, fmtDate } from "@/lib/format";
import type { PatientRecord } from "@/types";

type Msg = { id: string; role: "user" | "assistant"; content: string; createdAt: string };

const SUGGESTIONS = ["What medicines do I need to take today?", "When is my next appointment?", "What should I avoid doing?", "What foods should I eat?", "When should I call the nurse?", "My temperature is 100.8 and the knee feels warm"];

function Typing() {
  return (
    <div className="flex gap-1 px-1 py-1.5">
      {[0, 1, 2].map((i) => (
        <motion.span key={i} className="size-2 rounded-full bg-brand-400" animate={{ y: [0, -5, 0], opacity: [0.5, 1, 0.5] }} transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }} />
      ))}
    </div>
  );
}

export default function Assistant() {
  const { data: rec } = useApi<PatientRecord>("/api/overview");
  const pid = rec?.patient.id;
  const { data, setData } = useApi<{ messages: Msg[] }>(pid ? `/api/patients/${pid}/chat` : null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Block body: newer Chromium returns a Promise from scrollIntoView, which React would treat as a cleanup function
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [data?.messages.length, busy]);

  async function send(message: string) {
    if (!pid || !message.trim() || busy) return;
    const optimistic: Msg = { id: `tmp-${Date.now()}`, role: "user", content: message, createdAt: new Date().toISOString() };
    setData((d) => ({ messages: [...(d?.messages ?? []), optimistic] }));
    setText("");
    setBusy(true);
    try {
      const res = await api<{ reply: Msg }>(`/api/patients/${pid}/chat`, { body: { message } });
      setData((d) => ({ messages: [...(d?.messages ?? []), res.reply] }));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Message failed");
    } finally {
      setBusy(false);
    }
  }

  if (!rec) return <PageSkeleton />;
  const msgs = data?.messages ?? [];

  return (
    <div className="mx-auto max-w-3xl">
      <Card className="flex h-[calc(100vh-9rem)] flex-col overflow-hidden">
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <div className="relative grid size-10 place-items-center rounded-xl bg-brand-600 text-white">
            <HeartPulse className="size-5" />
            <span className="absolute -right-0.5 -bottom-0.5 size-3 rounded-full bg-emerald-400 ring-2 ring-white" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-semibold">Care assistant</div>
            <div className="text-xs text-ink-500">Answers from your doctor-approved plan · shares symptoms with your care team</div>
          </div>
          <ShieldCheck className="size-5 text-brand-500" />
        </div>

        <div className="flex-1 space-y-4 overflow-y-auto bg-slate-50/50 px-5 py-5">
          {!msgs.length && (
            <div className="py-6 text-center">
              <p className="text-sm font-medium">Hi {rec.patient.user.name.split(" ")[0]} 👋 How can I help with your recovery today?</p>
              <p className="mt-1 text-xs text-ink-500">I can explain your medicines, appointments, tests, diet and warning signs.</p>
            </div>
          )}
          <AnimatePresence initial={false}>
            {msgs.map((m) => (
              <motion.div key={m.id} initial={{ opacity: 0, y: 8, scale: 0.98 }} animate={{ opacity: 1, y: 0, scale: 1 }} className={cn("flex gap-2.5", m.role === "user" && "flex-row-reverse")}>
                {m.role === "user" ? <Avatar name={rec.patient.user.name} size={30} tone="sky" /> : <div className="grid size-[30px] shrink-0 place-items-center rounded-full bg-brand-600 text-white"><HeartPulse className="size-3.5" /></div>}
                <div className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-sm", m.role === "user" ? "rounded-tr-md bg-brand-600 text-white" : "rounded-tl-md bg-white ring-1 ring-line")}>
                  {m.role === "user" ? m.content : <Markdown className="[&_p]:my-1">{m.content}</Markdown>}
                  <div className={cn("mt-1 text-[10px]", m.role === "user" ? "text-brand-100" : "text-ink-400")}>{fmtDate(m.createdAt, "h:mm a")}</div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          {busy && (
            <div className="flex gap-2.5">
              <div className="grid size-[30px] place-items-center rounded-full bg-brand-600 text-white"><HeartPulse className="size-3.5" /></div>
              <div className="rounded-2xl rounded-tl-md bg-white px-3 ring-1 ring-line"><Typing /></div>
            </div>
          )}
          <div ref={end} />
        </div>

        <div className="border-t border-line bg-white p-4">
          <div className="mb-2.5 flex gap-1.5 overflow-x-auto pb-1">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="shrink-0 rounded-full bg-slate-50 px-3 py-1.5 text-xs text-ink-700 ring-1 ring-line transition hover:bg-brand-50 hover:ring-brand-200">{s}</button>
            ))}
          </div>
          <form onSubmit={(e) => { e.preventDefault(); send(text); }} className="flex gap-2">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Type your question or describe how you feel…" className="h-11 flex-1 rounded-xl border border-line px-4 text-sm outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-100" />
            <Button type="submit" size="lg" disabled={!text.trim() || busy} className="h-11 px-4"><SendHorizontal className="size-4" /></Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
