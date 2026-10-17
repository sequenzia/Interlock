// The console is a static build. Unset, VITE_BACKEND_URL leaves every request on
// the page's own origin, where the Vite dev proxy (or the e2e mock backend) owns
// /ws, /health and /eval. The Vercel build sets it to the backend container's
// https origin, and the socket follows it as wss.
const base = (import.meta.env.VITE_BACKEND_URL ?? "").replace(/\/+$/, "");

export function httpUrl(path: string): string {
  return `${base}${path}`;
}

export function wsUrl(): string {
  if (base) return `${base.replace(/^http/, "ws")}/ws`;
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/ws`;
}
