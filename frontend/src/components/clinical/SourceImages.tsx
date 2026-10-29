import { ImageIcon, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Markdown, Modal } from "../ui";
import { api } from "@/services/api";
import type { Doc } from "@/types";

/** Lazily loads the original image behind a SOURCE_NOTE document (images are not included in list payloads). */
export function SourceImage({ docId, className, onClick }: { docId: string; className?: string; onClick?: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    api<{ dataUrl: string }>(`/api/documents/${docId}/image`)
      .then((r) => alive && setUrl(r.dataUrl))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [docId]);
  if (failed) return <div className={`grid place-items-center bg-slate-50 text-ink-400 ${className}`}><ImageIcon className="size-5" /></div>;
  if (!url) return <div className={`grid place-items-center bg-slate-50 text-ink-400 ${className}`}><Loader2 className="size-4 animate-spin" /></div>;
  return <img src={url} alt="Source document" className={`object-cover ${onClick ? "cursor-zoom-in" : ""} ${className}`} onClick={onClick} />;
}

/** Side-by-side: original image and what the agent read from it — so the doctor can verify before approving. */
export function SourceViewer({ doc, onClose }: { doc: Doc | null; onClose: () => void }) {
  return (
    <Modal open={!!doc} onClose={onClose} size="xl" title={doc?.title} subtitle="Original image beside the agent's transcript — check every line before approving">
      {doc && (
        <div className="grid gap-5 lg:grid-cols-2">
          <div className="overflow-hidden rounded-xl border border-line bg-slate-50">
            <SourceImage docId={doc.id} className="h-auto w-full !object-contain" />
          </div>
          <Markdown>{doc.content}</Markdown>
        </div>
      )}
    </Modal>
  );
}

export function SourceStrip({ docs }: { docs: Doc[] }) {
  const [open, setOpen] = useState<Doc | null>(null);
  if (!docs.length) return null;
  return (
    <div className="mt-3">
      <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-500">Read from {docs.length} attached image{docs.length > 1 ? "s" : ""} — click to verify</div>
      <div className="flex flex-wrap gap-2">
        {docs.map((d) => (
          <button key={d.id} onClick={() => setOpen(d)} className="group relative h-20 w-20 overflow-hidden rounded-xl border border-line bg-white ring-brand-300 transition hover:ring-2">
            <SourceImage docId={d.id} className="size-full" />
            <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent px-1 pb-0.5 pt-3 text-[9px] text-white">Verify</span>
          </button>
        ))}
      </div>
      <SourceViewer doc={open} onClose={() => setOpen(null)} />
    </div>
  );
}
