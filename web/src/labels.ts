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
  waiting: { en: "Waiting for the match", es: "Esperando el partido", hi: "मैच का इंतज़ार" },
  stats: { en: "Stats", es: "Estadísticas", hi: "आँकड़े" },
  shot: { en: "Shot", es: "Remate", hi: "शॉट" },
  caption: { en: "Caption", es: "Subtítulo", hi: "कैप्शन" },
  // Badges on a graphic
  unverified: { en: "Unverified", es: "Sin verificar", hi: "असत्यापित" },
  in_english: { en: "in English", es: "en inglés", hi: "अंग्रेज़ी में" },
  // The strike cue's word, by cue kind
  "cue.chance": { en: "Shot", es: "Remate", hi: "शॉट" },
  "cue.goal": { en: "Goal", es: "Gol", hi: "गोल" },
  "cue.whistle": { en: "Whistle", es: "Silbato", hi: "सीटी" },
  "cue.crowd_rising": { en: "Crowd rising", es: "La grada se levanta", hi: "दर्शक उठ रहे हैं" },
  "cue.crowd_roar": { en: "Crowd roar", es: "Rugido de la grada", hi: "दर्शकों की गर्जना" },
  "cue.crowd_groan": { en: "Crowd groan", es: "Lamento de la grada", hi: "दर्शकों की आह" },
  "cue.card": { en: "Card", es: "Tarjeta", hi: "कार्ड" },
  "cue.play": { en: "Play", es: "Juego", hi: "खेल" },
};

/** The viewer page around the picture: its title, the pickers, the help and the status lines. */
export const VIEWER_UI: Record<string, T> = {
  title: { en: "Viewer", es: "Espectador", hi: "दर्शक" },
  who: { en: "Who is watching", es: "Quién mira", hi: "कौन देख रहा है" },
  access: { en: "Accessibility", es: "Accesibilidad", hi: "सुगम्यता" },
  language: { en: "Language", es: "Idioma", hi: "भाषा" },
  supporting: { en: "Supporting", es: "Tu equipo", hi: "समर्थन" },
  help: { en: "What these mean", es: "Qué significa cada opción", hi: "इनका मतलब" },
  note: {
    en: "Strike cues and detail cards go to deaf-access viewers. Switch Accessibility to see them.",
    es: "Las señales de remate y las fichas de detalle se muestran en el modo para personas sordas. Cambia Accesibilidad para verlas.",
    hi: "शॉट के संकेत और विवरण कार्ड बधिर दर्शकों वाले विकल्प में दिखते हैं। इन्हें देखने के लिए सुगम्यता बदलें।",
  },
  warming: { en: "Warming up: the next run is loading.", es: "Preparando: se está cargando la siguiente secuencia.", hi: "तैयारी हो रही है: अगला रीप्ले लोड हो रहा है।" },
  connecting: { en: "Connecting…", es: "Conectando…", hi: "कनेक्ट हो रहा है…" },
  lost: { en: "Lost the feed. Reconnecting automatically.", es: "Se perdió la señal. Reconectando automáticamente.", hi: "फ़ीड टूट गई। अपने-आप दोबारा जुड़ रहा है।" },
  bug: { en: "Score and match clock", es: "Marcador y reloj del partido", hi: "स्कोर और मैच की घड़ी" },
  your_side: { en: "The score from your side", es: "El marcador visto desde tu equipo", hi: "आपकी टीम के हिसाब से स्कोर" },
};

/** The pickers' choices. Language names stay in their own language, as language pickers do. */
export const PERSONA_NAMES: Record<"newcomer" | "fan" | "analyst", T> = {
  newcomer: { en: "New to football", es: "Nuevo en el fútbol", hi: "फ़ुटबॉल में नए" },
  fan: { en: "Fan", es: "Aficionado", hi: "प्रशंसक" },
  analyst: { en: "Analyst", es: "Analista", hi: "विश्लेषक" },
};
export const ACCESS_NAMES: Record<"none" | "deaf", T> = {
  none: { en: "Standard", es: "Estándar", hi: "सामान्य" },
  deaf: { en: "Deaf — cues and captions", es: "Personas sordas — señales y subtítulos", hi: "बधिर — संकेत और कैप्शन" },
};
export const SIDE_NAMES: Record<"home" | "away" | "neutral", T> = {
  home: { en: "Home", es: "Local", hi: "घरेलू टीम" },
  away: { en: "Away", es: "Visitante", hi: "मेहमान टीम" },
  neutral: { en: "Neutral", es: "Neutral", hi: "तटस्थ" },
};

