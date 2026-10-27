# ADR-004: Azure Container Apps over AKS for the build week

Decision: Container Apps (consumption) with KEDA scaling on Event Hubs lag; simulator as an ACA job.
Why: `azd up` provisions and deploys in one command; event-driven scaling is native; AKS would cost
a day of setup the team does not have.
Status (Oct 27): KEDA scaling is not built. Each app runs a fixed replica count, and ingest stays at one
replica until the consumer has a checkpoint store (`infra/modules/apps.bicep`).
Consequences: the Cloud Native category story is Container Apps + Event Hubs + Cosmos (plus Azure AI
Content Safety on operator overrides and an Application Insights availability test, both added later),
not Kubernetes; an AKS variant could be added after the hackathon. The Logic App for the 20-second SLA
hold is deferred — the hold runs as an in-process `asyncio` timer in both environments.

Update (2026-10-27, post PR #106): three controls previously flagged as missing on this ADR's path have
landed on the API side without changing the Container Apps / scaling decision:

- `services/api/api/scheduler.py` places every graphic (collisions, next-gap, preempt-on-goal-or-red-card,
  hold-when-pressure-is-rising); the earlier "scheduler is not built" caveat on `/schedule` no longer
  applies.
- `services/api/api/guards.py` adds per-minute rate limits on operator decisions and overrides, a
  one-at-a-time replay with a cooldown, a replay-speed cap of 50x, and a daily model-call budget
  (`CRQ_DAILY_AI_MOMENTS`, default 300) that falls back to templates when exceeded.
- `services/api/api/content_safety.py` checks every operator override against Azure AI Content Safety
  before it is recorded or aired; 424 when the service can't be reached, so nothing unchecked airs.

KEDA scaling and a durable checkpoint store for the ingest consumer remain the two Container-Apps-shaped
items reserved for a post-submission iteration; both are referenced in `infra/modules/apps.bicep` and in
`services/ingest/ingest/consumer.py`.
