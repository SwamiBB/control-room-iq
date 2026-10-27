# Control Room IQ — Architecture Review

**Review date:** 2026-10-27  
**Review type:** Static architecture review  
**Scope:** Architecture and end-to-end design documents, ADRs, threat model, API routes, and Azure Bicep deployment.

## Scope and limitations

This review examined the architecture described in `docs/ARCHITECTURE.md`, `docs/ARCHITECTURE.md`, `docs/THREAT-MODEL.md`, and `docs/adr/`, then compared key claims with the inspected API and infrastructure source.

No application, test suite, build, linter, or live deployment was run. Findings are based on source and documentation inspection; runtime impact should be verified with focused tests and deployment checks. This is an AI-assisted review record, not a substitute for security approval or engineering validation.

## Resolution notes (post PR #106, same day)

**PR #106 merged at ~18:09 UTC on 2026-10-27, between the revision this review was cut from and this record.** Three items in this review are stale as a result. The remaining items are accurate on the current `main` and are explicitly in scope for a post-submission iteration.

- **Stale in "API contract assessment": *"the reviewed materials do not define a rate-limiting policy for replay or operator actions."*** PR #106 added [`services/api/api/guards.py`](../services/api/api/guards.py): 120 decisions and 20 overrides per minute, a one-at-a-time replay with a cooldown, a replay-speed cap of 50x, and a daily model-call budget (`CRQ_DAILY_AI_MOMENTS`, default 300) that falls back to templates past the budget.
- **Stale in "Technology selection": *the scheduler and content-filter concerns are now addressed.*** [`services/api/api/scheduler.py`](../services/api/api/scheduler.py) resolves on-air collisions, assigns `t_in_ms`/`t_out_ms`, preempts the lower third on a goal or red card, and advises a hold when pressure is rising. [`services/api/api/content_safety.py`](../services/api/api/content_safety.py) checks every operator override against Azure AI Content Safety before it is recorded or aired (424 when the check cannot run). Both are reflected in the Enterprise controls block of [`README.md`](../README.md) and in [`docs/ENTERPRISE-OVERVIEW.md`](ENTERPRISE-OVERVIEW.md).
- **Partially addressed in "Data model assessment": *decision-log durability scope is now documented.*** [`docs/ENTERPRISE-OVERVIEW.md`](ENTERPRISE-OVERVIEW.md) §4 states that the audit record is durable, while in-flight state (proposals, packets, in-progress agent runs) is in-memory for the lifetime of a run. The code behaviour is unchanged; durable retry/recovery and paginated history remain post-submission items.

Findings that **are still accurate on the current `main`**: operator-route authentication, shared workload identity across the three apps, API versioning prefix, standardized ProblemDetails-style error responses, pagination on history endpoints, Event Hubs recovery via durable checkpoints, event-driven agent processing as a separately deployed consumer, and the ADR hygiene gaps (ADR-004 noting KEDA deferred is accurate; the deeper reconciliation and the new ADRs on authentication, service identities and persistence are tracked for a post-submission iteration).

## ADR assessment

**NEEDS REVISION** — The ADRs record important choices, but do not consistently meet the repository's ADR standard: they lack dates, status, deciders, complete context, alternatives considered, and explicit risks.

- [ADR-004 — Container Apps over AKS](adr/ADR-004-container-apps.md) selects KEDA scaling, while noting it is not built.
- [ADR-003 — Model router](adr/ADR-003-model-router.md) has an earlier decision statement that conflicts with its later update.
- [ADR-001 — Python with Microsoft Agent Framework](adr/ADR-001-python-agent-framework.md) and [ADR-002 — Synthetic data](adr/ADR-002-synthetic-data.md) are brief decision summaries rather than complete records.

**Review comment:** Reconcile each ADR with the deployed design, then record its current status, alternatives, consequences, and risks. Add or update ADRs for the authentication model, service identities and permissions, persistence and recovery, and event-driven versus in-process processing.

## API contract assessment

**NEEDS REVISION** — The inspected API routes do not show several contract controls expected before production use:

- Routes are not under a versioned prefix such as `/api/v1/`.
- Operator routes lack authentication and authorization; a request-supplied actor value does not establish identity.
- The reviewed materials do not define a rate-limiting policy for replay or operator actions.
- Collection endpoints need an explicit pagination policy before histories grow.
- Standardized ProblemDetails-style error responses and consumer contract tests are not evidenced in the reviewed materials.
- Wildcard CORS does not protect operator routes or establish caller identity.

**Review comment:** Document the authentication scheme, authorization roles, error shape, pagination, throttling, and breaking-change policy. Add contract tests for the web console, renderer, and external consumers.

## Data model assessment

**NEEDS REVISION** — Cosmos DB partitioning by `/match_id` and synthetic-only data are reasonable for the current single-tenant demo, but the reviewed design does not establish tenant isolation or a production migration and retention strategy.

