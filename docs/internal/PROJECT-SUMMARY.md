# Control Room IQ — project summary (start here)

**Last updated:** Friday, October 23, 2026, night · **Owner:** Swami
**Purpose:** one entry point for the team and for anyone reading the repo. Each section links to the detailed doc.
Where documents disagree, the newest decision wins, and the contract in `packages/schemas` governs the build.

---

## 1. At a glance

| Item | Detail |
| --- | --- |
| Hackathon | **Inside the Game: Developer Hackathon** (Microsoft × Premier League), global and virtual |
| Brief | Turn **synthetic** football event data into explainable match intelligence, real-time narratives, recaps and personalized experiences for studio, broadcast and streaming. No real match data |
| Deadline | Tuesday, October 27, 2026, 11:59 pm Pacific (team target: noon Central) |
| Submission | Public GitHub repo, project page, demo video under 2 minutes, testing instructions |
| Our entry | **Control Room IQ**, "the AI member of the production gallery" |
| Category | **Best Enterprise Solution** (primary), Best Use of Microsoft Foundry (secondary) |
| Judging (equal weights) | Technological implementation · agentic design and innovation · real-world impact · UX and presentation · category fit |

---

## 2. Team and ownership

| Person | Role | Owns |
| --- | --- | --- |
| **Swami** | Lead, API, Azure plumbing | API, Bicep router deployments, `azd up`, Event Hubs, Cosmos, Logic App hold timer, CI, hosted URL, operator session, video, docs |
| **Pranav B** | Simulator, stats and data | Simulator, stats engine and match intelligence, reference matches, evaluation datasets, thresholds |
| **Siranjeevi K** | Agents and evaluations | The five agents and `workflow.py`, router clients (`model_served` on spans), `scheduler.py`, Agent Service registration, Foundry evaluation run and README table |
| **Mudassar Syed** | Front end | Graphics operator console, top-down pitch view, renderer on `OverlayPacket`, viewer page, deaf fan's view, catch-up card |

**Boundary rule:** a finding that changes *what the user sees or which features exist* goes to Swami. A finding
that changes *how existing code works* belongs to the engineer.

Open work per person is in the handoff docs: [HANDOFF-2026-10-24-agents-siranjeevi.md](HANDOFF-2026-10-24-agents-siranjeevi.md),
[HANDOFF-2026-10-24-web-mudassar.md](HANDOFF-2026-10-24-web-mudassar.md) (consolidated front-end list),
[HANDOFF-2026-10-24-match-intelligence.md](HANDOFF-2026-10-24-match-intelligence.md),
[HANDOFF-2026-10-24-goal-routine-metrics.md](HANDOFF-2026-10-24-goal-routine-metrics.md),
[HANDOFF-2026-10-24-fan-card.md](HANDOFF-2026-10-24-fan-card.md).

---

## 3. The concept

Control Room IQ ingests synthetic match events, turns them into live match state, explains why key moments
matter, proposes what goes on screen and when, and routes **every** graphic through a human graphics operator
(fire, hold, drop, override).

- **The gate is mandatory by design.** No setting lets the AI air anything. A proposal nobody acts on gets a
  warning at 10 seconds and is **held** at 20 seconds, never fired. A held graphic that is no longer relevant expires.
- The approved moment goes **first to the deaf fan, live**: a visual cue on the strike, then a plain-language
  caption on the result, in their language.
- Every other viewer gets it by knowledge level, language and team supported. Code checks decide whether an AI
  version or a template line airs.

**Personas:** (1) the **graphics operator** in the production gallery, who has seconds to decide and needs evidence
and one-click control; (2) the **deaf fan**, who has pictures and the score but no commentary, crowd or whistle.

**Design method:** Personas → Moments → Questions → Information needed → Experience, then Data → Models →
Architecture → Implementation.

---

## 4. Current status (Friday, October 23, night)

