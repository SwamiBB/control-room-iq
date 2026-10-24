/**
 * Fixed words the viewer renders in the viewer's language.
 *
 * Nothing here is AI text. The caption itself is `packet.line`, already delivered in the right
 * language by the API. These are only the labels around it: zones, outcomes, headings and the
 * chance sentence, per docs/HANDOFF-2026-10-24-fan-card.md.
 *
 * NOT YET NATIVE-REVIEWED. The Spanish and Hindi strings below need a native speaker before the
 * video (open item in PROJECT-SUMMARY §12). Player and club names are never translated.
 */

export type Lang = "en" | "es" | "hi";

type T = Record<Lang, string>;

/** Zone is written by the stats engine as "<area>, <side>". */
const AREAS: Record<string, T> = {
  "six-yard box": { en: "six-yard box", es: "área pequeña", hi: "छह गज बॉक्स" },
  "inside the box": { en: "inside the box", es: "dentro del área", hi: "बॉक्स के अंदर" },
  "edge of the box": { en: "edge of the box", es: "borde del área", hi: "बॉक्स के किनारे" },
  "final third": { en: "final third", es: "último tercio", hi: "अंतिम तिहाई" },
  "middle third": { en: "middle third", es: "tercio medio", hi: "मध्य तिहाई" },
  "own third": { en: "own third", es: "tercio propio", hi: "अपना तिहाई" },
};

const SIDES: Record<string, T> = {
  left: { en: "left", es: "izquierda", hi: "बाएँ" },
  right: { en: "right", es: "derecha", hi: "दाएँ" },
  centre: { en: "centre", es: "centro", hi: "केंद्र" },
  center: { en: "centre", es: "centro", hi: "केंद्र" },
};

const OUTCOMES: Record<string, T> = {
  goal: { en: "Goal", es: "Gol", hi: "गोल" },
  saved: { en: "Saved", es: "Atajado", hi: "बचाया गया" },
  off_target: { en: "Off target", es: "Fuera", hi: "निशाने से बाहर" },
  blocked: { en: "Blocked", es: "Bloqueado", hi: "ब्लॉक किया गया" },
  // fan_card.py filters outcomes to the four above, so this one cannot reach the card today.
  // Kept so a schema change does not leak a raw code onto a Spanish or Hindi screen.
  post: { en: "Off the post", es: "Al poste", hi: "पोस्ट पर" },
};

export const HEADINGS: Record<string, T> = {
  shooter: { en: "Shot by", es: "Remate de", hi: "शॉट" },
  zone: { en: "From", es: "Desde", hi: "कहाँ से" },
  outcome: { en: "Outcome", es: "Resultado", hi: "परिणाम" },
  chance: { en: "Chance", es: "Ocasión", hi: "मौका" },
  score: { en: "Score", es: "Marcador", hi: "स्कोर" },
  live: { en: "Live", es: "En vivo", hi: "लाइव" },
};

export const heading = (key: keyof typeof HEADINGS | string, lang: Lang): string =>
  HEADINGS[key]?.[lang] ?? key;

/** "edge of the box, left" → "borde del área, izquierda". Unknown parts pass through unchanged. */
export function zoneText(zone: string | null | undefined, lang: Lang): string | null {
  if (!zone) return null;
  if (lang === "en") return zone;
  return zone
    .split(",")
    .map((part) => {
      const k = part.trim().toLowerCase();
      return AREAS[k]?.[lang] ?? SIDES[k]?.[lang] ?? part.trim();
    })
    .join(", ");
}

export const outcomeText = (outcome: string | null | undefined, lang: Lang): string | null =>
  outcome ? OUTCOMES[outcome]?.[lang] ?? outcome : null;

/**
 * The chance sentence. English uses the stats engine's own wording; Spanish and Hindi are built
 * from xG with the same rule, so the two never disagree:
 *   xG >= 0.5 → "about round(xG x 10) in 10";  otherwise → "about 1 in round(1/xG)", minimum 2.
 */
export function chanceText(
  xg: number | null | undefined,
  chanceQuality: string | null | undefined,
  lang: Lang,
): string | null {
  if (lang === "en") return chanceQuality ?? null;
  if (xg == null || xg <= 0) return null;
  const many = xg >= 0.5;
  const n = many ? Math.round(xg * 10) : Math.max(2, Math.round(1 / xg));
  if (lang === "es") {
    return many
      ? `alrededor de ${n} de cada 10 ocasiones así acaban en gol`
      : `alrededor de 1 de cada ${n} ocasiones así acaban en gol`;
  }
  return many
    ? `ऐसे लगभग 10 में से ${n} मौके गोल बनते हैं`
    : `ऐसे लगभग ${n} में से 1 मौका गोल बनता है`;
}
