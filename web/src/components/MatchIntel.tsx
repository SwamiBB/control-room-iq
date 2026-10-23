import {
  DIFFICULTY_TEXT, accuracy, fastestShot, km, kmh, leaders, metres, passLabel, pct, thresholdKind, thresholdLabel,
  type IntelState, type NameOf,
} from "../intel";

type Props = { state: IntelState | null; name: NameOf; team: (teamId?: string | null) => string };

const minute = (playMs: number) => `${Math.floor(playMs / 60000) + 1}'`;

/**
 * Operator panel for hackathon expectation (ii): who crossed a speed or distance threshold, the latest pass rated
 * for distance, accuracy and difficulty, and ball and shot speed. Every number is the stats engine's.
 */
export default function MatchIntel({ state, name, team }: Props) {
  if (!state) return <p className="intel-empty">Waiting for the stats engine…</p>;
  const crossings = [...(state.thresholds ?? [])].reverse().slice(0, 6);
  const fast = leaders(state, "top_speed_kmh");
  const far = leaders(state, "distance_m");
  const lp = state.last_pass;
  const shot = fastestShot(state);
  const flagged = new Set((state.thresholds ?? []).filter((t) => t.kind === "top_speed" || t.kind === "sprint").map((t) => t.player));

  return (
    <div className="intel">
      <div className="intel-block">
        <h3>Threshold indicators</h3>
        {crossings.length === 0 ? <p className="intel-empty">None crossed yet</p> : (
          <ul className="crossings">
            {crossings.map((t, i) => (
              <li key={`${t.event_id ?? i}-${t.kind}`}>
                <span className={`badge ${t.kind}`}>{thresholdKind(t.kind)}</span>
                <b>{t.player ? name(t.player) : "Ball"}</b>
                <span>{thresholdLabel(t)}</span>
                {t.play_ms != null && <small>{minute(t.play_ms)}</small>}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="intel-grid">
        <div className="intel-block">
          <h3>Top speed</h3>
          <table className="leaders"><tbody>
            {fast.map((l) => (
              <tr key={l.player_id} className={flagged.has(l.player_id) ? "over" : ""}>
                <td>{name(l.player_id)}{flagged.has(l.player_id) && <span className="flag" title="Crossed the speed threshold">▲</span>}</td>
                <td className="team">{team(l.team)}</td><td className="val">{kmh(l.value)}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
        <div className="intel-block">
          <h3>Distance covered</h3>
          <table className="leaders"><tbody>
            {far.map((l) => (
              <tr key={l.player_id}>
                <td>{name(l.player_id)}</td><td className="team">{team(l.team)}</td>
                <td className="val">{km(l.value / 1000)}{state.players[l.player_id]?.sprints ? ` · ${state.players[l.player_id].sprints} spr` : ""}</td>
              </tr>
            ))}
          </tbody></table>
        </div>
      </div>

      <div className="intel-block">
        <h3>Pass quality</h3>
        {lp ? (
          <div className="pass-card">
            <div className="pass-who"><b>{name(lp.player)}</b>{lp.receiver && <> → <b>{name(lp.receiver)}</b></>}
              {lp.key_pass && <span className="badge key">Key pass</span>}{lp.completed === false && <span className="badge miss">Not completed</span>}</div>
            <dl>
              <div><dt>Distance</dt><dd>{metres(lp.distance_m)}</dd></div>
              <div><dt>Passer accuracy</dt><dd>{pct(lp.accuracy_pct)}</dd></div>
              <div><dt>Ball speed</dt><dd>{kmh(lp.ball_speed_kmh)}</dd></div>
            </dl>
            <div className={`difficulty ${passLabel(lp)}`} aria-label={`Difficulty ${lp.difficulty.toFixed(2)}`}>
              <span className="bar"><i style={{ width: `${Math.round(lp.difficulty * 100)}%` }} /></span>
              <span>Difficulty {lp.difficulty.toFixed(2)} · {DIFFICULTY_TEXT[passLabel(lp)]}</span>
            </div>
          </div>
        ) : <p className="intel-empty">No rated pass yet</p>}
        <div className="team-acc">
          <span>Pass accuracy</span>
          <b>{team(state.home.team)} {pct(accuracy(state.home))}</b>
          <b>{team(state.away.team)} {pct(accuracy(state.away))}</b>
        </div>
      </div>

      <div className="intel-block">
        <h3>Ball and shot speed</h3>
        <div className="team-acc speeds">
          <span>Fastest shot</span>
          <b>{shot ? `${name(shot.player)} ${kmh(shot.speed_kmh)}` : "–"}</b>
          <span>Last pass ball speed</span>
          <b>{kmh(lp?.ball_speed_kmh)}</b>
        </div>
      </div>
    </div>
  );
}