**On `main` (through #24):** schemas v0.2, API v0.2, pipeline v0.2 with three reference matches, goal routine,
gallery metrics, hold warning and expiry, preview before firing, match intelligence with the review fixes, the deaf
fan's caption card built in code, README rewrite, consolidated agents handoff.

**Waiting for review:** `feat/localizer-agent` (five agents: Localizer added, personalizer English only, fallback fix #17).

**Next:**
- Agents: fix the startup crash in Azure (#9), `scheduler.py`, router clients per agent, live check against the
  model router (#10), `register_agents.py`, evaluations.
- Simulator and stats: match intelligence in the stats engine, real distance covered, evaluation datasets, data
  provenance note.
- Front end: viewer controls, console words, goal routine card, countdown and expiry, preview picker, metrics
  panel, match intelligence panel, scheduler view, caption card.
- Azure: three router deployments in Bicep, first `azd up`, Logic App hold timer.

### Demo definition of done

Offline replay (`CRQ_OFFLINE=1`), no login: big chance → deaf fan's cue within about 1 s and the strike lit on the
pitch → console proposal with evidence, faithfulness, routed model and hold countdown → graphics operator fires or
overrides → caption on the deaf fan's screen → timeline shows a later goal preempting the lower third → decision
log lists every action, including a hold by the timer. The full acceptance scenario is in
[END-TO-END-ARCHITECTURE.md](END-TO-END-ARCHITECTURE.md) §14.

---

## 5. Timeline

| Day | Focus |
| --- | --- |
| Tue Oct 20 | Registered; repo created; stack and Azure decisions |
| Wed Oct 21 | Repo docs |
| Thu Oct 22 | Personas and moments; positioning; roles; front-end decisions D1–D3 |
| Fri Oct 23 | Schemas and API v0.2; pipeline; goal routine, metrics, timing, preview; match intelligence; caption card; five-agent decision |
| Sat Oct 24 | Scheduler, router clients, Agent Service registration, evaluations, cloud deploy, Logic App |
| Sun Oct 25 | Docs refresh (SOLUTION, PLAN), parked items |
| Mon Oct 26 | Video, project page, evaluation table, tests green in CI |
| Tue Oct 27 | Submit |

---

## 6. Key decisions (latest first)

| Date | Decision |
| --- | --- |
| Oct 24 | **Five agents**, registered by name: `explainer` (router-quality), `narrator` (router-balanced: the English on-air line and the half- and full-time recap), `producer` (router-quality), `personalizer` (router-cost, English only), `localizer` (router-cost, Spanish and Hindi in one call). No Recap agent; `GET /recap` is code. Spanish and Hindi are a constrained translation of the checked English versions; on failure, the template line in that language, never English labeled as Spanish or Hindi |
| Oct 23 (night) | Match intelligence review: a number on the English line that is not in the facts is flagged to the operator (`unsourced_numbers`); speed moments on the lower third; fans get whole numbers, analysts one decimal; viewer chips stay English for now |
| Oct 23 (evening) | **One caption card** for the deaf fan, facts filled in code. **Producer takeover** is the stated next step, not built: "if the graphics operator is away, the producer's console takes over; the AI never does" |
| Oct 23 | **No AI or default decision** when the operator does not act: warn at 10 s, hold at 20 s, expire stale held graphics. **Preview before firing** for the viewer groups the operator picks |
| Oct 23 | After a call with a control-room operations lead: **goal routine** (one click fires goal graphic → scorer stats after the replay → ticker; follow-ups computed in code), **gallery words** on screen and in docs ([GALLERY-TERMS.md](GALLERY-TERMS.md)), **`GET /metrics`** (turnaround, error rate, workload) |
| Oct 23 | **Viewer model, four independent axes:** Persona (newcomer / fan / analyst) × Access (none / deaf) × Lang (en / es / hi) × Allegiance (home / away / neutral) |
| Oct 23 | **Approval scope:** the operator approves the English line once. A version in another register or language airs only if `variant_checks.py` passes; otherwise a template in that language (`fallback_text.py`), otherwise English. Goals, cards and stoppages always use templates outside English. Overrides air unverified, in English, with a badge |
| Oct 23 | **FanCue is built in plain code** (`fan_cue.py`): pulse from importance; direction by broadcast convention (home attacks left to right in the first half) |
| Oct 22 | Schedule on play-time ms, display the match clock. Approval triple on every packet. Languages EN, ES, HI (Arabic and right-to-left dropped). No Speech or audio description. Deaf fan's view uses event-driven cards plus a live strip |
| Oct 20 | Stack: Python 3.11+, Microsoft Agent Framework, FastAPI, React + TypeScript. Azure: Container Apps, Event Hubs, Cosmos DB (serverless), Logic Apps, Bicep + `azd`, East US 2. Model router as three deployments plus a `gpt-4.1-mini` fallback. Our own deterministic, seedable simulator is the ground truth |

---

## 7. Architecture and contract (summary)

```
Simulator (play_ms, shot_taken, stoppage, whistle, crowd, phase_id, x/y)
 → stats engine (MatchState, xG, pressure_trend, shots, phase trail, match intelligence)
 → moment detector
     ├─ strike beat → fan_cue.py (code, ≤ 1 s) → /ws/viewer + pitch highlight
     └─ result beat → Agent Framework workflow (one trace per moment_id)
          Explain → Narrator (English on-air line)
            → Producer                       ∥  Personalizer (English) → Localizer (es, hi)
            → scheduler.py (code)
          → publisher checks + variant_checks.py → Cosmos
 → Graphics operator console: fire / hold / drop / override, undo; preview; 10 s warning, 20 s hold, expiry
 → OverlayPacket {approval_id, approved_by, approved_at, cue_id, t_in/t_out, replaces[]}
     → /ws/overlay (renderer; also the crq-overlay Event Hub)
     → /ws/viewer?persona=&access=&lang=&allegiance=
```

**Settled rules**
1. Schedule on `play_ms`; display `{period, clock_ms}`.
2. **Structural gate:** text reaches a screen only inside an `OverlayPacket` that carries the approval triple. The renderer refuses anything else.
3. **Numbers from code, words from models. Cues are code, captions are AI. Scheduling is code, content is AI.** Models never calculate xG, score, speed or timing.
4. **Model choice is visible:** `router-quality` (explainer, producer), `router-balanced` (narrator), `router-cost` (personalizer, localizer). The routed model is recorded on every span and shown on the proposal.
5. Top-down pitch view (SVG, 105 × 68) drawn from the event stream. No video, no 3D.
6. Clean room: synthetic data only, no scraped commentary, no pre-trained football models, no copied third-party code.

**Key thresholds:** big chance at xG ≥ 0.30 or chance_rank ≤ 3; pressure spike at 9/min; pressure trend over a
3-minute window; `shot_taken` 400–900 ms before the outcome; faithfulness ≥ 0.8 for variants.

Detail: [END-TO-END-ARCHITECTURE.md](END-TO-END-ARCHITECTURE.md), [DESIGN.md](DESIGN.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [CHANGES-2026-10-23.md](CHANGES-2026-10-23.md).

---

## 8. Front-end decisions (Oct 22)

- **D1 approval:** fire / hold / drop + undo-as-revert; edit-with-re-verify later. Status is a derived predicate, not a transition graph. Undo is not "take off air" (drop is). One decision in flight at a time.
- **D2 transport:** the renderer holds the clock. Packets arrive ahead of time with play-ms timing and are upserted by `cue_id`. Preemption is a re-send with a shortened duration. Late packets anchor at arrival. The caption layer never queues. Uses `min_hold_ms` and per-kind `max_delay_ms`.
- **D3 blocking (two-tier, to confirm):** `unsupported` is a hard block with no override; `uncertain` needs a logged acknowledgment. The server enforces it; the UI shows reasons, not scores.
- **Never cut:** hold countdown, visible approval → fan causality, scheduler timeline, pitch view.

---

## 9. Submission checklist

- [ ] Hosted public URL with a pre-loaded replay, no login
- [ ] Video under 2 minutes; first 20 seconds say: live during play · approved by the gallery · reaching the fan who can't hear it
- [ ] README proof block filled with measured figures only (URL, video, tests, Foundry evaluation, planted falsehoods, operator quote)
- [ ] Foundry evaluation table (faithfulness, relevance, fluency per language, planted falsehoods caught)
- [ ] Tests green in CI; Bicep / `azd` one-command deploy
- [ ] Decision log download (`/decisions.csv`)
- [ ] Project page tagline, description and category

---

## 10. Open items

1. D3 two-tier blocking: confirm.
2. Control-room operator validation session and one quote for the README and video.
3. Native-speaker review of the Spanish and Hindi templates and of Localizer output on the reference match.
4. Whether `t_start_ms` / `t_end_ms` become display-only once the scheduler lands.
5. Azure subscription and model router quota (East US 2); GitHub Actions OIDC variables.

---

## 11. Document index

| Doc | What it's for |
| --- | --- |
| [PROJECT-SUMMARY.md](PROJECT-SUMMARY.md) | **This page.** Start here |
| [END-TO-END-ARCHITECTURE.md](END-TO-END-ARCHITECTURE.md) | Principles, components, runtime flows, contracts, Azure deployment, quality gates, decision log |
| [DESIGN.md](DESIGN.md) | Detailed design: viewer model, agents, delivery rules, fallbacks |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Azure architecture and latency budget |
| [SOLUTION.md](SOLUTION.md) · [PLAN.md](PLAN.md) | Solution overview and plan (refresh on Sunday) |
| [CHANGES-2026-10-23.md](CHANGES-2026-10-23.md) | The v0.2 contract change plan |
| [GALLERY-TERMS.md](GALLERY-TERMS.md) | Gallery roles and on-screen words |
| [CALIBRATION.md](CALIBRATION.md) | Simulator realism checks |
| [SETUP.md](SETUP.md) | Local and Azure setup |
| `HANDOFF-*.md` | Open work per person |
| [adr/](adr/) | Long-form decision records |

**Keeping this page current:** when a decision is made, add one line to §6 and update §4 and §10.
