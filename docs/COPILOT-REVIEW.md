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
