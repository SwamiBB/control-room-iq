import { useEffect, useState } from "react";
import { fetchMetrics, type GalleryMetrics } from "../api";
import "./metrics.css";

/**
 * Gallery metrics: how fast the operator is deciding, how often the system is wrong, how much it
 * is asking of one person. Numbers, not charts — there is no series and no time axis here, and an
 * operator reads these at a glance. The one exception is the delivery mix, which is parts of a
 * whole and says more as a bar than as four counts.
 */

const POLL_MS = 5000;

const secs = (v: number | null | undefined) => (v == null ? "–" : `${v.toFixed(1)}s`);
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const num = (v: number | null | undefined, dp = 0) => (v == null ? "–" : v.toFixed(dp));

/** Quality ladder, worst last: a checked variant is the good case, English is the fallback. */
const MIX_ORDER = ["variant", "template", "base", "override"] as const;
const MIX_LABEL: Record<string, string> = {
  variant: "Checked variant",
  template: "Template",
  base: "English line",
  override: "Override",
};

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="tile">
      <b>{value}</b>
      <span>{label}</span>
      {note && <small>{note}</small>}
    </div>
  );
}

export default function MetricsPanel() {
  const [m, setM] = useState<GalleryMetrics | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let stale = false;
    const load = () =>
      fetchMetrics()
        .then((d) => { if (!stale) { setM(d); setError(false); } })
        .catch(() => { if (!stale) setError(true); });
    load();
    const t = window.setInterval(load, POLL_MS);
    return () => { stale = true; window.clearInterval(t); };
  }, []);

  if (error && !m) return <p className="empty">Metrics unavailable (<code>GET /metrics</code>).</p>;
  if (!m) return <p className="empty">Loading metrics…</p>;

  const mix = MIX_ORDER.map((k) => ({ key: k, n: m.errors.deliveries[k] ?? 0 }));
  const mixTotal = mix.reduce((a, b) => a + b.n, 0);
  const failures = Object.entries(m.errors.check_failures).sort((a, b) => b[1] - a[1]);

  return (
    <div className="metrics">
      <div className="metric-group">
        <h4>Turnaround</h4>
        <div className="tiles">
          <Tile label="Median" value={secs(m.turnaround.median_s)} />
          <Tile label="p90" value={secs(m.turnaround.p90_s)} />
          <Tile label="Slowest" value={secs(m.turnaround.max_s)} />
          <Tile label="Fired" value={num(m.turnaround.fired)} />
        </div>
      </div>

      <div className="metric-group">
        <h4>Operator workload</h4>
        <div className="tiles">
          <Tile label="Per 10 min" value={num(m.workload.decisions_per_10_min, 1)} note="decisions" />
          <Tile label="Graphics / click" value={num(m.workload.graphics_per_click, 1)} />
          <Tile label="Waiting" value={num(m.workload.pending)} />
          <Tile label="Play time" value={`${num(m.workload.play_minutes, 0)}′`} />
        </div>
      </div>

      <div className="metric-group">
        <h4>Where it went wrong</h4>
        <div className="tiles">
          <Tile label="Overridden" value={pct(m.errors.override_rate)} note={`${m.errors.overridden} of ${m.errors.decided}`} />
          <Tile label="Dropped" value={pct(m.errors.drop_rate)} note={`${m.errors.dropped} of ${m.errors.decided}`} />
          <Tile label="Held by the timer" value={num(m.workload.sla_holds)} />
          <Tile label="Expired" value={num(m.workload.expired)} />
        </div>
      </div>

      {mixTotal > 0 && (
        <div className="metric-group">
          <h4>What viewers actually got</h4>
          <div className="mix" role="img"
               aria-label={mix.map((s) => `${MIX_LABEL[s.key]} ${s.n}`).join(", ")}>
            {mix.filter((s) => s.n > 0).map((s) => (
              <span key={s.key} className={`seg ${s.key}`} style={{ flexGrow: s.n }} />
            ))}
          </div>
          <ul className="mix-key">
            {mix.filter((s) => s.n > 0).map((s) => (
              <li key={s.key}>
                <i className={`dot ${s.key}`} />
                {MIX_LABEL[s.key]} <b>{s.n}</b>
                <span className="share">{Math.round((s.n / mixTotal) * 100)}%</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {failures.length > 0 && (
        <div className="metric-group">
          <h4>Why a version was replaced</h4>
          <ul className="failures">
            {failures.map(([code, n]) => <li key={code}>{code} <b>{n}</b></li>)}
          </ul>
        </div>
      )}

      {m.errors.fallback_proposals > 0 && (
        <p className="metric-note">{m.errors.fallback_proposals} proposals were written by the template fallback, not a model.</p>
      )}
      {error && <p className="metric-note">Last refresh failed; showing the previous reading.</p>}
    </div>
  );
}
