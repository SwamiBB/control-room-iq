# Copilot-Assisted Review Record

**Review date:** 2026-10-27
**Project:** Control Room IQ
**Purpose:** Record the project-readiness review and two static code-review passes for the hackathon submission.

## Scope and limitations

This report records review observations, not proof that a defect has been reproduced or fixed. The reviews were based on source, configuration, project documentation, the published hackathon rules, and (for the first readiness pass) a limited browser inspection of the public demo.

- No application, test suite, build, linter, or local demo was run as part of the static code-review passes.
- The browser inspection was limited to the public demo pages and does not establish that all paths work reliably.
- Findings identify code paths that appear incomplete or incorrect by inspection. They require owner review and, where appropriate, targeted tests before being treated as confirmed runtime defects.
- This document records AI-assisted review observations. The project team is responsible for validation, prioritization, and any changes.

## Revisions reviewed

| Pass | Revision | Scope |
|---|---|---|
| Initial readiness and static review | Local `main` at `444924f` | Hackathon-rule alignment, project documentation, and static inspection of the API, agents, ingest/statistics, and frontend integration paths. Limited browser inspection was separate from the static review. |
| Targeted recheck | `origin/main` at `b0a979431ed2e6e5fb8bcdbe4642979b96285d79` | Rechecked only the seven findings from the initial code review against the latest fetched upstream revision. |

At the time of the recheck, the local `main` branch was 18 commits behind `origin/main`. The second pass reviewed the fetched remote source without updating the local checkout. Confirm the revision again before relying on this report for a later submission or release.

## Hackathon-readiness observations

The project concept maps well to the challenge: it describes a synthetic-event pipeline, match statistics and context, explanations, on-screen graphics, and personalized viewer experiences, including language and deaf-viewer support.

The first readiness pass noted these submission actions in the README and project material at the reviewed revision:

1. Replace the demo-video `[link]` placeholder with a public video under two minutes, and ensure the project-page entry includes it.
2. Provide concise English testing instructions and verify the judge path from a fresh start. The rules require a working project to be available for evaluation through the judging period.
3. Replace or remove placeholder evaluation results and operator-quote fields. Do not publish unmeasured or unapproved claims.
4. Ensure the README, project page, video, screenshots, and deployed behavior make consistent claims about scheduling, Foundry services, evaluation, and tracing.
5. Present enterprise readiness proportionately. The reviewed documentation described operator access-control limitations; do not imply production security controls that are not implemented.

These are submission-preparation observations from the first pass, not a new verification of the current submission page or current deployment.

## Static code findings and recheck

| ID | Priority | Finding | Initial review | Rechecked at `b0a9794` |
|---|---|---|---|---|
| C1 | High | **Azure event-driven agent path appears unwired.** The API documentation describes consuming `crq-moments`, and ingest publishes moments, but the inspected deployment defines API, ingest, and web apps without an agent consumer for that stream. The API pipeline invocation is in the local replay/moment-handling path. | Open | Still open by inspection |
| C2 | High for enterprise use | **Operator decision routes have no application-level authentication or authorization in the inspected code.** Decision routes accept a request-provided `actor`; the API also configures wildcard CORS. This means the actor value is not a verified identity. | Open | Still open by inspection |
| C3 | Medium | **The display schedule is not a placement scheduler.** The API does not pass on-air state into the pipeline, and `schedule.py` constructs a read-only view. Proposals without placement fields use the immediate-air fallback in `packets.py`. | Open | Still open by inspection |
| C4 | Medium | **Momentum decay compares period-local timestamps across periods.** Recent actions are recorded and decayed using `ev.t_ms`; because the match clock resets at halftime while the recent-action window remains, first-half events may be assigned an incorrect age in the second half. | Open | Still open by inspection |
| C5 | Medium, edge case | **Pass-accuracy aggregate may not be refreshed when pass distance is absent.** Pass counts update before `_rate_pass`, but that function returns early if `distance_m` is missing; the percentage is computed after that guard. The event schema allows optional attributes, so this is a robustness gap even if current synthetic records always include distance. | Open | Still open by inspection |
| C6 | Low, transient | **Previous `match_state` can remain during new-match initialization.** `new_match` clears the serialized state but not `match_state` before asynchronous loading of the next folder completes. | Open | Still open by inspection |
| C7 | Medium, durability | **API proposals and audit data are held in process memory.** The inspected `Hub` stores proposals, decisions, packets, and deliveries in memory; ingest-side Cosmos writes do not persist the API's approval state. | Open | Still open by inspection |

