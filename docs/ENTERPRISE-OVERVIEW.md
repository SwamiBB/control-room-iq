# Enterprise architecture overview

This document is the enterprise-readiness overview for Control Room IQ: how production controls —
reliability, transparency and audit — are enforced in code rather than policy. Every claim here points at
a file in this repository.

> **One-sentence pitch.** Control Room IQ is the AI member of the production gallery: five Foundry agents
> propose what goes on screen, a graphics operator fires every graphic, and the deaf fan is served first.
> The AI cannot put anything on air by itself — not because we told it not to, because the schema will not
> let it.

Live demo: see the top of [README.md](../README.md). All match data is synthetic.

---

## The enterprise claim

Production controls in a broadcast gallery mean reliability, transparency and auditability. Here is where
each lives in the code.

### 1. The gate is in the schema, not in a setting

A renderer only airs text that is wrapped in an `OverlayPacket`. The packet type **cannot be constructed
without** `approval_id`, `approved_by`, `approved_at` — these are required fields on the Pydantic model.

- Schema: [`packages/schemas/crq_schemas/__init__.py:560`](../packages/schemas/crq_schemas/__init__.py) —
  `class OverlayPacket` with required approval triple at lines 583–585.
- Guard: [`services/api/api/packets.py`](../services/api/api/packets.py) — docstring: *"The packet type
  itself is the gate, since it cannot be constructed without approval fields."*
- Negative-path test: [`services/api/tests/test_gate.py`](../services/api/tests/test_gate.py) —
  `test_approve_stamps_packet_with_the_decision` asserts the stamped triple matches the decision log entry.
- Status rule: [`services/api/tests/test_approval.py`](../services/api/tests/test_approval.py) —
  `test_approve_then_cannot_hold` proves the state machine refuses contradictory actions.

**There is no auto-approve path, no auto-approve setting, no bypass flag.** The SLA timer can `hold`,
never `approve` — see [`services/api/api/timing.py`](../services/api/api/timing.py).

### 2. Numbers from code, words from models

Every number that reaches air comes from the stats engine. Agents may quote but never compute. A number
in the English line that the stats engine did not produce is flagged to the operator before firing.

- Rule: [`docs/END-TO-END-ARCHITECTURE.md`](END-TO-END-ARCHITECTURE.md) §2, principle P1.
- Flag field: `OverlayProposal.unsourced_numbers` — see schema line 556.
- Variant checks: [`services/api/api/variant_checks.py`](../services/api/api/variant_checks.py) — rejects
  invented numbers, changed names, cites outside the moment, banned topics (referee / betting / injury),
  low faithfulness, and text that was never translated.
- Enforcement: [`services/api/tests/test_variant_checks.py`](../services/api/tests/test_variant_checks.py)
  and [`test_variant_checks_intel.py`](../services/api/tests/test_variant_checks_intel.py).

### 3. Model choice is auditable per agent

Three router deployments (`router-quality`, `router-balanced`, `router-cost`). Every agent is bound to
one. The model the router selected is recorded on every span and on every proposal.

- Routing table: [`services/agents/agents/config.py`](../services/agents/agents/config.py) —
  `AGENT_ROUTING` and `deployment_for(agent)`.
- Visible on the proposal: `OverlayProposal.model_served` field.
- Trace: one OpenTelemetry trace per moment; each agent call is a span carrying its routing mode and
  the model the router chose (`crq.model_served`), which also goes into `meta.model_served`.

### 4. Full audit trail

- Every decision (approve, override, hold, reject, SLA hold, expiry, supersession) is appended to the Cosmos DB
  `decisions` container, once, per replay run (`services/api/api/decision_store.py`).
- **Scope:** the audit record (decisions) is durable; in-flight state (proposals, packets, in-progress agent runs) is
  kept in the API's in-memory hub for the lifetime of a run. An API restart loses only the current run's working
  set; every decision ever written survives.
- Downloadable at `GET /decisions.csv` (route in
  [`services/api/api/main.py:407`](../services/api/api/main.py); CSV built in
  [`services/api/api/exports.py`](../services/api/api/exports.py), with formula-injection
  prefixes neutralised).
- Per-viewer-group delivery visible at `GET /deliveries` (route in
  [`services/api/api/main.py:418`](../services/api/api/main.py); variant selection in
  [`services/api/api/delivery.py`](../services/api/api/delivery.py)).

### 5. Enterprise substrate

- **No secrets in source.** Managed identity + OIDC from GitHub Actions. `.env.example` is checklist-only.
- **Supply chain.** [`.github/workflows/codeql.yml`](../.github/workflows/codeql.yml) scans Python,
  TypeScript and workflow files. [`.github/workflows/trivy.yml`](../.github/workflows/trivy.yml) scans
  dependencies, secrets, Dockerfiles and Bicep-compiled ARM, plus the three container images.
  [`.github/dependabot.yml`](../.github/dependabot.yml) keeps actions and dependencies current.
- **Pinned to commit SHAs.** Every GitHub action is pinned to a full commit SHA (not a tag), with the
  CVE-2026-33634 trivy-action supply-chain attack cited in the workflow header as the reason.
- **Degrade, never stall.** Every agent has a timeout and a deterministic template fallback. `CRQ_OFFLINE=1`
  runs the whole pipeline with no Azure. The demo survives model quota failure.
- **Clean room.** Synthetic data only — no scraped commentary, no pre-trained football models, no third-party
  match data, no code copied from any company product.

