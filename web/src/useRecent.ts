import { useEffect, useState } from "react";

/**
 * How long the latest shot's path and "Shot by …" label stay on a pitch. Left up until the next shot, an old
 * one read as if it were happening now; the shot's marker stays on the console's shot map either way.
 */
export const SHOT_ON_SCREEN_MS = 8000;

/**
 * True for `ms` after `key` first appears, then false until the key changes. A new key (the next shot) starts
 * its own time; the same key coming again (a reconnect re-sending it) does not bring it back.
 */
export function useRecent(key: string | null | undefined, ms: number): boolean {
  const [expired, setExpired] = useState<string | null>(null);
  useEffect(() => {
    if (!key) return;
    const t = window.setTimeout(() => setExpired(key), ms);
    return () => window.clearTimeout(t);
  }, [key, ms]);
  return Boolean(key) && expired !== key;
}