“Still open by inspection” means the relevant code pattern remained in the fetched revision; it does not mean the issue was reproduced at runtime.

## Dead-code and documentation observations

The initial static pass also noted:

- `model_fallback` / `MODEL_FALLBACK_DEPLOYMENT` appeared to be declared in configuration and Bicep but not consumed by the agent-client path.
- `ReplayDriver` appeared to have test coverage but no production call site in the application or simulator CLI.
- The API module docstring described an Azure consumer and `store.py` persistence path that were not present in the tracked implementation inspected.

These are candidates for removal, clearer experimental/test-only labeling, or implementation. They were not part of the seven-finding targeted recheck and should be rechecked before action.

## Suggested follow-up

1. Assign an engineer to confirm each finding against the intended architecture.
2. Reproduce relevant behavior with focused tests, especially halftime momentum, distance-less pass records, and new-match initialization.
3. Decide whether the Azure event-driven worker, scheduling, authentication, and durable API state are required for the submission or are explicitly out of scope.
4. Update claims and close or defer findings with a rationale; do not describe an observation as fixed until the change is verified.


## Latest broad static codebase audit

**Review date:** 2026-10-27  
**Revision reviewed:** `f75393c5ad1decd44cc8904d3d4c6e942aaadb4b` (`main` and `origin/main` at the time checked)  
**Review type:** Static code review; no application or test suite was run.

### Scope and limitations

The review inspected the API and operator routes, replay flow, ingest consumer and statistics folding, decision persistence, variant checks, infrastructure identity and role assignments, deployment topology, and related architecture and enterprise documentation. It also considered the simulator, schemas, frontend, CI, and evaluation paths.

This was a broad source review, not a line-by-line proof of every runtime path. Findings describe risks or inconsistencies visible in the reviewed source. They should be validated against intended product requirements and, for behavior-dependent items, with focused tests before being treated as reproduced defects. No builds, tests, linters, or live app checks were run for this audit.

### Resolution notes (post PR #106, same day)

**PR #106 merged at ~18:09 UTC on 2026-10-27, between the revision this review was cut from (`f75393c`) and this record.** Three findings in this review are stale as a result, and one is partially addressed by same-day documentation. The remaining findings are still accurate on the current `main`.

- **Stale: *"Placement scheduling appears to be a read-only view, not a placement scheduler"*.** PR #106 added [`services/api/api/scheduler.py`](../services/api/api/scheduler.py) with `place`, `hold_advice` and `Placement`. It assigns `t_in_ms`/`t_out_ms`, resolves collisions by taking the next clean gap, lets a goal or red card preempt the lower third, and advises a hold when the pressure trend is rising. The read-only `/schedule` view in [`services/api/api/schedule.py`](../services/api/api/schedule.py) now surfaces the scheduler's output rather than describing it.
- **Stale: *"Public replay can trigger repeated model work without effective request bounds"*.** PR #106 added [`services/api/api/guards.py`](../services/api/api/guards.py): 120 decisions and 20 overrides per minute (counting only decisions on real, open cards, so junk requests can't lock the operator out), a one-at-a-time replay with a cooldown, a replay-speed cap of 50x, and a daily model-call budget (`CRQ_DAILY_AI_MOMENTS`, default 300) that forces template-only output past the budget with a console note explaining why.
- **Stale (adjacent to the "no auth" finding): *operator overrides had no content filter beyond the AI-variant banned-topic rules*.** PR #106 added [`services/api/api/content_safety.py`](../services/api/api/content_safety.py), which checks every operator override against Azure AI Content Safety before it is recorded or aired. The banned-topic rule the AI variants follow runs first, then the Content Safety service. Violence is refused from Medium, the rest from Low. In Azure a check that cannot run refuses the override with a 424, so nothing unchecked airs.
- **Partially addressed: *"the decision log is best-effort, not a guaranteed complete audit trail"*.** Documentation now states this scope explicitly in [`docs/ENTERPRISE-OVERVIEW.md`](ENTERPRISE-OVERVIEW.md) §4 ("the audit record is durable; in-flight state is kept in the API's in-memory hub for the lifetime of a run"). The code behaviour is unchanged; durable retry/recovery and paginated history remain post-submission items.

