# Operational runbook

One page for the on-call responder. If you have ten seconds, the whole system has three failure modes:
Foundry doesn't answer, the API container falls over, or the demo URL goes dark. All three recover
without touching data because the demo runs on synthetic events and the audit trail is in Cosmos DB.

## Services and where to look

| Service | Role | Health probe |
| --- | --- | --- |
| `ca-crq-api-poc-eastus2-01` | FastAPI, runs the whole pipeline in-process (simulator → stats → agents → proposals → approvals → overlay feed) | `GET /healthz` (internal only; the API has `ingress.external: false`) |
| `ca-crq-web-poc-eastus2-01` | nginx reverse-proxy and the React SPA; the one public ingress | `GET /` returns the SPA shell |
| `ca-crq-ingest-poc-eastus2-01` | Event Hubs → stats engine fold (used in Azure mode; currently fixed one replica with no scaling) | No ingress; check container logs |
| `cosmos-crq-poc-eastus2-01` | `decisions` container is written to on every operator action (PR #100) | Azure portal → Cosmos data explorer, container `decisions` |
| `evhns-crq-poc-eastus2-01` | `match-events` (sim → ingest), `crq-overlay` (packet feed) | Azure portal → Event Hubs → incoming messages |
| `aif-crq-poc-eastus2-01` | Foundry account; three router deployments (`router-quality`, `router-balanced`, `router-cost`) plus `gpt-4.1-mini` fallback | Portal → Foundry project → Deployments → request counts |

## Normal operations

### Starting the reference replay

```powershell
$BASE = "https://ca-crq-web-poc-eastus2-01.wittyground-1f27f60c.eastus2.azurecontainerapps.io"
Invoke-RestMethod -Method Post -Uri "$BASE/matches/replay" -ContentType "application/json" `
  -Body '{"file":"data/reference/match-042.jsonl","speed":1,"from_play_ms":2460000}'
```

The payload says: *reference match*, *real-time speed*, *from minute 41 (play_ms 2 460 000)*. For a fuller run,
set `from_play_ms:0`; for a condensed walkthrough, `speed:5`.

### Reading `/metrics`

```powershell
Invoke-RestMethod "$BASE/metrics" | ConvertTo-Json -Depth 5
```

What matters:

- `turnaround.median_s` under 20 means Foundry is answering; over 25 means timeouts are pushing proposals
  to the template fallback.
- `errors.fallback_proposals` growing means Foundry is failing agent calls (quota, auth, model router);
  check the Foundry portal.
- `errors.check_failures.*` non-zero means variant checks are rejecting agent output; usually a numbers
  drift. Not an incident; the console shows the amber chip and the operator either overrides or holds.
- `workload.sla_holds` climbing with `operator_decisions` flat means nobody is driving the desk.

### Downloading the decision log

```powershell
Invoke-WebRequest "$BASE/decisions.csv" -OutFile decisions.csv
```

Reads from Cosmos DB (persisted) with a fallback to in-memory for the current run. If the file is empty,
Cosmos credentials or RBAC are not landing on the API's managed identity — check `COSMOS_ENDPOINT` env var
and the `Cosmos DB Built-in Data Contributor` role assignment in `infra/modules/data.bicep`.

## Incident playbooks

### Foundry quota or model router outage

Signal: `fallback_proposals` climbs; `median_s` jumps to the agent timeout (12 s); every lineage chip on
`/operator-demo` greys out.

Response:

1. Verify Foundry portal → Deployments. If a router shows 0 TPM, raise the quota or wait it out.
2. The demo keeps running: every agent has a deterministic template fallback and the "degrade, never stall"
   principle keeps proposals arriving. The video's resilience beat is this exact state.
3. To record locally without Foundry: set `CRQ_OFFLINE=1` in the API container's env or in `.env` and restart.

### API container crash

Signal: `/metrics` returns 502 from nginx; browser shows "API unreachable" overlay.

Response:

1. Container Apps revisions auto-restart. If `az containerapp show` shows the revision stuck, force a
   restart: `az containerapp revision restart --name ca-crq-api-poc-eastus2-01 --resource-group crq-rg-poc-eastus2-01 --revision <active-revision>`.
2. State loss: in-flight proposals, packets and in-progress agent runs are lost; **every decision ever
   written survives in Cosmos DB** (per the scope line in [ENTERPRISE-OVERVIEW.md §4](ENTERPRISE-OVERVIEW.md#4-full-audit-trail)).
3. The replay must be restarted (POST `/matches/replay`); the Cosmos decisions container is not read back.

### Demo URL dark

Signal: the public hostname 503s or times out.

Response:

1. `az containerapp show --name ca-crq-web-poc-eastus2-01 --resource-group crq-rg-poc-eastus2-01` to check revision health.
2. If the environment is up but revisions are failing, roll back: `az containerapp revision set-mode --mode Single --name ca-crq-web-poc-eastus2-01 --resource-group crq-rg-poc-eastus2-01` then activate a known-good revision.
3. **Offline fallback for judging:** record the walkthrough locally with `CRQ_OFFLINE=1` and link to the
   recording. ADR-13 treats offline mode as a first-class path for exactly this reason.

### Someone trolls the public operator endpoint during judging

Signal: unexpected `/decisions.csv` entries; `operator_decisions` climbing without you.

Response:

1. Container Apps revision restart clears in-memory state. The audit trail stays in Cosmos.
2. Pre-authored rate limiting is not in this build (see `SECURITY.md` deferred list). The practical
   mitigation is restart-plus-watch; durations of actual judging are short enough that one restart suffices.

## Keys and secrets

There are none to rotate. Every workload calls Azure data planes with its managed identity; GitHub Actions
authenticates to Azure via OIDC with `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` repository
variables (**not** secrets). `.env.example` is a checklist; the committed Bicep deploys everything that
needs an endpoint. If a credential ever shows up anywhere in the repo, that is the incident; `trufflehog`
runs in CI (`.github/workflows/trivy.yml`).

See [SECURITY.md](../SECURITY.md) for the full posture and the "What is deferred" section for post-submission
hardening (private endpoints, Entra ID sign-in, Logic App for the SLA).
