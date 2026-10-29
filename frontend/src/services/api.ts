/**
 * REST client for the FastAPI backend. Same-origin `/api/*` (proxied by Vite in development), so the
 * httpOnly session cookie set at login authenticates every call. Errors carry the backend's `{ error }` message.
 */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T = unknown>(url: string, init?: { method?: string; body?: unknown }): Promise<T> {
  const res = await fetch(url, {
    method: init?.method ?? (init?.body ? "POST" : "GET"),
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    body: init?.body ? JSON.stringify(init.body) : undefined,
    credentials: "same-origin",
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && typeof window !== "undefined" && !url.startsWith("/api/auth/login")) {
    // Clear the stale cookie first, otherwise the login route bounces straight back to the dashboard
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => undefined);
    if (!window.location.pathname.startsWith("/login")) window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
  if (!res.ok) throw new ApiError(res.status, (data as { error?: string })?.error ?? `Request failed (${res.status})`);
  return data as T;
}

/** URL of the Jinja2 → PDF rendering of a document. */
export const documentPdfUrl = (id: string) => `/api/documents/${id}/pdf`;

/** Runs an async action while keeping a minimum duration so agent animations can play out. */
export async function withMinDuration<T>(p: Promise<T>, ms = 1800): Promise<T> {
  const [r] = await Promise.all([p, new Promise((res) => setTimeout(res, ms))]);
  return r;
}