Findings that **are still accurate on the current `main`** and are explicitly in scope for a post-submission iteration: operator authentication ([`README.md`](../README.md) Limits, [`SECURITY.md`](../SECURITY.md) §9, [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) T1), shared workload identity across the three apps, the Event Hubs producer context closure after first publish, the absence of a durable checkpoint store on the ingest consumer, variant checks that do not verify Spanish text is Spanish, and the deployed event-driven agent path (a separate `crq-moments` consumer is not deployed; the pipeline runs in-process in the API container).

### Blocking issues

- **[BLOCKING][SECURITY] Operator actions and operator WebSocket have no application authentication or authorization.** The approve, hold, override, and reject routes, as well as `/ws/operator`, do not enforce an authenticated operator identity. The request-provided `actor` is not proof of identity. The API is internally exposed behind the public web app, but that proxy does not replace route-level authorization. Wildcard CORS is also configured; CORS is not an access-control mechanism. Add authentication and role checks, derive the actor from the verified identity, and restrict CORS to intended origins. Relevant code: [`services/api/api/main.py`](../services/api/api/main.py).

- **[BLOCKING][SECURITY] Public replay can trigger repeated model work without effective request bounds.** `/matches/replay` constrains the file to the `data` directory and prevents concurrent replay, but `speed` and `decision_speed` have no maximum, `min_importance` has no range constraint, and the route has no visible caller authentication or rate limit. Repeated requests can trigger agent/model work and consume service resources. Set validated limits and appropriate authentication, throttling, and operational quotas. Relevant code: [`services/api/api/main.py`](../services/api/api/main.py).

- **[BLOCKING][SECURITY] The API, ingest, and web apps share a broadly privileged workload identity.** The Bicep assigns the same user-assigned identity to all three apps. That identity receives Event Hubs Data Owner at namespace scope and Cosmos DB Data Contributor at account scope. A compromise of any app can therefore expose data and permissions needed by the others. Split identities by service and grant only the required hub/container permissions at the narrowest supported scope. Relevant files: [`infra/modules/apps.bicep`](../infra/modules/apps.bicep) and [`infra/modules/data.bicep`](../infra/modules/data.bicep).

### Correctness and durability

- **[BLOCKING][CORRECTNESS] The Event Hubs producer is closed after its first publish.** The `publish` callback enters `async with producer` for each moment. Exiting that context closes the shared producer; a later moment publish may then fail. Such an exception is not handled as an unusable input record, so the current event may not reach the checkpoint update. Keep the producer context open around the consumer’s lifetime and add a focused test that publishes more than one moment. Relevant code: [`services/ingest/ingest/consumer.py`](../services/ingest/ingest/consumer.py).

- **[BLOCKING][CORRECTNESS] Event Hubs consumption has no durable checkpoint store configured.** The consumer starts at `starting_position="-1"` and does not pass a durable checkpoint store, although the deployment comments describe checkpointing as a prerequisite for safe scaling. After a process restart, retained events may be replayed and moments republished. Wire a durable checkpoint store and verify the intended recovery position and duplicate-handling behavior. Relevant files: [`services/ingest/ingest/consumer.py`](../services/ingest/ingest/consumer.py) and [`infra/modules/apps.bicep`](../infra/modules/apps.bicep).

- **[SUGGESTION][CORRECTNESS] Pass accuracy can remain stale for a pass without `distance_m`.** Pass and completion counters are incremented before `_rate_pass`; that function returns early when distance is missing, before recomputing `pass_accuracy_pct`. Recompute the count-based accuracy independently of distance-based quality and test a distance-less pass. Relevant code: [`services/ingest/ingest/stats.py`](../services/ingest/ingest/stats.py).

- **[SUGGESTION][DURABILITY] The decision log is best-effort, not a guaranteed complete audit trail.** Failed Cosmos writes are logged and dropped; writes can also be dropped when the queue is full or the API is shutting down. Shutdown waits only five seconds before cancelling the worker, and a history read returns at most 5,000 records. This does not support an unqualified claim that every decision is durably retained and retrievable. Decide the required audit guarantees; if loss is unacceptable, make failures visible to operators and provide durable retry/recovery and paginated history. Relevant code: [`services/api/api/decision_store.py`](../services/api/api/decision_store.py).

- **[SUGGESTION][CORRECTNESS] The Event Hubs event callback can block the async loop during match-folder initialization.** `StateFolder(meta)` is constructed directly inside the async callback, and initialization may synchronously load tracking data. Move blocking initialization off the event loop or otherwise demonstrate it is bounded and non-blocking under expected inputs. Relevant code: [`services/ingest/ingest/consumer.py`](../services/ingest/ingest/consumer.py).

