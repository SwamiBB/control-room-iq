import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import {
  WS, clock, playClock, layerName, modelLabel, isCodeBuilt, isTemplateFallback, decide, decidePackage, startReplay, decisionLabel, decisionHelp, DECISION_HELP, errorMessage,
  COMPRESSED_SPEEDS, REAL_TIME, speedLabel, type ReplayScope, type ReplaySpeed,
  fetchDecisions, decisionsCsvUrl, fetchDeliveries, fetchReplayStatus, canStartReplay,
  type DecisionEntry, type DeliveryAudit, type MomentMsg, type PlayClock, type Proposal, type SlaWarning,
} from "../api";
import ErrorBoundary from "../components/ErrorBoundary";
import IntelChips from "../components/IntelChips";
import MatchIntel from "../components/MatchIntel";
import PitchView, { latestShotPath, type PitchShot } from "../components/PitchView";
import PreviewFor from "../components/PreviewFor";
import SettingsMenu from "../components/SettingsMenu";
import MetricsPanel from "../components/MetricsPanel";
import { chime, primeChime } from "../chime";
import { Resync } from "../resync";
import { stableOrder } from "../runningOrder";
import { agentsWriting, runPhase, RUN_PHASE_TEXT } from "../runStatus";
import { loadSettings, newArrivals, saveSettings, shortcutFor, type OperatorSettings } from "../settings";
import { useLiveSocket } from "../useLiveSocket";
import { SHOT_ON_SCREEN_MS, useRecent } from "../useRecent";
import type { MomentMetrics } from "../intel";
import "./operator.css";

const OPEN: Proposal["status"][] = ["proposed", "held"];
const OVERRIDE_MAX = 280; // the API's limit on override_line, for firing and for the preview alike
/** What the banner says was being tried, for one graphic or a whole goal routine: "fire the goal routine". */
const VERBS = { approve: "fire", hold: "hold", reject: "drop", override: "fire the override" } as const;
const actWords = (a: keyof typeof VERBS, noun = "the graphic") => (a === "override" ? VERBS.override : `${VERBS[a]} ${noun}`);
const WINDOW_MS = 90_000; // how much play time the running-order timeline shows

type Group = { packageId: string | null; items: Proposal[] };

const groupKey = (g: Group) => g.packageId ?? g.items[0].proposal_id;
/** Most urgent first: a group is as urgent as its most urgent item. */
const weightOf = (g: Group) => Math.min(...g.items.map((i) => i.priority ?? 9));

/** localStorage, or nothing where reading it throws (a private window, blocked site data). */
const browserStore = () => {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
};

/** True on /operator-demo. Enables the architecture-overlay chrome judges see; the plain /operator stays clean. */
const DemoContext = createContext(false);

