# Evidence: the deployed environment, as queried

Read on **2026-10-27 (UTC)** from the live Azure deployment and its telemetry, with read-only commands. Resource
names, IDs and hostnames are left out on purpose: the repository is public. Each section says how it was read, so
anyone with access to an environment deployed from this repository can repeat it.

## 1. What is deployed

`az resource list -g <resource group>`, grouped by type:

| Count | Resource type | Kind |
| --- | --- | --- |
| 3 | Container Apps (`api`, `web`, `ingest`) | |
| 1 | Container Apps environment | |
| 1 | Foundry account (`Microsoft.CognitiveServices/accounts`) with one project | AIServices |
| 1 | Speech account | SpeechServices |
| 1 | Azure Cosmos DB account | GlobalDocumentDB |
| 1 | Event Hubs namespace | |
| 1 | Container registry | |
| 1 | Storage account | StorageV2 |
| 1 | Application Insights, on a Log Analytics workspace | web |
| 1 | User-assigned managed identity (the workload identity) | |

## 2. No keys anywhere

Each service's own `show` command:

| Service | Setting | Value |
| --- | --- | --- |
| Azure Cosmos DB | `disableLocalAuth` | `true` |
| Event Hubs | `disableLocalAuth` | `true` |
| Application Insights | `DisableLocalAuth` | `true` (telemetry is accepted with Entra ID only) |
| Foundry account | `disableLocalAuth` | `true` |
| Storage | `allowSharedKeyAccess` | `false` |
| Storage | `requireInfrastructureEncryption` / `minimumTlsVersion` | `true` / `TLS1_2` |
| Container registry | `adminUserEnabled` | `false` |

## 3. Network shape

`az containerapp list`:

| App | Public ingress | Identity | Replicas |
| --- | --- | --- | --- |
| `web` (nginx) | **yes**: the only public entry point | user-assigned | 1–2 |
| `api` | **no**: internal to the environment, reached only through nginx | user-assigned | 1 |
| `ingest` | **none** | user-assigned | 1 |

## 4. What the workload identity may do

`az role assignment list --assignee <workload identity>` (Azure RBAC; Cosmos DB's data-plane role is a separate
Cosmos SQL role assignment, defined in `infra/modules/data.bicep`):

| Role | Scope |
| --- | --- |
| AcrPull | the container registry |
| Foundry User | the Foundry account (models, and Content Safety for operator overrides) |
| Cognitive Services Speech User | the Speech account |
| Azure Event Hubs Data Owner | the Event Hubs namespace |
| Storage Blob Data Contributor | the storage account |
| Monitoring Metrics Publisher | Application Insights (sending traces with Entra ID) |

Every role is assigned by Bicep (`infra/`), none by hand.

## 5. Models

`az cognitiveservices account deployment list`:

| Deployment | Model | SKU | Capacity (K tokens/min) | Content filter |
| --- | --- | --- | --- | --- |
| `router-quality` | model-router | GlobalStandard | 100 | Microsoft.DefaultV2 |
| `router-balanced` | model-router | GlobalStandard | 100 | Microsoft.DefaultV2 |
| `router-cost` | model-router | GlobalStandard | 100 | Microsoft.DefaultV2 |
| `gpt-4.1-mini` | gpt-4.1-mini | GlobalStandard | 100 | Microsoft.DefaultV2 (fallback and evaluation judge) |

Each router has its routing mode set in `infra/modules/ai.bicep`; the agents' mapping is in
`services/agents/agents/config.py` (`AGENT_ROUTING`).

**Live portal view.** The Foundry portal's *Models → Deployments* page for this project
([`foundry-models-deployments-2026-10-27.png`](foundry-models-deployments-2026-10-27.png)) shows the
same four deployments at *Succeeded*, their SKU and version, and the right-panel *Call this model*
sample code that uses `DefaultAzureCredential` with the panel confirming *API Key authentication is
disabled* — the key-less Entra ID path that §2 and §4 describe for all data planes.

## 6. What the agents did: 24 hours of traces

Log Analytics over the Application Insights the apps send to (KQL over `AppDependencies`, the spans named in
`SECURITY.md` §6). Every run in these 24 hours was a replay of the synthetic reference match.

**Per agent:**

| Agent span | Routing mode | Calls | Failed calls |
| --- | --- | --- | --- |
| `crq.agent explainer` | quality | 69 | 0 |
| `crq.agent narrator` | balanced | 70 | 0 |
| `crq.agent producer` | quality | 44 | 0 |
| `crq.agent personalizer` | cost | 40 | 0 |
| `crq.agent localizer` | cost | 39 | 0 |

**The model each router chose** (`crq.model_served`, recorded on every agent span):

| Model served | Calls |
| --- | --- |
| gpt-5.6-luna | 120 |
| gpt-5.5 | 69 |
| gpt-5.6-terra | 31 |
| gpt-5.6-sol | 26 |
| gpt-6-astra | 16 |

**Per moment** (`crq.moment`, one trace each): 69 moments, 33 of them with a card proposed to the operator.

**Live view, same project.** The Application Insights *Agents (Preview)* dashboard
([`application-insights-agents-dashboard-2026-10-27.png`](application-insights-agents-dashboard-2026-10-27.png))
shows per-agent run counts, the three model-router deployments (`router-quality`, `router-balanced`,
`router-cost`), token consumption and a Traces panel listing `invoke_agent` dependencies on the
`crq.moment` span — the same shape the KQL above returns. The visible run counts are smaller than this
section's table because they are over a shorter window.

## 7. Supply chain

`gh run list --branch main`: CodeQL and Trivy succeed on every push to `main`. The CI job's status is in the
repository's Actions tab.

## 8. Agents (live portal view)

The Foundry portal's *Agents* tab for this project
([`foundry-agents-tab-2026-10-27.png`](foundry-agents-tab-2026-10-27.png)) shows the five agents the
`python -m agents.register_agents` script registers (`crq-narrator`, `crq-producer`, `crq-explainer`,
`crq-localizer`, `crq-personalizer`), all at *Status: Running*, version 2, type *Prompt*, interaction
type *Text*, last updated 2026-10-27. The *Description* column matches the per-agent docstrings in
`services/agents/agents/agent_catalog.py`.

## 9. Evaluation (live portal view)

The Foundry portal's *Evaluations* tab for this project
([`foundry-evaluation-crq-eval-2026-10-26.png`](foundry-evaluation-crq-eval-2026-10-26.png)) shows one
completed run, `crq-eval-2026-10-26`, with these headline numbers:

| Metric | Score |
| --- | --- |
| Overall | 89% |
| Groundedness | 72% (43 / 60) |
| Relevance | 100% (60 / 60) |
| Coherence | 100% (60 / 60) |
| Fluency | 78% (47 / 60) |
| Violence (safety) | 95% (57 / 60) |

**Dataset = *Inline data*.** The portal reports what the code does: `evals/run_eval.py` runs the live
agents against the synthetic reference match (`data/reference/match-042.jsonl`) and submits rows to
Foundry evaluators inline — there is no `evals/datasets/` folder, and planted-falsehood probes are built
inline in the runner. Scores and the full breakdown are reported honestly in
[`evals/results/latest.md`](../../evals/results/latest.md); the numbers above are from one run of the
runner and are not a certification.