- **[SUGGESTION][CORRECTNESS] The deployed event-driven agent path appears unwired.** Ingest publishes to `crq-moments`, but the inspected Bicep defines API, ingest, and web apps—not a separate agents-runner consumer. The API runs the pipeline in its in-process replay flow. If live Event Hubs moments are intended to produce proposals, the deployment currently appears to lack that consumer path. Either implement and deploy it or clearly document the live-feed path as out of scope. Relevant files: [`services/ingest/ingest/consumer.py`](../services/ingest/ingest/consumer.py), [`services/api/api/main.py`](../services/api/api/main.py), and [`infra/modules/apps.bicep`](../infra/modules/apps.bicep).

- **[SUGGESTION][CORRECTNESS] Placement scheduling appears to be a read-only view, not a placement scheduler.** The inspected scheduling path does not resolve on-air collisions or populate placement intervals; proposals without placement use an immediate-air fallback. Confirm the intended feature scope and align implementation and claims. Relevant code: [`services/api/api/schedule.py`](../services/api/api/schedule.py) and [`services/api/api/packets.py`](../services/api/api/packets.py).

- **[SUGGESTION][CORRECTNESS] In-memory API state is not recovered after an API restart.** Proposals, packets, deliveries, and current-run state are held in the API `Hub`; Cosmos persistence applies to decisions, not the entire live operator state. The current deployment is configured for one API replica, but a restart can still lose the active desk state. Document this limitation or persist and restore the state required for recovery. Relevant files: [`services/api/api/main.py`](../services/api/api/main.py) and [`services/api/api/decision_store.py`](../services/api/api/decision_store.py).

### Validation and documentation

- **[SUGGESTION][CORRECTNESS] Variant checks do not establish that Spanish text is actually Spanish.** The untranslated check rejects a base-line prefix for non-English variants, but applies a script-share check only to Hindi. It can therefore accept English paraphrases labeled Spanish. Unknown names that are not in the roster may also evade the roster-based name check. Add language-specific validation or describe these checks as limited heuristics; test both cases. Relevant code: [`services/api/api/variant_checks.py`](../services/api/api/variant_checks.py).

- **[SUGGESTION][CORRECTNESS] Architecture documentation conflicts with the inspected deployment.** The architecture describes a separately deployed agents-runner and says Bicep provisions it, while the inspected app module defines only API, ingest, and web. It also describes checkpoint-based recovery despite no durable checkpoint store being passed to the consumer. Update the documentation to match the shipped topology and recovery behavior. Relevant files: [`docs/ARCHITECTURE.md`](ARCHITECTURE.md), [`infra/modules/apps.bicep`](../infra/modules/apps.bicep), and [`services/ingest/ingest/consumer.py`](../services/ingest/ingest/consumer.py).

- **[SUGGESTION][CORRECTNESS] The operator architecture overlay appears to describe a different feed path from the current replay flow.** The overlay labels the feed as Simulator → Event Hubs → Ingest, while the reviewed replay route folds and processes the file in the API process. Make the displayed topology explicit about which path is live and which is the replay/demo path. Relevant code: [`web/src/views/Operator.tsx`](../web/src/views/Operator.tsx) and [`services/api/api/main.py`](../services/api/api/main.py).

- **[SUGGESTION][STYLE] Recheck apparent dead or experimental code before retaining it as supported functionality.** The fallback model deployment setting appears declared without being consumed by the agent-client path; `ReplayDriver` appears to have tests but no production call site; and an API module description refers to paths not present in the inspected implementation. Confirm call sites and intended future use, then remove unused code or label/document it as experimental. This is a static candidate list, not proof that the symbols are unused in every deployment path.

### Previously identified issues rechecked as fixed by inspection

The earlier halftime momentum issue appears corrected by using `play_ms` for the recent-action window. The new-match initialization path clears `match_state` before loading the new folder. These were verified by source inspection only; no regression tests were run for this audit.

### AI-assisted review attribution

This document records an AI-assisted static review using GitHub Copilot as a review aid. It does not claim that Copilot authored the project implementation, and a committed review record alone is not independent proof of IDE usage. The project team remains responsible for confirming findings, testing changes, and deciding what to disclose in the submission.

### Verdict

**REQUEST CHANGES** for a production deployment or any submission that represents operator actions as access-controlled, the decision log as complete, or Event Hubs recovery/live agent processing as implemented. For a hackathon demo, clearly label these as limitations and validate the submission claims against the actual deployed path.