export default function Operator({ demo = false }: { demo?: boolean } = {}) {
  const [proposals, setProposals] = useState<Record<string, Proposal>>({});
  const [moments, setMoments] = useState<MomentMsg[]>([]);
  const [state, setState] = useState<any>(null);
  const [clk, setClk] = useState<PlayClock | null>(null);
  const [meta, setMeta] = useState<any>(null);
  const [override, setOverride] = useState<Record<string, string>>({});
  const [deliveries, setDeliveries] = useState<Record<string, DeliveryAudit[]>>({});
  const [warnings, setWarnings] = useState<Record<string, SlaWarning>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<DecisionEntry[]>([]);
  const [speed, setSpeed] = useState<number | null>(null);
  const [ended, setEnded] = useState<{ error?: string | null } | null>(null);
  // From GET /healthz on connect, then from replay messages. null until known.
  const [running, setRunning] = useState<boolean | null>(null);
  const [scope, setScope] = useState<ReplayScope>("window");
  const [pace, setPace] = useState<ReplaySpeed>(20);
  // The run this console started: from the click until its first state, and the speed it asked for.
  const [starting, setStarting] = useState(false);
  const [runPace, setRunPace] = useState<number | null>(null);
  const lastStateAt = useRef<number | null>(null);
  const writingSince = useRef<number | null>(null);
  const matchAt = useRef<number | null>(null);
  const [logError, setLogError] = useState<string | null>(null);
  const [settings, setSettings] = useState<OperatorSettings>(() => loadSettings(browserStore()));
  const changeSettings = (next: OperatorSettings) => {
    if (next.alert && !settings.alert) primeChime(); // this click is what lets the page make a sound
    setSettings(next);
    saveSettings(browserStore(), next);
  };
  // Proposals already on the desk, so a re-send on reconnect or a status change is not a new arrival.
  const seen = useRef(new Set<string>());

  // Column split, as a percentage given to the decisions column. Remembered per console.
  const [split, setSplit] = useState<number>(() => {
    try {
      const v = Number(localStorage.getItem("crq.split"));
      return Number.isFinite(v) && v >= 30 && v <= 75 ? v : 52;
    } catch {
      return 52;
    }
  });
  const bodyRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  // Picked viewer groups are one set shared by every card, remembered per console.
  const [views, setViews] = useState<string[]>(() => {
    try {
      const v = JSON.parse(localStorage.getItem("crq.views") ?? "[]");
      return Array.isArray(v) ? v.slice(0, 12) : [];
    } catch {
      return [];
    }
  });
  const changeViews = useCallback((next: string[]) => {
    setViews(next);
    try { localStorage.setItem("crq.views", JSON.stringify(next)); } catch { /* private window */ }
  }, []);

  const saveSplit = useCallback((pct: number) => {
    const next = Math.min(75, Math.max(30, pct));
    setSplit(next);
    try { localStorage.setItem("crq.split", String(Math.round(next))); } catch { /* private window */ }
  }, []);

  const startDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    e.currentTarget.setPointerCapture(e.pointerId);
  }, []);
  const onDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!dragging.current || !bodyRef.current) return;
    const r = bodyRef.current.getBoundingClientRect();
    saveSplit(((e.clientX - r.left) / r.width) * 100);
  }, [saveSplit]);
  const endDrag = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    dragging.current = false;
    try { e.currentTarget.releasePointerCapture(e.pointerId); } catch { /* already released */ }
  }, []);

  // The log is the API's, not ours: holds by the timer and expiries never pass through this console.
  const refreshDecisions = useCallback(() => {
    fetchDecisions()
      .then((d) => { setDecisions(d); setLogError(null); })
      .catch((err) => setLogError(errorMessage(err, "load the decision log")));
  }, []);

  useEffect(() => {
    refreshDecisions();
    const t = window.setInterval(refreshDecisions, 5000);
    return () => window.clearInterval(t);
  }, [refreshDecisions]);

  // Everything that belongs to one match. The API re-sends only the match and its proposals on connect.
  const clearDesk = useCallback(() => {
    setMeta(null);
    setProposals({});
    setMoments([]);
    setDeliveries({});
    setWarnings({});
    setDecisions([]);
    setState(null);
    setClk(null);
    setEnded(null);
  }, []);

  const [resync] = useState(() => new Resync({ proposals: () => setProposals({}), desk: clearDesk }));
  useEffect(() => () => resync.dispose(), [resync]);

  // What the socket does not re-send: the chips each fired graphic got, and whether a replay is running.
  const loadDeliveries = useCallback(() => {
    fetchDeliveries()
      // Anything the socket delivered meanwhile is newer, so it wins.
      .then((fetched) => setDeliveries((d) => ({ ...fetched, ...d })))
      .catch(() => undefined); // chips are a nicety; the banner is for actions
  }, []);

  const link = useLiveSocket(`${WS}/ws/operator`, (m: any) => {
    {
      if (m.type === "proposal") {
        setProposals((p) => ({ ...p, [m.proposal.proposal_id]: m.proposal }));
        if (newArrivals(seen.current, [m.proposal]).length > 0 && settings.alert) chime();
      }
      if (m.type === "moment") setMoments((x) => [m, ...x].slice(0, 30));
      if (m.type === "state") {
        setState(m.state);
        if (m.clock) setClk(m.clock);
        lastStateAt.current = Date.now();
        setStarting(false);
      }
      if (m.type === "match") {
        // A fresh match clears the desk: last run's cards, log and deliveries belong to that match. The desk's
        // own match re-sent on connect keeps it, and the chips the match already has are fetched back.
        resync.match(m.meta?.match_id, meta?.match_id);
        matchAt.current = Date.now();
        setMeta(m.meta);
        loadDeliveries();
      }
      if (m.type === "deliveries") setDeliveries((d) => ({ ...d, [m.proposal_id]: m.deliveries }));
      if (m.type === "sla_warning") setWarnings((w) => ({ ...w, [m.proposal_id]: m }));
      if (m.type === "replay") {
        setSpeed(typeof m.speed === "number" ? m.speed : null);
        setRunning(!m.finished);
        if (m.finished) {
          setEnded({ error: m.error ?? null });
          setStarting(false);
        }
      }
    }
  }, () => {
    // On every connect: the proposals come again. A blip keeps the rest; a restarted API sends no match, or
    // another one, and then the stale desk goes rather than linger with cards that would only answer 404.
    resync.opened();
    fetchReplayStatus()
      .then(({ running: r, speed: s }) => { setRunning(r); setSpeed(s); })
      .catch(() => setRunning(null));
  });

  // Drives the countdowns; the server stays the source of truth for the hold itself.
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 250);
    return () => window.clearInterval(t);
  }, []);

  /** `action` is what the banner says was being tried if it fails: "fire the graphic". */
  const run = useCallback(async (key: string, action: string, fn: () => Promise<unknown>) => {
    setBusy((b) => ({ ...b, [key]: true }));
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(errorMessage(err, action));
    } finally {
      setBusy((b) => ({ ...b, [key]: false }));
    }
  }, []);

  const act = (id: string, a: "approve" | "hold" | "override" | "reject") =>
    run(id, actWords(a), async () => {
      const p = await decide(id, a, a === "override" ? { override_line: override[id] } : {});
      setProposals((x) => ({ ...x, [p.proposal_id]: p }));
      if (a === "override") setOverride((o) => ({ ...o, [id]: "" }));
      refreshDecisions();
    });

  // A routine's buttons wait while any of its items is being decided on its own, as the items' buttons wait for
  // Fire all: either way round, a second click would race the first into a 409.
  const routineBusy = (g: Group) =>
    Boolean(g.packageId && (busy[g.packageId] || g.items.some((p) => busy[p.proposal_id])));

  const actPackage = (packageId: string, a: "approve" | "hold" | "reject") =>
    run(packageId, actWords(a, "the goal routine"), async () => {
      const items = await decidePackage(packageId, a);
      setProposals((x) => {
        const next = { ...x };
        for (const p of items) next[p.proposal_id] = p;
        return next;
      });
      refreshDecisions();
    });

  const names: Record<string, string> = useMemo(() => Object.fromEntries(
    [meta?.home, meta?.away].flatMap((t: any) => (t?.players ?? []).map((p: any) => [p.player_id, p.name]))
  ), [meta]);
  const name = (id?: string | null) => (id ? names[id] ?? id : "");
  const team = (id?: string | null) =>
    id === meta?.home?.team_id ? meta.home.short_name : id === meta?.away?.team_id ? meta.away.short_name : id ?? "";

  const all = Object.values(proposals);
  const open = all.filter((p) => OPEN.includes(p.status));

  // Goal routine: items sharing a package_id are one card, in running order.
  const groups: Group[] = useMemo(() => {
    const byPackage = new Map<string, Proposal[]>();
    const singles: Group[] = [];
    for (const p of open) {
      if (p.package_id) {
        const list = byPackage.get(p.package_id) ?? [];
        list.push(p);
        byPackage.set(p.package_id, list);
      } else {
        singles.push({ packageId: null, items: [p] });
      }
    }
    const packs: Group[] = [...byPackage.entries()].map(([packageId, items]) => ({
      packageId,
      items: items.sort((a, b) => (a.package_seq ?? 0) - (b.package_seq ?? 0)),
    }));
    return [...packs, ...singles].sort((a, b) => weightOf(a) - weightOf(b));
  }, [open]);

  // Shortcuts act on the top of the running order: the card the operator is looking at first.
  // The running order holds still: a card keeps the place it arrived in. While the pointer is over the list an
  // arrival goes to the bottom, marked new, and moves to its place once the pointer leaves or "+N new" is clicked.
  const [pointerOnList, setPointerOnList] = useState(false);
  const orderRef = useRef<{ order: string[]; pending: string[] }>({ order: [], pending: [] });
  const byKey = new Map(groups.map((g) => [groupKey(g), g]));
  const { order, pending } = stableOrder(
    orderRef.current.order, groups.map((g) => ({ key: groupKey(g), weight: weightOf(g) })), pointerOnList,
    orderRef.current.pending,
  );
  orderRef.current = { order, pending };
  const placed = order.map((k) => byKey.get(k)).filter((g): g is Group => Boolean(g));
  const top = placed[0];
  const topRef = useRef(top);
  topRef.current = top;
  const decideTop = useRef<(a: "approve" | "hold" | "reject") => void>(() => undefined);
  decideTop.current = (a) => {
    const g = topRef.current;
    if (!g) return;
    if (g.packageId) {
      if (!routineBusy(g)) actPackage(g.packageId, a);
      return;
    }
    const p = g.items[0];
    if (busy[p.proposal_id] || (a === "hold" && p.status === "held")) return; // as the buttons are disabled
    act(p.proposal_id, a);
  };
  useEffect(() => {
    if (!settings.shortcuts) return;
    const onKey = (e: KeyboardEvent) => {
      // Named fields: a KeyboardEvent's are prototype getters, which a spread would not copy.
      const a = shortcutFor({
        key: e.key, ctrlKey: e.ctrlKey, metaKey: e.metaKey, altKey: e.altKey, repeat: e.repeat,
        target: e.target as HTMLElement | null,
      });
      if (!a) return;
      e.preventDefault();
      decideTop.current(a);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [settings.shortcuts]);
  // A setting remembered from last time has had no click to unlock sound yet: the first one will do.
  useEffect(() => {
    if (!settings.alert) return;
    window.addEventListener("pointerdown", primeChime, { once: true });
    return () => window.removeEventListener("pointerdown", primeChime);
  }, [settings.alert]);

  const onAir = all
    .filter((p) => p.status === "aired" || p.status === "approved" || p.status === "overridden")
    .sort((a, b) => String(b.decided_at ?? "").localeCompare(String(a.decided_at ?? "")));
  // Fired cards leave the running order, but their deliveries arrive after the decision,
  // so the last few stay here to carry their chips.
  const justFired = onAir.slice(0, 3);
  const log = [...decisions].sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, 15);
  const lineFor = (proposalId: string) => {
    const p = proposals[proposalId];
    return p ? p.override_line ?? p.line : proposalId;
  };

  const nowPlay = clk?.play_ms ?? 0;
  // The latest shot's path and label for a few seconds; after that only its marker stays on the shot map.
  const latestPath = latestShotPath(moments, name);
  const latestPathUp = useRecent(latestPath?.id, SHOT_ON_SCREEN_MS);
  // Degrading rather than stalling is by design, but the operator should be told it is happening.
  // A goal routine's stats and ticker are built in code, not a fallback, so they do not count.
  const fallbackCount = open.filter(isTemplateFallback).length;

  // The run status rests on the API slowing the match while agents write: see agentsWriting() in runStatus.ts
  // before narrowing _awaiting_decision() in the API, or this stops saying "writing" without any error.
  const waiting = open.filter((p) => p.status === "proposed").length;
  if (agentsWriting(speed, runPace, waiting)) writingSince.current ??= Date.now();
  else writingSince.current = null;
  const phase = runPhase({
    starting, running, lastStateAt: lastStateAt.current, writingSince: writingSince.current, now: Date.now(),
  });

  return (
    <DemoContext.Provider value={demo}>
    <div className={`gallery ${demo ? "demo" : ""}`}>
      {demo && (
        <div className="arch-badge" title="You are on /operator-demo. The plain /operator does not show these labels.">
          <span className="arch-badge-dot" aria-hidden="true" />
          ARCHITECTURE OVERLAY
        </div>
      )}
      <header className="gallery-head">
        <div>
          <h1>Graphics operator</h1>
          {meta && <p className="match">{meta.home.name} v {meta.away.name} · {meta.venue}</p>}
          {phase && (
            <p className="run-status" role="status">
              <span className="spinner" aria-hidden="true" />
              {RUN_PHASE_TEXT[phase]}
            </p>
          )}
          {!starting && canStartReplay(Boolean(meta), Boolean(ended), running) && (
            <p className="replay-start">
              <select
                aria-label="How much of the match to replay"
                value={scope}
                onChange={(e) => setScope(e.target.value as ReplayScope)}
              >
                <option value="window">Minutes 41–46</option>
                <option value="full">Full match</option>
              </select>
              {/* Only the dead air: the match still drops to real time whenever a graphic is waiting. */}
              <select
                aria-label="Replay speed between decisions"
                title="Real time is the speed of a live feed. The others compress the gaps between decisions; the match drops to real time whenever a graphic is waiting."
                value={pace}
                onChange={(e) => setPace(Number(e.target.value) as ReplaySpeed)}
              >
                <option value={REAL_TIME}>{speedLabel(REAL_TIME)}</option>
                <optgroup label="Compressed for the demo">
                  {COMPRESSED_SPEEDS.map((s) => <option key={s} value={s}>{speedLabel(s)}</option>)}
                </optgroup>
              </select>
              <button
                className="primary"
                disabled={busy.replay}
                onClick={() => run("replay", "start the replay", async () => {
                  // The status says what is happening from the click until the run's first state arrives.
                  const clickedAt = Date.now();
                  lastStateAt.current = null;
                  setRunPace(pace);
                  setStarting(true);
                  try {
                    await startReplay({ scope, speed: pace });
                  } catch (err) {
                    setStarting(false); // nothing started: the last run's desk stays as it was
                    throw err;
                  }
                  // The last run's cards, log and clock go as soon as the API accepts, not with its match frame,
                  // which can be seconds behind. A match frame that beat this response has cleared them already.
                  if ((matchAt.current ?? 0) < clickedAt) clearDesk();
                  setRunning(true);
                })}
              >
                {meta ? "Run again" : "Start replay"}
              </button>
              {ended?.error
                ? <span className="replay-ended error">Replay stopped: {ended.error}</span>
                : meta && <span className="replay-ended">Replay complete</span>}
            </p>
          )}
        </div>
        {state && (
          <div className="scoreboard">
            <b>{state.home.goals} – {state.away.goals}</b>
            <span>{clk ? clock(clk.clock_ms, clk.period) : clock(state.t_ms, state.period)}</span>
            <small>play {playClock(nowPlay)}{speed ? ` · ${speed === REAL_TIME ? "real time" : `${speed}×`}` : ""}</small>
          </div>
        )}
        <SettingsMenu settings={settings} onChange={changeSettings} />
      </header>

      {/* One bar's height is always kept here, so the desk does not drop when the fallback notice appears. */}
      <div className="desk-notices">
        {link !== "live" && (
          <p className="error" role="alert">
            {link === "connecting"
              ? "Connecting to the API…"
              : "Can't reach the API. Start it with CRQ_OFFLINE=1 — retrying automatically."}
          </p>
        )}
        {logError && link === "live" && (
          <p className="warnbar">{logError} Decisions are still being recorded; the log refreshes every 5 s.</p>
        )}
        {fallbackCount > 0 && (
          <p className="warnbar">
            {fallbackCount} of the graphics waiting came from the template fallback, not a model — the agents may be unavailable.
          </p>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>

      <div
        className="gallery-body"
        ref={bodyRef}
        style={{ gridTemplateColumns: `minmax(0, ${split}%) 10px minmax(0, 1fr)` }}
      >
        {/* ---- left: the decisions ------------------------------------------------ */}
        <section className="running-order">
          <ArchSub>Microsoft Agent Framework · 5 agents · Cosmos DB · 20-second SLA</ArchSub>
          <h2>
            Running order <span className="count">{open.length}</span>
            {pending.length > 0 && (
              <button className="new-cards" onClick={() => setPointerOnList(false)}
                      title="New graphics wait at the bottom while the pointer is on the list, so nothing moves under it. Click to put them in priority order.">
                +{pending.length} new below
              </button>
            )}
          </h2>

          <div className="timeline-slot">
            <Timeline proposals={all} nowPlay={nowPlay} />
          </div>

          {placed.length === 0 && (
            <p className="empty">
              {link !== "live"
                ? "Not connected to the API, so nothing can arrive."
                : starting
                  ? RUN_PHASE_TEXT.warming
                : !meta
                  ? "Connected, but no match is loaded. Press Start replay."
                  : "Match running. No graphics proposed yet — the agents raise these at moments, not continuously."}
            </p>
          )}

          <div className="cards" onPointerEnter={() => setPointerOnList(true)} onPointerLeave={() => setPointerOnList(false)}>
          {placed.map((g) => (
            <article key={groupKey(g)}
                     className={`card ${g.packageId ? "routine" : ""} ${pending.includes(groupKey(g)) ? "arrived" : ""}`}>
              {settings.shortcuts && g === top && (
                <p className="keys-hint" aria-label="Keyboard shortcuts act on this card">
                  <span><kbd>F</kbd>{g.packageId ? "fire all" : "fire"}</span>
                  <span><kbd>H</kbd>hold</span>
                  <span><kbd>D</kbd>drop</span>
                </p>
              )}
              {g.packageId && (
                <div className="routine-head">
                  <h3>Goal routine</h3>
                  <span className="muted">{g.items.length} graphics, one click</span>
                  <PackageCountdown lead={g.items[0]} warned={Boolean(warnings[g.items[0].proposal_id])} />
                  <div className="routine-actions">
                    <button className="fire" disabled={routineBusy(g)} onClick={() => actPackage(g.packageId!, "approve")}>
                      Fire all {g.items.length}
                    </button>
                    <button disabled={routineBusy(g)} onClick={() => actPackage(g.packageId!, "hold")}>Hold</button>
                    <button className="drop" disabled={routineBusy(g)} onClick={() => actPackage(g.packageId!, "reject")}>Drop</button>
                  </div>
                </div>
              )}

              {g.items.map((p) => (
                <Card
                  key={p.proposal_id}
                  p={p}
                  inPackage={Boolean(g.packageId)}
                  showCountdown={!g.packageId}
                  warning={warnings[p.proposal_id]}
                  deliveries={deliveries[p.proposal_id]}
                  override={override[p.proposal_id] ?? ""}
                  // A routine's own buttons wait while Fire all 3 is in flight, or a second click is a 409.
                  busy={Boolean(busy[p.proposal_id] || (g.packageId && busy[g.packageId]))}
                  name={name}
                  showReasoning={settings.reasoning}
                  showPreview={settings.preview}
                  views={views}
                  onChangeViews={changeViews}
                  onOverrideChange={(v) => setOverride((o) => ({ ...o, [p.proposal_id]: v }))}
                  onAct={(a) => act(p.proposal_id, a)}
                />
              ))}
            </article>
          ))}
          </div>

          {justFired.length > 0 && (
            <>
              <h2>Just fired</h2>
              {justFired.map((p) => (
                <article key={`fired-${p.proposal_id}`} className="card fired">
                  <div className="item-head">
                    <b className="layer">{layerName(p.layer)}</b>
                    {/* "aired" means it went out, not that it is still up: the console is not told when a
                        graphic leaves air, so these say Fired rather than On air. */}
                    <span className={`tag ${p.status}`}>
                      {decisionLabel(p.status === "aired" ? "approved" : p.status, p.decided_by)}
                    </span>
                    {p.decided_by && <span className="muted">{p.decided_by}</span>}
                  </div>
                  <p className="line">{p.override_line ?? p.line}</p>
                  <DeliveryChips items={deliveries[p.proposal_id]} />
                </article>
              ))}
            </>
          )}

          <div className="log-head">
            <h2>Decision log</h2>
            <ArchSub>Append-only · Cosmos DB · CSV export · formula-injection safe</ArchSub>
            <a className="csv" href={decisionsCsvUrl} download>Download CSV</a>
          </div>
          <ul className="log">
            {log.length === 0 && <li className="empty">No decisions yet.</li>}
            {log.map((d) => (
              <li key={d.entry_id}>
                <span className={`tag ${d.action}`} title={decisionHelp(d.action, d.actor)}>{decisionLabel(d.action, d.actor)}</span>
                <span className="log-line">{lineFor(d.proposal_id)}</span>
                <small>{d.actor}</small>
              </li>
            ))}
          </ul>
        </section>

        {/* ---- right: what the screens show ---------------------------------------- */}
        {/* Drag to give the decisions or the match more room; the choice is remembered per console. */}
        <div
          className="splitter"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize the columns"
          aria-valuenow={Math.round(split)}
          aria-valuemin={30}
          aria-valuemax={75}
          tabIndex={0}
          onPointerDown={startDrag}
          onPointerMove={onDrag}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onDoubleClick={() => saveSplit(52)}
          onKeyDown={(e) => {
            if (e.key === "ArrowLeft") saveSplit(split - 2);
            if (e.key === "ArrowRight") saveSplit(split + 2);
          }}
        />

        <section className="program">
          <h2>Program feed</h2>
          <ArchSub>Simulator → Azure Event Hubs → Ingest Container App → stats engine</ArchSub>
          <PitchView
            shots={(state?.shots ?? []) as PitchShot[]}
            homeTeamId={meta?.home?.team_id}
            pressureTrend={state?.pressure_trend}
            momentum={state?.momentum_label}
            nameOf={name}
            latestPath={latestPathUp ? latestPath : null}
          />
          <div className="on-air">
            {onAir[0] ? (
              <>
                <span className="on-air-tag">On air · {layerName(onAir[0].layer)}</span>
                <p className="line">{onAir[0].override_line ?? onAir[0].line}</p>
              </>
            ) : (
              <p className="empty">Nothing on air.</p>
            )}
          </div>

          {state && (
            <div className="stats">
              <Stat label="Possession" h={`${state.home.possession_pct}%`} a={`${state.away.possession_pct}%`} />
              <Stat label="xG" h={state.home.xg.toFixed(2)} a={state.away.xg.toFixed(2)} />
              <Stat label="Shots" h={state.home.shots} a={state.away.shots} />
              <Stat label="PPDA" h={state.home.ppda ?? "–"} a={state.away.ppda ?? "–"} />
            </div>
          )}

          <h2>Gallery metrics</h2>
          <ArchSub>Application Insights · OpenTelemetry one trace per moment</ArchSub>
          <MetricsPanel />

          <h2>Match intelligence</h2>
          <MatchIntel state={state} name={name} team={team} />

          <h2>Moments and reasoning</h2>
          <div className="moments">
            {moments.map((m) => (
              <article key={m.moment.moment_id}>
                <div className="meta">
                  {clock(m.moment.t_ms, m.moment.period)} · {m.moment.kind}
                  {m.moment.beat && m.moment.beat !== "none" && <> · {m.moment.beat}</>}
                  {" · "}{m.moment.importance.toFixed(2)}
                </div>
                <b>{m.explanation.headline}</b>
                <p>{m.explanation.why_it_matters}</p>
                <IntelChips metrics={m.intel ?? m.moment.metrics} name={name} />
                <small>
                  pattern: {m.explanation.pattern} · cites {m.explanation.cites.join(", ")}
                  {m.failures.length > 0 && ` · fallback used (${m.failures.length})`}
                  {/* The producer's own call, not a failure; the API writes it for the operator, so as is. */}
                  {(m.notes ?? []).map((note, i) => <span key={i} className="note"> · {note}</span>)}
                </small>
              </article>
            ))}
          </div>
        </section>
      </div>
    </div>
    </DemoContext.Provider>
  );
}

/** Small italic sub-label under a section header; renders only on /operator-demo. */
function ArchSub({ children }: { children: ReactNode }) {
  const demo = useContext(DemoContext);
  if (!demo) return null;
  return <div className="arch-sub">{children}</div>;
}

/** Agent lineage chip for a proposal; renders only on /operator-demo. */
function AgentLineage({ p }: { p: Proposal }) {
  const demo = useContext(DemoContext);
  if (!demo) return null;
  const codeBuilt = isCodeBuilt(p);
  const template = isTemplateFallback(p);
  const live = !codeBuilt && !template;
  const agents = [
    { name: "EXPLAINER", mode: "quality", on: live, title: "Why the moment matters, with cites. router-quality." },
    { name: "NARRATOR", mode: "balanced", on: live, title: "The English on-air line (≤ 22 words). router-balanced." },
    { name: "PRODUCER", mode: "quality", on: live, title: "Layer, template and evidence. router-quality." },
    { name: "PERSONALIZER", mode: "cost", on: live && !codeBuilt, title: "English versions per persona × access. router-cost." },
    { name: "LOCALIZER", mode: "cost", on: live && !codeBuilt, title: "Spanish and Hindi variants. router-cost." },
  ];
  const source = codeBuilt
    ? "Built in code — no agents ran"
    : template
    ? "Template fallback — a model did not produce this line (timeout, decline, or offline mode)"
    : null;
  return (
    <div className="lineage" title={source ?? "The agent pipeline that produced this proposal."}>
      {agents.map((a, i) => (
        <span key={a.name} className={`lineage-agent ${a.mode} ${a.on ? "on" : "off"}`} title={a.title}>
          {a.name}
          {i < agents.length - 1 && <span className="lineage-arrow" aria-hidden="true">→</span>}
        </span>
      ))}
      {source && <span className="lineage-note">{source}</span>}
    </div>
  );
}

/* --------------------------------------------------------------------------- card */

function Card({
  p, inPackage, showCountdown = true, warning, deliveries, override, busy, name,
  showReasoning = true, showPreview = true, views, onChangeViews, onOverrideChange, onAct,
}: {
  p: Proposal;
  inPackage: boolean;
  showCountdown?: boolean;
  showReasoning?: boolean;
  showPreview?: boolean;
  views: string[];
  onChangeViews: (v: string[]) => void;
  warning?: SlaWarning;
  deliveries?: DeliveryAudit[];
  override: string;
  busy: boolean;
  name: (id?: string | null) => string;
  onOverrideChange: (v: string) => void;
  onAct: (a: "approve" | "hold" | "override" | "reject") => void;
}) {
  const holdAt = p.hold_at ? Date.parse(p.hold_at) : null;
  const warnAt = p.warn_at ? Date.parse(p.warn_at) : null;
  const now = Date.now();
  const secondsLeft = holdAt ? Math.max(0, Math.ceil((holdAt - now) / 1000)) : null;
  const warning_on = Boolean(warning) || (warnAt != null && now >= warnAt && p.status === "proposed");
  const advice = p.hold_advice?.recommend_hold ? p.hold_advice : null;
  const unsourced = p.unsourced_numbers ?? [];

  return (
    <div className={`item ${p.status} ${warning_on ? "warn" : ""}`}>
      <div className="item-head">
        <b className="layer">{layerName(p.layer)}</b>
        {p.status === "held" && (
          <span className="tag held" title={decisionHelp(p.status, p.decided_by)}>{decisionLabel(p.status, p.decided_by)}</span>
        )}
        {inPackage && p.item_label && <span className="seq">{p.item_label}</span>}
        {inPackage && (p.package_offset_ms ?? 0) > 0 && (
          <span className="muted">+{Math.round((p.package_offset_ms ?? 0) / 1000)} s</span>
        )}
        {/* Until the scheduler places it, the API's interim slot is t_in == t_out: "00:00 → 00:00". */}
        {p.t_out_ms > p.t_in_ms && <span className="muted">{playClock(p.t_in_ms)} → {playClock(p.t_out_ms)}</span>}
        <span className="muted">priority {Math.round(p.priority)}</span>
        {p.faithfulness != null && (
          <span className={`eval ${p.faithfulness < 0.8 ? "low" : ""}`}>faithfulness {p.faithfulness.toFixed(2)}</span>
        )}
        {modelLabel(p) && (
          <span className="model" title={isCodeBuilt(p) ? "Built from the match stats; no model wrote it" : `routing: ${p.meta?.routing}`}>
            {modelLabel(p)}
          </span>
        )}
      </div>

      {showCountdown && secondsLeft != null && p.status === "proposed" && (
        <div className={`sla ${warning_on ? "warn" : ""}`} title={DECISION_HELP.timer}>
          {warning_on ? `Holds in ${secondsLeft} s` : `${secondsLeft} s to decide`}
        </div>
      )}

      {/* No clock time: a held card expires only once the match has moved past it (play time) AND it has had
          60 s on the desk (wall time). Above 1x those resolve at different moments, so any one time is a guess. */}
      {p.status === "held" && (
        <div className="sla" title={DECISION_HELP.expired}>Expires once the match moves on</div>
      )}

      <p className="line">{p.line}</p>
      <AgentLineage p={p} />
      <IntelChips metrics={p.payload?.intel as MomentMetrics | undefined} name={name} />

      {unsourced.length > 0 && (
        <p className="unsourced">
          Number not from the data: {unsourced.join(", ")}
        </p>
      )}

      {advice && <p className="advice">Hold advised — {advice.reason}</p>}

      {showReasoning && p.evidence?.length > 0 && (
        <ul className="evidence">
          {p.evidence.map((e) => <li key={e.event_id}>{e.text}</li>)}
        </ul>
      )}

      {showReasoning && <p className="reasoning">{p.reasoning}</p>}

      <DeliveryChips items={deliveries} />

      {/* Every item of a goal routine gets its own, since Fire all 3 pushes all three at once.
          Its own boundary too: a bad preview row must never take the Fire button with it. */}
      {showPreview && (
        <ErrorBoundary name="Preview for">
          <PreviewFor
            proposalId={p.proposal_id}
            views={views}
            onChangeViews={onChangeViews}
            overrideLine={override}
          />
        </ErrorBoundary>
      )}

      <input
        id={`override-${p.proposal_id}`}
        placeholder="Replacement line…"
        maxLength={OVERRIDE_MAX}
        value={override}
        onChange={(e) => onOverrideChange(e.target.value)}
      />

      <div className="actions">
        <button className="fire" disabled={busy} onClick={() => onAct("approve")}>Fire</button>
        <button disabled={busy || p.status === "held"} onClick={() => onAct("hold")}>Hold</button>
        <button className="drop" disabled={busy} onClick={() => onAct("reject")}>Drop</button>
        <button disabled={busy || !override.trim()} onClick={() => onAct("override")}>Fire override</button>
      </div>
    </div>
  );
}

/** What each viewer group actually received, and why. Renders nothing until the API reports. */
function DeliveryChips({ items }: { items?: DeliveryAudit[] }) {
  if (!items || items.length === 0) return null;
  const word = (s: string) =>
    s === "variant" ? "✓ variant" : s === "template" ? "↩ template" : s === "override" ? "Override" : "↩ English";
  return (
    <ul className="deliveries" aria-label="What each viewer group received">
      {items.map((d) => (
        <li key={`${d.persona}.${d.access}.${d.lang}`} className={`chip ${d.source}`}>
          <b>{d.lang}</b> {d.persona}{d.access === "deaf" ? " · deaf" : ""}
          <span>{word(d.source)}</span>
          {d.failures.length > 0 && <small>{d.failures.join(", ")}</small>}
        </li>
      ))}
    </ul>
  );
}

/** One countdown for the whole routine, taken from the lead graphic. */
function PackageCountdown({ lead, warned }: { lead: Proposal; warned: boolean }) {
  if (!lead.hold_at || lead.status !== "proposed") return null;
  const left = Math.max(0, Math.ceil((Date.parse(lead.hold_at) - Date.now()) / 1000));
  const warnAt = lead.warn_at ? Date.parse(lead.warn_at) : null;
  const amber = warned || (warnAt != null && Date.now() >= warnAt);
  return (
    <span className={`sla ${amber ? "warn" : ""}`} title={DECISION_HELP.timer}>
      {amber ? `Holds in ${left} s` : `${left} s to decide`}
    </span>
  );
}

/* ----------------------------------------------------------------------- timeline */

/** Layers down, play time across: what is booked, what is queued, and where we are now. */
function Timeline({ proposals, nowPlay }: { proposals: Proposal[]; nowPlay: number }) {
  const from = Math.max(0, nowPlay - WINDOW_MS / 3);
  const to = from + WINDOW_MS;
  // Until scheduler.py lands the API gives an interim "air now" slot with t_in == t_out.
  // Those are drawn at the now marker and labelled, not placed somewhere invented.
  const unscheduled = (p: Proposal) => !(p.t_out_ms > p.t_in_ms);
  const live = (p: Proposal) => p.status !== "rejected" && p.status !== "expired";
  const shown = proposals.filter(
    (p) => live(p) && (unscheduled(p) ? OPEN.includes(p.status) : p.t_out_ms > from && p.t_in_ms < to),
  );
  const layers = [...new Set(shown.map((p) => p.layer))].sort();
  const pos = (ms: number) => ((Math.min(Math.max(ms, from), to) - from) / (to - from)) * 100;
  const anyUnscheduled = shown.some(unscheduled);

  if (layers.length === 0) return <p className="empty">The timeline fills as graphics are scheduled.</p>;

  return (
    <div className="timeline" aria-label="Layers against play time">
      {layers.map((l) => (
        <div className="track" key={l}>
          <span className="track-name">{layerName(l)}</span>
          <div className="lane">
            {shown.filter((p) => p.layer === l).map((p) => (
              unscheduled(p) ? (
                <div
                  key={p.proposal_id}
                  className={`block ${p.status} unscheduled`}
                  style={{ left: `${pos(nowPlay)}%`, width: "3%" }}
                  title={`${p.line} — unscheduled, air now`}
                />
              ) : (
                <div
                  key={p.proposal_id}
                  className={`block ${p.status}`}
                  style={{ left: `${pos(p.t_in_ms)}%`, width: `${Math.max(1.5, pos(p.t_out_ms) - pos(p.t_in_ms))}%` }}
                  title={`${p.line} (${playClock(p.t_in_ms)}–${playClock(p.t_out_ms)})`}
                />
              )
            ))}
            <div className="now" style={{ left: `${pos(nowPlay)}%` }} />
          </div>
        </div>
      ))}
      <div className="scale"><span>{playClock(from)}</span><span>{playClock(to)}</span></div>
      {anyUnscheduled && (
        <p className="timeline-note">Hatched blocks are unscheduled — the API is airing them now because the scheduler has not placed them yet.</p>
      )}
    </div>
  );
}

const Stat = ({ label, h, a }: { label: string; h: any; a: any }) => (
  <div className="stat"><span>{h}</span><label>{label}</label><span>{a}</span></div>
);