See [`SECURITY.md`](../SECURITY.md) for the full posture.

---

## Three-minute walkthrough

The judge-ready walkthrough is in the [README](../README.md#judge-walkthrough-about-three-minutes-no-login).
Highlights to notice:

1. **Minute 41 strike** — pulse reaches the deaf-fan screen in under a second (code, no model).
2. **Supersession** — a goal 1.5 s later takes over the chance proposal automatically.
3. **Fire all 3** — the goal routine fires three graphics with one click.
4. **Preview** — pick viewer groups and see exactly what each would receive, before anything airs.
5. **20-second SLA** — leave a card untouched; it is held, never aired.
6. **Override** — operator text airs in English with an unverified badge; audit row written.
7. **Metrics** — turnaround, error rate, workload; download `decisions.csv`.

---

## Evidence index

| Claim | File | What to look for |
| --- | --- | --- |
| Approval triple required on every packet | `packages/schemas/crq_schemas/__init__.py:560` | `OverlayPacket` with `approval_id`, `approved_by`, `approved_at` |
| Packet construction is the gate | `services/api/api/packets.py` | Module docstring |
| Negative-path gate test | `services/api/tests/test_gate.py` | `test_approve_stamps_packet_with_the_decision` |
| Approve → aired, cannot hold | `services/api/tests/test_approval.py` | `test_approve_then_cannot_hold` |
| SLA holds, never approves | `services/api/api/timing.py` | `warn_at`, auto-hold, expiry |
| Unsourced numbers flagged | `packages/schemas/crq_schemas/__init__.py:556` | `OverlayProposal.unsourced_numbers` |
| Variant checks catch invention and banned content | `services/api/api/variant_checks.py` | Module docstring + `_BANNED` patterns |
| Per-agent model router | `services/agents/agents/config.py` | `AGENT_ROUTING`, `deployment_for` |
| Model served recorded per call | `services/agents/agents/workflow.py:292` | `getattr(response, "raw_representation", None).model` captured into `info["model_served"]` |
| Append-only decision log, CSV export | `services/api/api/main.py:407` (route) + `services/api/api/exports.py` (body) | `/decisions.csv`, formula-injection safe |
| Per-viewer-group deliveries | `services/api/api/main.py:418` (route) + `services/api/api/delivery.py` (logic) | `/deliveries` |
| CodeQL on Python, TS, workflows | `.github/workflows/codeql.yml` | Matrix languages, pinned SHAs |
| Trivy on deps, secrets, Dockerfiles, Bicep | `.github/workflows/trivy.yml` | Workflow header note on CVE-2026-33634 |
| Dependabot | `.github/dependabot.yml` | Weekly cadence |
| Offline mode as first-class | `services/api/api/offline.py`, `CRQ_OFFLINE=1` | Whole pipeline runs with no Azure |

---

## What is intentionally not built

Honesty on scope is part of the enterprise story.

**Product scope**

- Sign-in and roles via Entra ID — stated as the next step; the producer takeover depends on it. Until it lands,
  any client that can reach the API can call the decision endpoints and the actor on the request is trusted.
  This is explicitly called out in the README limits section.
- Spanish and Hindi templates and labels still need a native-speaker review pass.
- Offside and VAR appear as text only; no dedicated graphics.
- Distance covered counts runs with the ball until the tracking totals are wired in.

**Enterprise architecture gaps** *(flagged in the external review; carried as post-submission items)*

- **Event-driven agent worker.** The intended Azure topology has `services/ingest` publishing moments to the
  `crq-moments` Event Hub and a separate agent worker consuming them. The current implementation runs the whole
  pipeline (simulator → stats → agents → proposals → approvals → overlay) in-process inside the API container,
  which the live deployment does successfully. The second worker is deferred to a post-submission iteration.
- **Deterministic placement scheduler.** `scheduler.py` is the "Landing shortly" row in the README table.
  Proposals are timed by arrival; collision resolution, preemption, and `t_in_ms/t_out_ms` placement arrive
  with that module.
- **Direct model fallback.** `MODEL_FALLBACK_DEPLOYMENT` is provisioned by Bicep (`infra/modules/ai.bicep`
  deploys the `gpt-4.1-mini` fallback) and injected into the API container, but the current fallback path for
  each agent is its deterministic template, not a direct call to this deployment. Wiring the direct fallback is
  a post-submission item.
- **In-flight state persistence.** Decisions are durable (Cosmos DB, per §4). Proposals, packets and in-progress
  agent runs live in memory for the duration of a run. A full Cosmos-backed working set is a post-submission item.

**Known data-path edges**

- **Momentum decay after half time.** `_recent` in `services/ingest/ingest/stats.py` stores period-local
  `ev.t_ms`; a brief window after half time the decay math can over-weight late-first-half events until the
  60-slot buffer rotates clean. Fix is to store `play_ms` for the recent window; filed for post-submission.
- **Pass-accuracy guard with missing distance.** Pass accuracy aggregates can go stale when a pass event is
  missing `distance_m` because the quality-recalc path returns early. Not seen on the current synthetic
  fixtures; the fix is to split distance-dependent quality from count-based accuracy.
- **`new_match` transient state.** Starting a new match clears the hub but keeps `match_state` populated with
  the previous match until the new folder loads. A `/recap` call during that window would see the previous
  state behind the new metadata. Fix is to set `match_state = None` during `new_match`.

See [README §Limits](../README.md#limits) for the shipped-feature limits.