/** What each choice changes, for the pickers' tooltips: the personalizer agent's rules, in a viewer's words. */
export const PERSONA_HELP_TEXT: Record<"newcomer" | "fan" | "analyst", T> = {
  newcomer: {
    en: "Plain words, no jargon. Says what happened rather than the statistic, with one fact at most.",
    es: "Palabras sencillas, sin tecnicismos. Cuenta lo que pasó en lugar de la estadística, con un dato como mucho.",
    hi: "आसान शब्द, कोई तकनीकी भाषा नहीं। आँकड़े की जगह बताता है कि क्या हुआ, ज़्यादा से ज़्यादा एक तथ्य के साथ।",
  },
  fan: {
    en: "Knows the game. Warm, factual lines with a key number or two, rounded: a speed, a pass length.",
    es: "Conoce el juego. Frases cercanas y precisas con uno o dos datos clave, redondeados: una velocidad, la longitud de un pase.",
    hi: "खेल को जानते हैं। गर्मजोशी भरी, तथ्यपूर्ण पंक्तियाँ, एक-दो मुख्य आँकड़ों के साथ, पूर्णांक में: कोई गति, पास की लंबाई।",
  },
  analyst: {
    en: "Precise and neutral. The supporting figure in full: speeds to one decimal, pass difficulty and accuracy.",
    es: "Preciso y neutral. El dato completo: velocidades con un decimal, dificultad y precisión de los pases.",
    hi: "सटीक और निष्पक्ष। पूरा आँकड़ा: गति एक दशमलव तक, पास की कठिनाई और सटीकता।",
  },
};
export const ACCESS_HELP_TEXT: Record<"none" | "deaf", T> = {
  none: { en: "The graphics as broadcast.", es: "Los gráficos tal como se emiten.", hi: "ग्राफ़िक्स, जैसे प्रसारण में आते हैं।" },
  deaf: {
    en: "A visual cue on every strike, and a caption card with who, where, the outcome and the score. Lines never rely on sound.",
    es: "Una señal visual en cada remate y una ficha con quién, desde dónde, el resultado y el marcador. Nada depende del sonido.",
    hi: "हर शॉट पर एक दृश्य संकेत, और एक कैप्शन कार्ड: किसने, कहाँ से, परिणाम और स्कोर। कोई भी पंक्ति आवाज़ पर निर्भर नहीं।",
  },
};

/**
 * The match-intelligence chips' fixed words. `{name}` and `{value}` are filled in by intel.ts; the numbers and
 * player names themselves are never translated.
 */
