import { useEffect, useRef, useState } from "react";

/**
 * One WebSocket with an honest status and automatic reconnection.
 *
 * The demo runs offline from a replay, so the usual failure is not a network blip: it is the API
 * not running, or the replay never started. Those look identical to an empty screen unless the
 * link state is shown, so this reports "connecting" / "live" / "down" and keeps retrying with a
 * backoff rather than dying silently on the first close.
 */

export type LinkState = "connecting" | "live" | "down";

const FIRST_RETRY_MS = 1000;
const MAX_RETRY_MS = 10000;

export function useLiveSocket(url: string, onMessage: (msg: any) => void): LinkState {
  const [state, setState] = useState<LinkState>("connecting");
  // Held in a ref so a new handler identity never tears down a healthy socket.
  const handler = useRef(onMessage);
  handler.current = onMessage;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry = FIRST_RETRY_MS;
    let timer: number | undefined;
    let closed = false;

    const open = () => {
      if (closed) return;
      setState((s) => (s === "live" ? "connecting" : s));
      let s: WebSocket;
      try {
        s = new WebSocket(url);
      } catch {
        schedule();
        return;
      }
      socket = s;

      s.onopen = () => {
        retry = FIRST_RETRY_MS;
        setState("live");
      };
      s.onmessage = (e) => {
        let msg: unknown;
        try {
          msg = JSON.parse(e.data);
        } catch {
          // A malformed frame is worth knowing about but must never take the screen down.
          console.warn("Ignored a frame that was not JSON", e.data);
          return;
        }
        try {
          handler.current(msg);
        } catch (err) {
          console.error("Message handler failed", err, msg);
        }
      };
      s.onerror = () => { /* onclose always follows; retry is handled there */ };
      s.onclose = () => {
        if (closed) return;
        setState("down");
        schedule();
      };
    };

    const schedule = () => {
      if (closed) return;
      timer = window.setTimeout(open, retry);
      retry = Math.min(retry * 2, MAX_RETRY_MS);
    };

    open();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      if (socket) {
        socket.onclose = null;
        socket.close();
      }
    };
  }, [url]);

  return state;
}
