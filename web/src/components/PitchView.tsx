import "./pitch.css";

/**
 * Top-down pitch drawn from the event stream: no video, no 3D.
 *
 * Coordinates are 0-100 on both axes, attacking left to right for the team in possession
 * (see packages/schemas). So away-team shots are rotated 180 degrees here, which fixes the
 * home side attacking right for the whole match and lets an operator read one picture.
 *
 * Shot coordinates are not on ShotRecord yet. Until they are, the markings draw and the
 * component says so rather than inventing positions.
 */

export type PitchShot = {
  event_id: string;
  team: string;
  player: string;
  xg: number;
  outcome: string;
  play_ms: number;
  zone?: string;
  x?: number | null;
  y?: number | null;
};

type Props = {
  shots: PitchShot[];
  homeTeamId?: string | null;
  /** Shot to ring as the live strike; defaults to the most recent one. */
  strikeEventId?: string | null;
  pressureTrend?: "rising" | "steady" | "falling";
  momentum?: "home_pushing" | "balanced" | "away_pushing";
  nameOf?: (id?: string | null) => string;
};

const W = 105;
const H = 68;

/** 0-100 in possession-relative space to pitch metres, rotated for the away side. */
export function place(x: number, y: number, mirror: boolean) {
  const px = mirror ? 100 - x : x;
  const py = mirror ? 100 - y : y;
  return { cx: (px / 100) * W, cy: (py / 100) * H };
}

export const radius = (xg: number) => 1.1 + Math.max(0, Math.min(1, xg)) * 3.4;

const OUTCOME_CLASS: Record<string, string> = {
  goal: "goal",
  saved: "saved",
  blocked: "blocked",
  off_target: "off",
  post: "post",
};

export default function PitchView({
  shots, homeTeamId, strikeEventId, pressureTrend = "steady", momentum = "balanced", nameOf,
}: Props) {
  const placed = shots.filter((s) => s.x != null && s.y != null);
  const latest = [...placed].sort((a, b) => b.play_ms - a.play_ms)[0];
  const strike = strikeEventId ?? latest?.event_id ?? null;

  // A light tint on the third the pressure is coming from, only while it is rising.
  const tint =
    pressureTrend === "rising" && momentum === "home_pushing" ? "home"
      : pressureTrend === "rising" && momentum === "away_pushing" ? "away"
        : null;

  return (
    <figure className="pitch-view">
      <svg viewBox={`-2 -2 ${W + 4} ${H + 4}`} role="img"
           aria-label={`Top-down pitch with ${placed.length} shot markers, sized by expected goals`}>
        {tint === "home" && <rect className="tint" x={W * 0.667} y={0} width={W * 0.333} height={H} />}
        {tint === "away" && <rect className="tint" x={0} y={0} width={W * 0.333} height={H} />}

        {/* markings */}
        <g className="lines" fill="none">
          <rect x={0} y={0} width={W} height={H} />
          <line x1={W / 2} y1={0} x2={W / 2} y2={H} />
          <circle cx={W / 2} cy={H / 2} r={9.15} />
          <circle className="spot" cx={W / 2} cy={H / 2} r={0.5} />

          {/* penalty and six-yard boxes, both ends */}
          <rect x={0} y={H / 2 - 20.16} width={16.5} height={40.32} />
          <rect x={W - 16.5} y={H / 2 - 20.16} width={16.5} height={40.32} />
          <rect x={0} y={H / 2 - 9.16} width={5.5} height={18.32} />
          <rect x={W - 5.5} y={H / 2 - 9.16} width={5.5} height={18.32} />
          <circle className="spot" cx={11} cy={H / 2} r={0.5} />
          <circle className="spot" cx={W - 11} cy={H / 2} r={0.5} />
          <path d="M 16.5 26.69 A 9.15 9.15 0 0 1 16.5 41.31" />
          <path d={`M ${W - 16.5} 26.69 A 9.15 9.15 0 0 0 ${W - 16.5} 41.31`} />

          {/* goals */}
          <rect className="goal" x={-1.5} y={H / 2 - 3.66} width={1.5} height={7.32} />
          <rect className="goal" x={W} y={H / 2 - 3.66} width={1.5} height={7.32} />
        </g>

        {/* shot markers: area by chance quality, colour by what happened */}
        <g className="shots">
          {placed.map((s) => {
            const mirror = Boolean(homeTeamId) && s.team !== homeTeamId;
            const { cx, cy } = place(s.x as number, s.y as number, mirror);
            const isStrike = s.event_id === strike;
            return (
              <g key={s.event_id} className={`shot ${OUTCOME_CLASS[s.outcome] ?? "off"} ${isStrike ? "strike" : ""}`}>
                {isStrike && <circle className="ring" cx={cx} cy={cy} r={radius(s.xg) + 3} />}
                <circle cx={cx} cy={cy} r={radius(s.xg)}>
                  <title>
                    {`${nameOf ? nameOf(s.player) : s.player} · ${s.xg.toFixed(2)} xG · ${s.outcome}${s.zone ? ` · ${s.zone}` : ""}`}
                  </title>
                </circle>
              </g>
            );
          })}
        </g>
      </svg>

      <figcaption>
        {placed.length === 0
          ? shots.length === 0
            ? "No shots yet."
            : `${shots.length} shots, no coordinates yet — ShotRecord has no x/y, so nothing can be placed.`
          : <>
              <span className="key goal">Goal</span>
              <span className="key saved">Saved</span>
              <span className="key blocked">Blocked</span>
              <span className="key off">Off target</span>
              <span className="note">Marker size is expected goals. Home attacks right.</span>
            </>}
      </figcaption>
    </figure>
  );
}