export const CHIP_WORDS: Record<string, T> = {
  ball: { en: "Ball", es: "Balón", hi: "गेंद" },
  pass: { en: "Pass", es: "Pase", hi: "पास" },
  pass_by: { en: "Pass by {name}", es: "Pase de {name}", hi: "{name} का पास" },
  difficulty: { en: "Difficulty", es: "Dificultad", hi: "कठिनाई" },
  passer_accuracy: { en: "Passer accuracy", es: "Precisión del pasador", hi: "पास देने वाले की सटीकता" },
  speed: { en: "Speed", es: "Velocidad", hi: "गति" },
  distance: { en: "Distance", es: "Distancia", hi: "दूरी" },
  sprints: { en: "sprints", es: "sprints", hi: "स्प्रिंट" },
  threshold: { en: "threshold", es: "umbral", hi: "सीमा" },
  fastest_run: { en: "One of the fastest runs", es: "Una de las carreras más rápidas", hi: "सबसे तेज़ दौड़ों में से एक" },
  thunderous: { en: "A thunderous strike", es: "Un remate potentísimo", hi: "ज़बरदस्त शॉट" },
  struck_firmly: { en: "Struck firmly", es: "Remate firme", hi: "दमदार शॉट" },
  // Pass difficulty, alone and as the newcomer's whole sentence
  "difficulty.routine": { en: "Routine", es: "Sencillo", hi: "आसान" },
  "difficulty.testing": { en: "Testing", es: "Exigente", hi: "चुनौतीपूर्ण" },
  "difficulty.hard": { en: "Hard", es: "Difícil", hi: "कठिन" },
  "difficulty.very_hard": { en: "Very hard", es: "Muy difícil", hi: "बहुत कठिन" },
  "to_complete.routine": { en: "Routine to complete", es: "Pase sencillo", hi: "आसान पास" },
  "to_complete.testing": { en: "Testing to complete", es: "Pase exigente", hi: "चुनौतीपूर्ण पास" },
  "to_complete.hard": { en: "Hard to complete", es: "Pase difícil", hi: "कठिन पास" },
  "to_complete.very_hard": { en: "Very hard to complete", es: "Pase muy difícil", hi: "बहुत कठिन पास" },
  // Threshold kinds
  "kind.top_speed": { en: "Top speed", es: "Velocidad máxima", hi: "शीर्ष गति" },
  "kind.sprint": { en: "Sprint", es: "Sprint", hi: "स्प्रिंट" },
  "kind.distance": { en: "Distance", es: "Distancia", hi: "दूरी" },
  "kind.pass_difficulty": { en: "Pass difficulty", es: "Dificultad del pase", hi: "पास की कठिनाई" },
  "kind.pass_distance": { en: "Long pass", es: "Pase largo", hi: "लंबा पास" },
  "kind.ball_speed": { en: "Ball speed", es: "Velocidad del balón", hi: "गेंद की गति" },
  "kind.shot_speed": { en: "Shot speed", es: "Velocidad del remate", hi: "शॉट की गति" },
};

/** A chip word in the viewer's language, with `{name}` filled in. An unknown key passes through as itself. */
export const chipWord = (key: string, lang: Lang, name = ""): string =>
  (CHIP_WORDS[key]?.[lang] ?? CHIP_WORDS[key]?.en ?? key).replace("{name}", name);

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

/** The supporter's view of the score, as perspective.py words it for the API's payload: "1–0 up". */
const STANDING: Record<"up" | "down" | "level", T> = {
  up: { en: "{us}–{them} up", es: "ganando {us}–{them}", hi: "{us}–{them} से आगे" },
  down: { en: "{us}–{them} down", es: "perdiendo {us}–{them}", hi: "{us}–{them} से पीछे" },
  level: { en: "level at {us}–{them}", es: "empatando {us}–{them}", hi: "{us}–{them} से बराबर" },
};

/** The score from one side ("home" or "away"), or null for a neutral viewer. */
export function supporterText(home: number, away: number, side: string, lang: Lang): string | null {
  if (side !== "home" && side !== "away") return null;
  const [us, them] = side === "home" ? [home, away] : [away, home];
  const standing = us > them ? "up" : us < them ? "down" : "level";
  return STANDING[standing][lang].replace("{us}", String(us)).replace("{them}", String(them));
}

const NBSP = " ", WORD_JOINER = "⁠";

/**
 * Where a line may break, for drawing it: a number keeps its unit ("88.1 km/h"), and a score is one piece that stays
 * with the word before it ("Marcador 1–0", "स्कोर 1–0"), so neither is left alone on a line. Only spaces become
 * non-breaking and an invisible joiner follows the score's dash: the words are the delivered line's, unchanged.
 */
export function keepTogether(line: string): string {
  return line
    .replace(/(\d) (km\/h|km|m|%)(?=$|[\s.,;:!?)·।])/g, `$1${NBSP}$2`)
    .replace(/(\S) (\d+[–-]\d+)(?!\d)/g, `$1${NBSP}$2`)
    .replace(/(\d)([–-])(?=\d)/g, `$1$2${WORD_JOINER}`);
}

/** True for an outcome code this table can name, so an unknown code never reaches a screen as itself. */
export const isOutcome = (outcome: unknown): outcome is string =>
  typeof outcome === "string" && Object.hasOwn(OUTCOMES, outcome);

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
