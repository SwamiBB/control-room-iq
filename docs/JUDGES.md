# For judges

A one-page map of Control Room IQ against the hackathon's five scoring criteria. Everything here points at
code in this repository.

> **One-sentence pitch.** Control Room IQ is the AI member of the production gallery: five Foundry agents
> propose what goes on screen, a graphics operator fires every graphic, and the deaf fan is served first.
> The AI cannot put anything on air by itself — not because we told it not to, because the schema will not
> let it.

Category: **Best Enterprise Solution** (also fits Best Use of Microsoft Foundry).
Live demo: see the top of [README.md](../README.md). All match data is synthetic.

---

## Scoring at a glance

| Criterion | Where to look first | Why it earns the score |
| --- | --- | --- |
| **Technological Implementation** | [`packages/schemas/crq_schemas/__init__.py`](../packages/schemas/crq_schemas/__init__.py), [`.github/workflows/`](../.github/workflows/), [tests count in CI] | Typed, versioned contract shared by every service; CodeQL + Trivy + Dependabot on every PR; pinned to commit SHAs; GitHub Actions via OIDC with no secrets |
| **Agentic Design & Innovation** | [`services/agents/agents/workflow.py`](../services/agents/agents/workflow.py), [`services/agents/agents/config.py`](../services/agents/agents/config.py), [`docs/END-TO-END-ARCHITECTURE.md`](END-TO-END-ARCHITECTURE.md) §5.2 | Five agents on Microsoft Agent Framework; per-agent router (quality / balanced / cost); every agent has a timeout and a template fallback; "degrade, never stall" |
| **Real-World Impact & Applicability** | [`docs/END-TO-END-ARCHITECTURE.md`](END-TO-END-ARCHITECTURE.md) §12, [`services/api/api/goal_package.py`](../services/api/api/goal_package.py), [`services/api/api/preview.py`](../services/api/api/preview.py) | Shaped by feedback from a working control-room operations lead; the deaf fan is served first; operator "Fire all 3" matches gallery practice; per-group preview before firing |
| **User Experience & Presentation** | [`web/src/views/Operator.tsx`](../web/src/views/Operator.tsx), [`web/src/views/Viewer.tsx`](../web/src/views/Viewer.tsx), demo video | Operator console, pitch view, SLA countdown, hold advice, routed-model badge; four-axis viewer picker (persona × access × lang × allegiance); deaf-fan second screen |
| **Adherence to Hackathon Category** (Best Enterprise) | the next section | Reliability, transparency and controls are not features — they are the schema |

---

## Why this is the Best Enterprise Solution

The category rewards "reliability, transparency, and controls required for production." Here is where each
lives in the code.

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
- Trace: one OpenTelemetry trace per `moment_id`; `agent.run` wrapped to capture
  `response.model` into `meta.model_served`.

### 4. Full audit trail

- Every agent output writes an `EvaluationRecord` (schema). Every operator decision, undo, SLA hold, and
  reject lands in an append-only decisions container.
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

- Sign-in and roles via Entra ID — stated as the next step; the producer takeover depends on it.
- Spanish and Hindi templates and labels still need a native-speaker review pass.
- Offside and VAR appear as text only; no dedicated graphics.
- Distance covered counts runs with the ball until the tracking totals are wired in.

See [README §Limits](../README.md#limits) for the full list.
