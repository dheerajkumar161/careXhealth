import { createElement, Fragment, useCallback, useSyncExternalStore, type ReactNode } from "react";
import { RTL, STATIC } from "./strings";

/**
 * Tiny i18n runtime. Keys are the English strings themselves: `t("Overview")`.
 * Lookup order: built-in dictionary → server translations (cached in localStorage) → English.
 * Missing strings are collected and translated in one batched call to POST /api/translate.
 */
const LS_PREFIX = "cb_i18n_";
const MAX_LEN = 600;

let lang = "en";
let version = 0;
const listeners = new Set<() => void>();
const dynamic: Record<string, Record<string, string>> = {};
const pending = new Set<string>();
const failed = new Set<string>(); // strings the server could not translate — do not ask again this session
let timer: ReturnType<typeof setTimeout> | null = null;

function emit() {
  version++;
  listeners.forEach((l) => l());
}

function load(code: string): Record<string, string> {
  if (!dynamic[code]) {
    try {
      dynamic[code] = JSON.parse(localStorage.getItem(LS_PREFIX + code) ?? "{}");
    } catch {
      dynamic[code] = {};
    }
  }
  return dynamic[code];
}

function persist(code: string) {
  try {
    const entries = Object.entries(dynamic[code] ?? {});
    localStorage.setItem(LS_PREFIX + code, JSON.stringify(Object.fromEntries(entries.slice(-1500))));
  } catch {
    /* storage full or blocked — in-memory cache still works */
  }
}

export function getLang() {
  return lang;
}

export function setLang(code: string) {
  const next = code || "en";
  if (next === lang) return;
  lang = next;
  failed.clear();
  pending.clear();
  if (typeof document !== "undefined") {
    document.documentElement.lang = next;
    document.documentElement.dir = RTL.has(next) ? "rtl" : "ltr";
  }
  try {
    localStorage.setItem("cb_lang", next);
  } catch {
    /* ignore */
  }
  emit();
}

/** Language remembered from the last visit, used before the session loads (login page). */
export function initialLang(): string {
  try {
    return localStorage.getItem("cb_lang") || navigator.language.split("-")[0] || "en";
  } catch {
    return "en";
  }
}

function schedule() {
  if (timer) return;
  timer = setTimeout(async () => {
    timer = null;
    const code = lang;
    const batch = [...pending].slice(0, 80);
    batch.forEach((s) => pending.delete(s));
    if (!batch.length) return;
    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ texts: batch, lang: code }),
      });
      if (!res.ok) throw new Error(String(res.status));
      const data = (await res.json()) as { texts: string[]; translated: boolean };
      if (code !== lang) return;
      const store = load(code);
      let changed = false;
      batch.forEach((src, i) => {
        if (data.texts[i] && data.texts[i] !== src) {
          store[src] = data.texts[i];
          changed = true;
        } else failed.add(src);
      });
      if (changed) {
        persist(code);
        emit();
      }
    } catch {
      batch.forEach((s) => failed.add(s));
    }
    if (pending.size) schedule();
  }, 120);
}

export function translate(text: string): string {
  if (lang === "en" || !text) return text;
  const hit = STATIC[lang]?.[text] ?? load(lang)[text];
  if (hit) return hit;
  if (text.length <= MAX_LEN && !failed.has(text) && !pending.has(text)) {
    pending.add(text);
    schedule();
  }
  return text;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** `const t = useT()` — re-renders when the language or fetched translations change. */
export function useT() {
  useSyncExternalStore(subscribe, () => version);
  return useCallback((text: string) => translate(text), []);
}

export function useLang() {
  useSyncExternalStore(subscribe, () => version);
  return lang;
}

/** `<T>Overview</T>` for inline JSX text. */
export function T({ children }: { children: string }): ReactNode {
  const t = useT();
  return createElement(Fragment, null, t(children));
}

/** Whether the model/dictionary could not translate this language's dynamic text (shows an English-fallback notice). */
export function hasFailures() {
  return failed.size > 0 && lang !== "en";
}

const outputCache: { lang: string; size: number; set: Set<string> } = { lang: "", size: -1, set: new Set() };

/** True when `text` is already a translation produced for the active language (so it must not be translated again). */
export function isTranslatedOutput(text: string): boolean {
  if (lang === "en") return false;
  const dyn = load(lang);
  const size = Object.keys(dyn).length;
  if (outputCache.lang !== lang || outputCache.size !== size) {
    outputCache.lang = lang;
    outputCache.size = size;
    outputCache.set = new Set([...Object.values(STATIC[lang] ?? {}), ...Object.values(dyn)]);
  }
  return outputCache.set.has(text);
}
