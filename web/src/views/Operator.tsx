import { useEffect, useRef, useState } from "react";
import { API, WS, clock, decide, type MomentMsg, type Proposal } from "../api";
import IntelChips from "../components/IntelChips";
import MatchIntel from "../components/MatchIntel";
import type { MomentMetrics } from "../intel";

export default function Operator() {
  const [proposals, setProposals] = useState<Record<string, Proposal>>({});
  const [moments, setMoments] = useState<MomentMsg[]>([]);
  const [state, setState] = useState<any>(null);
  const [meta, setMeta] = useState<any>(null);
  const [override, setOverride] = useState<Record<string, string>>({});
  const ws = useRef<WebSocket>();

  useEffect(() => {
    const s = new WebSocket(`${WS}/ws/operator`);
    s.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "proposal") setProposals((p) => ({ ...p, [m.proposal.proposal_id]: m.proposal }));
      if (m.type === "moment") setMoments((x) => [m, ...x].slice(0, 30));
      if (m.type === "state") setState(m.state);
      if (m.type === "match") setMeta(m.meta);
    };
    ws.current = s;
    return () => s.close();
  }, []);

  const act = async (id: string, a: "approve" | "hold" | "override") => {
    const p = await decide(id, a, a === "override" ? { override_line: override[id] } : {});
    setProposals((x) => ({ ...x, [id]: p }));
  };
  const start = () => fetch(`${API}/matches/replay`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ file: "data/match.jsonl", speed: 20 }) });

  const names: Record<string, string> = Object.fromEntries(
    [meta?.home, meta?.away].flatMap((t: any) => (t?.players ?? []).map((p: any) => [p.player_id, p.name])));
  const name = (id?: string | null) => (id ? names[id] ?? id : "");
  const team = (id?: string | null) => (id === meta?.home?.team_id ? meta.home.short_name : id === meta?.away?.team_id ? meta.away.short_name : id ?? "");

  const queue = Object.values(proposals).filter((p) => p.status === "proposed" || p.status === "held").sort((a, b) => b.priority - a.priority);
  const aired = Object.values(proposals).filter((p) => p.status === "aired").slice(-6).reverse();

  return (
    <div className="operator">
      <header>
        <h1>Operator console</h1>
        {meta ? <span>{meta.home.name} v {meta.away.name} · {meta.venue}</span> : <button onClick={start}>Start replay</button>}
        {state && <span className="score">{state.home.goals} – {state.away.goals} · {clock(state.t_ms, state.period)}</span>}
      </header>
      <section className="program">
        <h2>Program feed</h2>
        <div className="pitch">{aired[0] && <div className={`overlay ${aired[0].layer}`}>{aired[0].override_line ?? aired[0].line}</div>}</div>
        {state && (
          <div className="stats">
            <Stat label="Possession" h={`${state.home.possession_pct}%`} a={`${state.away.possession_pct}%`} />
            <Stat label="xG" h={state.home.xg.toFixed(2)} a={state.away.xg.toFixed(2)} />
            <Stat label="Shots" h={state.home.shots} a={state.away.shots} />
            <Stat label="PPDA" h={state.home.ppda ?? "–"} a={state.away.ppda ?? "–"} />
          </div>
        )}
        <h2>Match intelligence</h2>
        <MatchIntel state={state} name={name} team={team} />
      </section>
      <section className="queue">
        <h2>Next on screen ({queue.length})</h2>
        {queue.map((p) => (
          <article key={p.proposal_id} className={`proposal ${p.status}`}>
            <div className="meta"><b>{p.layer}</b> · priority {p.priority.toFixed(2)} · {clock(p.t_start_ms, 1)} → {clock(p.t_end_ms, 1)}
              {p.faithfulness != null && <span className="eval"> · faithfulness {p.faithfulness.toFixed(2)}</span>}</div>
            <p className="line">{p.line}</p>
            <IntelChips metrics={p.payload?.intel as MomentMetrics | undefined} name={name} />
            <p className="reasoning">{p.reasoning}</p>
            <input placeholder="Override line…" value={override[p.proposal_id] ?? ""} onChange={(e) => setOverride({ ...override, [p.proposal_id]: e.target.value })} />
            <div className="actions">
              <button className="approve" onClick={() => act(p.proposal_id, "approve")}>Approve</button>
              <button onClick={() => act(p.proposal_id, "hold")} disabled={p.status === "held"}>Hold</button>
              <button onClick={() => act(p.proposal_id, "override")} disabled={!override[p.proposal_id]}>Override</button>
            </div>
          </article>
        ))}
      </section>
      <section className="moments">
        <h2>Moments and reasoning</h2>
        {moments.map((m) => (
          <article key={m.moment.moment_id}>
            <div className="meta">{clock(m.moment.t_ms, m.moment.period)} · {m.moment.kind} · {m.moment.importance.toFixed(2)}</div>
            <b>{m.explanation.headline}</b>
            <p>{m.explanation.why_it_matters}</p>
            <IntelChips metrics={m.intel ?? m.moment.metrics} name={name} />
            <small>pattern: {m.explanation.pattern} · cites {m.explanation.cites.join(", ")}{m.failures.length > 0 && ` · fallback used (${m.failures.length})`}</small>
          </article>
        ))}
      </section>
    </div>
  );
}

const Stat = ({ label, h, a }: { label: string; h: any; a: any }) => (<div className="stat"><span>{h}</span><label>{label}</label><span>{a}</span></div>);
