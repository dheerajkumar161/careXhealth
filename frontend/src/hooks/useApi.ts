import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/services/api";

/** Minimal data hook with optional polling (the UI keeps polling — no WebSockets). */
export function useApi<T>(url: string | null, opts: { poll?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const urlRef = useRef(url);
  urlRef.current = url;

  const load = useCallback(async () => {
    if (!urlRef.current) return;
    try {
      const d = await api<T>(urlRef.current);
      setData(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    load();
    if (!opts.poll) return;
    const t = setInterval(load, opts.poll);
    return () => clearInterval(t);
  }, [url, load, opts.poll]);

  return { data, error, loading, reload: load, setData };
}
