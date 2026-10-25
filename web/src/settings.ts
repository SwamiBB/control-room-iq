/**
 * The operator's own console settings, remembered per browser.
 *
 * Four switches and no more. The defaults are the console as it was before there were settings. There is
 * deliberately no switch to hide template-built cards: an operator who cannot see a graphic cannot stop it.
 */

export type OperatorSettings = {
  /** Each card's evidence lines and the producer's reasoning. */
  reasoning: boolean;
  /** The "Preview for" row under each card. */
  preview: boolean;
  /** F, H and D fire, hold or drop the card at the top of the running order. */
  shortcuts: boolean;
  /** A chime when a new graphic reaches the running order. */
  alert: boolean;
};

export const DEFAULT_SETTINGS: OperatorSettings = { reasoning: true, preview: true, shortcuts: false, alert: false };

export const SETTINGS_KEY = "crq.settings";

type Store = Pick<Storage, "getItem" | "setItem">;

/** Whatever is stored, read safely: a missing, old or hand-edited value falls back field by field. */
export function loadSettings(store: Store | undefined): OperatorSettings {
  try {
    const raw = JSON.parse(store?.getItem(SETTINGS_KEY) ?? "{}");
    const out = { ...DEFAULT_SETTINGS };
    for (const k of Object.keys(DEFAULT_SETTINGS) as (keyof OperatorSettings)[]) {
      if (typeof raw?.[k] === "boolean") out[k] = raw[k];
    }
    return out;
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(store: Store | undefined, s: OperatorSettings): void {
  try {
    store?.setItem(SETTINGS_KEY, JSON.stringify(s));
  } catch {
    /* private window: the settings last for this page */
  }
}

export type ShortcutAction = "approve" | "hold" | "reject";

const KEYS: Record<string, ShortcutAction> = { f: "approve", h: "hold", d: "reject" };

/**
 * The action a key press asks for, or null. Typing in a field, a modifier held, or a held key repeating is
 * never a decision: firing a graphic must take one deliberate press.
 */
export function shortcutFor(e: {
  key: string; ctrlKey?: boolean; metaKey?: boolean; altKey?: boolean; repeat?: boolean;
  target?: { tagName?: string; isContentEditable?: boolean } | null;
}): ShortcutAction | null {
  if (e.ctrlKey || e.metaKey || e.altKey || e.repeat) return null;
  const tag = e.target?.tagName?.toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.target?.isContentEditable) return null;
  return KEYS[e.key.toLowerCase()] ?? null;
}

/**
 * Ids in `incoming` that are new waiting graphics, adding them to `seen`. A card re-sent on reconnect, or
 * one that changed status, is not new; a goal routine's items arrive together and count once each.
 */
export function newArrivals(seen: Set<string>, incoming: { proposal_id: string; status: string }[]): string[] {
  const fresh: string[] = [];
  for (const p of incoming) {
    if (seen.has(p.proposal_id)) continue;
    seen.add(p.proposal_id);
    if (p.status === "proposed") fresh.push(p.proposal_id);
  }
  return fresh;
}