- No tenant identifier appears in the described partition key or access model. Do not treat `match_id` alone as tenant isolation if multiple organizations are introduced.
- Active proposals, packets, deliveries, and other run state are held in API process memory; a restart can lose active state even though decisions are persisted.
- Decision persistence is best-effort: failed or overflowing writes are logged and dropped, shutdown waits only briefly, and history is capped. This conflicts with unqualified “full audit trail” language.
- The reviewed docs do not define schema evolution, migration rollback, or data deletion and retention procedures beyond sandbox lifetime.

**Review comment:** Keep the single-tenant and synthetic-data limitations explicit. Before multi-tenant or production data, define tenant-scoped authorization and partitioning, recovery behavior, retention and deletion, and reversible schema migration practices.

## Technology selection

**CONDITIONAL** — Container Apps, Event Hubs, Cosmos DB, managed identity, and Foundry are coherent choices for a hackathon proof of concept. However, the documented event-driven architecture and inspected deployment do not line up:

- The architecture describes a separate `agents-runner`, while the inspected app deployment defines API, ingest, and web apps.
- The API runs the replay pipeline in-process.
- The Event Hubs consumer does not configure a durable checkpoint store.
- The shared Event Hubs producer is entered in a context manager for each publish. Exiting that context closes the producer, so subsequent publishes may fail.

**Review comment:** Present the deployed replay path and planned streaming path as distinct. Do not claim resilient restart/recovery or live agent processing until those paths are implemented and verified.

## Key review comments

1. **High — Secure operator actions before representing the system as access-controlled.** The approval gate proves a packet has approval fields; it does not prove that the caller approving it is authorized. Add authentication, role checks, and identity-derived audit actors. This is the primary blocker for a public operator deployment.
2. **High — Split workload identities and reduce permissions.** API, ingest, and web share one identity; it receives Event Hubs Data Owner at namespace scope and Cosmos DB Data Contributor at account scope. Use separate identities and least-privilege scopes so compromise of one service does not grant broad access to the others.
3. **High — Make Event Hubs publishing and recovery reliable.** Keep the producer open for the consumer lifetime, configure durable checkpoints, and test multiple moment publications plus restart/replay behavior.
4. **Medium — Make audit guarantees match implementation.** Either provide durable retry/recovery, visible failure handling, and paginated history, or describe the decision log as best-effort rather than complete.
5. **Medium — Define the scaling boundary.** API run state is in-process, while the architecture discusses multiple API replicas. Scaling or restarting without shared state and connection-aware routing can produce inconsistent operator and viewer experiences.
6. **Medium — Align architecture documentation with deployed resources.** Update [ARCHITECTURE.md](ARCHITECTURE.md) and [ARCHITECTURE.md](ARCHITECTURE.md) to distinguish implemented, deferred, and target components—especially the agent runner, scheduler, and checkpoint-based recovery.

## STRIDE summary

| Threat | Finding | Severity | Mitigation |
|---|---|---|---|
| Spoofing | Operator routes and operator WebSocket do not establish an authenticated operator identity; request-supplied actor values are untrusted. | High | Require Entra ID authentication and role authorization; derive the audit actor from verified claims. |
| Tampering | Broad shared service permissions increase the impact of a compromised app; event recovery and duplicate handling are not clearly guaranteed. | High | Split identities and scope roles; configure durable checkpoints and idempotent event handling. |
| Repudiation | Decision writes can be dropped on Cosmos failures, queue overflow, or shutdown; the audit record may therefore be incomplete. | High | Provide durable retry/recovery and operator-visible persistence failures, or clearly limit the audit guarantee. |
| Information disclosure | Data is synthetic today, but public operator/viewer paths and broad shared identity permissions increase exposure if real data is introduced. | Medium | Keep synthetic-only restrictions explicit; add authorization and private networking before using real viewer or customer data. |
| Denial of service | Replay triggers pipeline/model work; reviewed request fields lack clear upper bounds and no rate-limit strategy is documented. | High | Validate strict bounds, authenticate where appropriate, and apply per-caller throttling and workload quotas. |
| Elevation of privilege | A compromised web, ingest, or API app inherits the same broad Event Hubs and Cosmos permissions. | High | Assign per-service identities and least-privilege data-plane roles. |

These findings should be tracked as security work before production use. No ADO work items were created as part of this review.

## Verdict

**ESCALATE TO SECURITY** — The public operator path lacks authentication and the shared identity has broad privileges. For a hackathon-only synthetic-data demo, those limitations may be explicitly disclosed. Do not describe the architecture as production-ready or its audit trail as complete and guaranteed until the findings above are addressed.

## AI-assisted review attribution

This document records an AI-assisted static architecture review using GitHub Copilot as a review aid. It does not claim that Copilot authored the project implementation. A committed review record alone is not independent proof of IDE usage; the project team is responsible for validating findings and deciding what to disclose in the submission.
