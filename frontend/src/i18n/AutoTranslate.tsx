import { useEffect, useRef, type ReactNode } from "react";
import { isTranslatedOutput, translate, useLang } from "./index";

const SKIP = new Set(["SCRIPT", "STYLE", "CODE", "PRE", "TEXTAREA", "INPUT", "SELECT", "OPTION", "KBD", "SVG"]);
// something worth translating: contains a run of letters, is not an e-mail / URL / pure number or time
const WORDY = /\p{L}{2,}/u;
const SKIP_TEXT = /^(?:\S+@\S+\.\S+|https?:\/\/\S+|[\d\s.,:/%°+\-–—()]+)$/u;

const NON_LATIN = new Set(["hi", "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "ur", "ar"]);

/** Text that is already mostly in a non-Latin target script (e.g. a server-translated plan) needs no second pass. */
function alreadyTargetScript(lang: string, text: string) {
  if (!NON_LATIN.has(lang)) return false;
  const latin = (text.match(/[A-Za-z]/g) ?? []).length;
  const letters = (text.match(/\p{L}/gu) ?? []).length;
  return letters > 0 && latin / letters < 0.5;
}

type Seen = { src: string; shown: string };

/**
 * Translates all visible text under it into the user's language (chosen in Settings), including dynamic content such as
 * plan items, appointment titles and notifications. Built-in dictionary first, then the backend translator (cached).
 * Text nodes are rewritten in place, so React keeps working and switching back to English restores the originals.
 */
export default function AutoTranslate({ children, className }: { children: ReactNode; className?: string }) {
  const lang = useLang();
  const root = useRef<HTMLDivElement>(null);
  const seen = useRef(new WeakMap<Text, Seen>());
  const nodes = useRef(new Set<WeakRef<Text>>());

  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let raf = 0;
    let busy = false;

    const apply = () => {
      busy = true;
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
        acceptNode(n) {
          for (let p = n.parentElement; p && p !== el; p = p.parentElement) {
            if (SKIP.has(p.tagName.toUpperCase()) || p.getAttribute("translate") === "no" || p.classList.contains("notranslate")) return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      for (let n = walker.nextNode() as Text | null; n; n = walker.nextNode() as Text | null) {
        const rec = seen.current.get(n);
        const current = n.nodeValue ?? "";
        // a node whose text changed since we last wrote it carries a new English source (React re-rendered it)
        const src = rec && current === rec.shown ? rec.src : current;
        if (lang === "en") {
          if (rec && current === rec.shown && rec.src !== current) n.nodeValue = rec.src;
          continue;
        }
        const trimmed = src.trim();
        if (!trimmed || !WORDY.test(trimmed) || SKIP_TEXT.test(trimmed) || isTranslatedOutput(trimmed) || alreadyTargetScript(lang, trimmed)) continue;
        const out = translate(trimmed);
        const shown = out === trimmed ? src : src.replace(trimmed, out);
        seen.current.set(n, { src, shown });
        nodes.current.add(new WeakRef(n));
        if (shown !== current) n.nodeValue = shown;
      }
      busy = false;
    };

    const schedule = () => {
      if (busy) return;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(apply);
    };

    apply();
    const mo = new MutationObserver(schedule);
    mo.observe(el, { childList: true, subtree: true, characterData: true });
    return () => {
      mo.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [lang]);

  return (
    <div ref={root} className={className}>
      {children}
    </div>
  );
}
