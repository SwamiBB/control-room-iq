import BallPath from "./BallPath";
import { H, W, asPath, place, type PathPoint } from "./pitchGeometry";
import "./pitch.css";

export { place };

/**
 * Top-down pitch drawn from the event stream: no video, no 3D.
 *
 * Coordinates are 0-100 on both axes, attacking left to right for the team in possession
 * (see packages/schemas). So away-team shots are rotated 180 degrees here, which fixes the
 * home side attacking right for the whole match and lets an operator read one picture.
 *
 * Each shot is drawn from where it was struck to where it finished, both from the stats engine. The
 * latest moment's path comes as an ordered list of points, so a fuller move trail can replace the two
 * points later without changing the drawing. Nothing is drawn between points the data does not have.
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
  end_x?: number | null;
  end_y?: number | null;
};

/** The latest moment's own path, in the shooting team's frame (MomentMetrics.shot_path). */
export type PitchPath = { id: string; team?: string | null; points: PathPoint[]; label: string };

type PathMoment = {
  moment: { team?: string | null; player?: string | null; event_ids?: string[]; metrics?: { shot_path?: unknown } | null };
  intel?: { shot_path?: unknown } | null;
};

/**
 * The newest moment that carries its own shot path, newest first as the console keeps them. Keyed by the
 * shot's event id, so it takes the place of that shot's faint line rather than drawing over it.
 */
export function latestShotPath(moments: PathMoment[], nameOf: (id?: string | null) => string): PitchPath | null {
  for (const m of moments) {
    const points = asPath(m.intel?.shot_path ?? m.moment.metrics?.shot_path);
    if (!points) continue;
    const who = nameOf(m.moment.player);
    return {
      id: m.moment.event_ids?.[0] ?? points.join(";"),
      team: m.moment.team,
      points,
      label: who ? `Shot by ${who}` : "Shot",
    };
  }
  return null;
}

type Props = {
  shots: PitchShot[];
  homeTeamId?: string | null;
  /** Shot to ring as the live strike; defaults to the most recent one. */
  strikeEventId?: string | null;
  pressureTrend?: "rising" | "steady" | "falling";
  momentum?: "home_pushing" | "balanced" | "away_pushing";
  nameOf?: (id?: string | null) => string;
  latestPath?: PitchPath | null;
};

export const radius = (xg: number) => 1.1 + Math.max(0, Math.min(1, xg)) * 3.4;

const OUTCOME_CLASS: Record<string, string> = {
  goal: "goal",
  saved: "saved",
  blocked: "blocked",
  off_target: "off",
  post: "post",
};

export default function PitchView({
  shots, homeTeamId, strikeEventId, pressureTrend = "steady", momentum = "balanced", nameOf, latestPath,
}: Props) {
  const mirrored = (team?: string | null) => Boolean(homeTeamId) && team !== homeTeamId;
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

        <PitchLines />

        {/* where each earlier shot finished, faint; the latest moment's path on top, drawn in once */}
        <g className="paths">
          {placed.filter((p) => p.end_x != null && p.end_y != null && p.event_id !== latestPath?.id).map((p) => (
            <BallPath key={p.event_id} emphasis="past" mirror={mirrored(p.team)}
                      points={[[p.x as number, p.y as number], [p.end_x as number, p.end_y as number]]} />
          ))}
        </g>

        {/* shot markers: area by chance quality, colour by what happened */}
        <g className="shots">
          {placed.map((s) => {
            const mirror = mirrored(s.team);
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

        {latestPath && (
          <BallPath key={latestPath.id} points={latestPath.points} mirror={mirrored(latestPath.team)}
                    label={latestPath.label} animate />
        )}
      </svg>

      <figcaption>
        {placed.length === 0
          ? shots.length === 0
            ? "No shots yet."
            : `${shots.length} shots, none with a position to place.`
          : <>
              <span className="key goal">Goal</span>
              <span className="key saved">Saved</span>
              <span className="key blocked">Blocked</span>
              <span className="key off">Off target</span>
              <span className="note">Marker size is expected goals; lines run to where each shot finished. Home attacks right.</span>
            </>}
      </figcaption>
    </figure>
  );
}

/** The markings alone, in metres: for any pitch drawn from the event stream. */
export function PitchLines() {
  return (
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
  );
}
