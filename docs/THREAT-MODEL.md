# Threat model

One page. STRIDE-adjacent; honest about what the current build mitigates structurally, what it mitigates
procedurally, and what is deferred to a post-submission iteration. All match data is synthetic; the deployment
is a POC resource group (`crq-rg-poc-eastus2-01`); nothing here holds PII.

## Trust boundaries

Three layers, each enforced in code (see the diagram at the top of [SECURITY.md](../SECURITY.md#the-trust-boundary-at-a-glance)):

1. **Schema** — Pydantic refuses to construct an `OverlayPacket` without `approval_id / approved_by / approved_at`.
2. **Builder** — `services/api/api/packets.py` only builds packets from a logged decision.
3. **Renderer** — refuses any packet missing the triple and logs the refusal.

The gate holds even if the layers above it were bypassed. Everything below is in-depth defense around that gate.

## Threats, mitigations and residuals

| # | Threat | Vector | Mitigation (today) | Residual (deferred) |
| --- | --- | --- | --- | --- |
| T1 | **Unauthenticated operator fires a graphic** | The API's decision endpoints have no auth; `actor` is a request field | API has `ingress.external: false`; only the nginx web container is on the public internet, and it proxies only the specific routes needed. The public demo endpoint is restarted-and-watch during judging. Every decision writes an audit row (actor, timestamp) to Cosmos | **Entra ID sign-in with roles for approve / override; actor derived from the verified token.** Named as the stated next step in README limits and SECURITY.md |
| T2 | **Prompt injection via the event feed** | Attacker-controlled event text influences agent output | **Numbers from code, words from models**: `variant_checks.py` rejects variants with invented numbers, name drift, cites outside the moment, banned content (referee / betting / injury), under-length Devanagari for Hindi, faithfulness < 0.8; the template fallback is used when a check fails | A dedicated Azure AI Content Safety resource; current content filtering is the Foundry deployment defaults. |
| T3 | **Model outage** | Foundry quota, model router failure, agent timeout | Every agent has a 12 s timeout and a deterministic template fallback; `/metrics` reports `fallback_proposals` so the operator sees degradation; the UI shows the greyed lineage with the fallback note; the deployed demo keeps running | — (acceptable) |
| T4 | **Data exfiltration** | Attacker reads sensitive data from the running system | Synthetic data only — fictional clubs, players, venues; no PII; no customer data; no real match data | — (acceptable while the data posture stays synthetic) |
| T5 | **Public URL abuse during judging** | Someone POSTs to the operator endpoints while judges are watching | Rate limits in the API far above a person's pace, counted only on real, open cards (120 decisions and 20 overrides a minute; one replay at a time, at most 50x, 5 s apart); a daily model budget that falls back to templates (`CRQ_DAILY_AI_MOMENTS`); the audit log in Cosmos captures every write; a revision restart clears in-memory state; synthetic data means no sensitive leakage | **Per-client limits at the edge (Front Door with WAF); per-session tokens.** Post-submission |
| T6 | **Supply chain compromise** | Compromised dependency or GitHub action | Every GitHub action pinned to a full commit SHA (not a tag) with the March 2026 trivy-action CVE-2026-33634 incident cited in the workflow header. CodeQL on Python / TypeScript / workflow files, Trivy on dependencies / secrets / Dockerfiles / Bicep-compiled ARM / three container images, Dependabot on actions and dependencies. Tool versions pinned (`TRIVY_VERSION`, `BICEP_VERSION`) | Reproducible builds (hash-locked lockfiles present, but no SBOM yet). SBOM generation is a post-submission iteration |
| T7 | **Decision log tampering** | Attacker modifies the audit trail | Decisions go to an **append-only** Cosmos DB container (PR #100) with `create_item` and idempotent IDs; CSV export at `/decisions.csv` protects spreadsheet formula injection on write; the Cosmos container is RBAC-scoped to the workload identity with `Cosmos DB Built-in Data Contributor` (write-only append pattern) | A separate reader role for audit downloads; append-only is enforced by application logic, not by Cosmos policy (`collectionDeleteRetention` could be a future hardening) |
| T8 | **Credential theft** | Attacker exfiltrates a secret from the repo, CI or a running container | **No keys to steal.** `disableLocalAuth: true` on Cosmos DB, Event Hubs, Foundry; `allowSharedKeyAccess: false` on Storage; `adminUserEnabled: false` on ACR. Every data-plane call requires an Entra ID principal with the matching RBAC role, held by the workload managed identity. GitHub Actions uses OIDC federation (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as **repository variables**, not secrets) | — (acceptable) |
| T9 | **Network path to data services** | Attacker reaches Cosmos / Event Hubs / Foundry from the open internet | Access requires Entra ID + the specific RBAC role; no local-auth path exists; TLS 1.2 minimum on every data service | **Private endpoints on Cosmos, Event Hubs and Foundry with `publicNetworkAccess: 'Disabled'`; VNet integration on the Container Apps managed environment.** Required for a production deployment with real viewer data; explicitly deferred in SECURITY.md §9 |
| T10 | **Replay drift / state corruption during a run** | A race or crash leaves the hub partially populated | `new_match` clears every collection AND clears `match_state` early (fixed in commit `3fb89e2`); `/recap` guards against null state; the SLA timer never approves; decisions are append-only to Cosmos | — (acceptable) |
| T11 | **Reader of generated content sees unsafe output** | A content-safety edge the Foundry filter missed, or an operator's override | Variant checks block referee / betting / injury topics (EN / ES / HI regexes); Devanagari share check prevents un-translated Hindi; faithfulness < 0.8 → template fallback. **Every override line** passes the same topic rule and Azure AI Content Safety on the Foundry account before it is recorded or aired (hate, sexual, self-harm from Low; violence from Medium), and is refused if the check can't run | Content Safety on the AI-written lines too, with thresholds tuned per category |

## Residuals summary (what judges should know)

Three items are explicitly deferred:

1. **Operator authentication (T1).** The current build has no sign-in. Judges testing the live demo can
   make decisions as any `actor` string. The architecture is ready for Entra ID; the implementation is a
   post-submission sprint. Named in [README limits](../README.md#limits) and
   [SECURITY.md §9](../SECURITY.md#9-deployment-posture).
2. **Private networking (T9).** The data tier is reachable from the public internet with Entra ID auth
   only. For a production deployment with real viewer data, private endpoints are mandatory and the Bicep
   module gap is a configuration change on the same resources, not a rewrite.
3. **Rate limiting at the edge (T5).** The API limits in total (it can't reliably tell clients apart
   behind the proxy), and a daily model budget bounds cost. A production ingress would add per-client limits
   behind Azure Front Door with WAF rules.

Everything else is either structurally mitigated by the code we ship today or carried as an operational
procedure (restart, offline mode, audit review).

## Where this fits

- Trust boundary and gate: [SECURITY.md §Trust boundary](../SECURITY.md#the-trust-boundary-at-a-glance)
- Full security posture: [SECURITY.md](../SECURITY.md)
- Deployment posture (public, Entra ID RBAC, no local auth): [SECURITY.md §9](../SECURITY.md#9-deployment-posture)
- Enterprise claim with code evidence: [ENTERPRISE-OVERVIEW.md](ENTERPRISE-OVERVIEW.md)
- Operational response: [RUNBOOK.md](RUNBOOK.md)
