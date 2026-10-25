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

/** The part of a WebSocket the loop uses, so a test can hand it a fake one. */
export type SocketLike = {
  onopen: (() => void) | null;
  onmessage: ((e: { data: any }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  close(): void;
};

export type LiveHandlers = {
  onMessage: (msg: any) => void;
  /** Runs on every successful connect, the first and each reconnect, before any of that connection's messages. */
  onOpen?: () => void;
  onState: (state: LinkState) => void;
};

/** The connect-and-retry loop behind `useLiveSocket`. Returns the function that closes it for good. */
export function connectLive(
  url: string,
  h: LiveHandlers,
  makeSocket: (url: string) => SocketLike = (u) => new WebSocket(u) as unknown as SocketLike,
): () => void {
  let socket: SocketLike | null = null;
  let retry = FIRST_RETRY_MS;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let closed = false;
  let state: LinkState = "connecting";
  const set = (s: LinkState) => {
    state = s;
    h.onState(s);
  };

  const open = () => {
    if (closed) return;
    if (state === "live") set("connecting");
    let s: SocketLike;
    try {
      s = makeSocket(url);
    } catch {
      schedule();
      return;
    }
    socket = s;

    s.onopen = () => {
      retry = FIRST_RETRY_MS;
      set("live");
      try {
        h.onOpen?.();
      } catch (err) {
        console.error("Open handler failed", err);
      }
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
        h.onMessage(msg);
      } catch (err) {
        console.error("Message handler failed", err, msg);
      }
    };
    s.onerror = () => { /* onclose always follows; retry is handled there */ };
    s.onclose = () => {
      if (closed) return;
      set("down");
      schedule();
    };
  };

  const schedule = () => {
    if (closed) return;
    timer = setTimeout(open, retry);
    retry = Math.min(retry * 2, MAX_RETRY_MS);
  };

  open();
  return () => {
    closed = true;
    clearTimeout(timer);
    if (socket) {
      socket.onclose = null;
      socket.close();
    }
  };
}

/**
 * `onOpen` runs on every successful connect, the first and each reconnect, before any of that connection's
 * messages: the place to drop what the server will send again, or what it may no longer have.
 */
export function useLiveSocket(url: string, onMessage: (msg: any) => void, onOpen?: () => void): LinkState {
  const [state, setState] = useState<LinkState>("connecting");
  // Held in refs so a new handler identity never tears down a healthy socket.
  const handler = useRef(onMessage);
  handler.current = onMessage;
  const opened = useRef(onOpen);
  opened.current = onOpen;

  useEffect(
    () => connectLive(url, {
      onMessage: (msg) => handler.current(msg),
      onOpen: () => opened.current?.(),
      onState: setState,
    }),
    [url],
  );

  return state;
}
