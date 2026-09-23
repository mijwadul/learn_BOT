/**
 * Dynamic API and WebSocket configuration.
 * - Allows overriding via NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL.
 * - Otherwise dynamically detects window.location.hostname so it works seamlessly on
 *   PC (localhost) or Mobile via Tailscale / LAN IP without manual code changes.
 */

export const getApiBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    return `http://${window.location.hostname}:8000`;
  }
  return "http://localhost:8000";
};

export const getWsBaseUrl = (): string => {
  if (process.env.NEXT_PUBLIC_WS_URL) {
    return process.env.NEXT_PUBLIC_WS_URL.replace(/\/$/, "");
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.hostname}:8000`;
  }
  return "ws://localhost:8000";
};
