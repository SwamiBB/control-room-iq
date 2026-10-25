## Agents work: Siranjeevi's consolidated list

Last updated: Monday, October 26, 2026. Checked against `main` at `bcc3f37` (#58), plus #60 (open). First
written on Friday, October 23 by merging Siranjeevi's own list with the agent items from `CHANGES-2026-10-23.md`,
`HANDOFF-2026-10-23-agents-web.md` and `HANDOFF-2026-10-24-match-intelligence.md`. Items 1, 4 and 5 are done;
3 is partly done; 2 and 6 are not started. Since Oct 25 Siranjeevi also owns the Azure and API hosting work
(see the last section).

| # | Task | Status | Why it is next |
| --- | --- | --- | --- |
| 1 | ✅ **Fix #9:** the API crashes on startup in Azure (`clients.py`), plus a test that builds the pipeline in online mode | Done in #26 | About 30 minutes. Blocks deploying the API and checking the live models |
| 2 | **`scheduler.py`** with tests | Does not exist | A Friday must-have, now overdue. Until it lands, a fired graphic airs at once, unscheduled |
| 3 | **Router clients per agent** with `model_served` | Partly done: the client works on `model-router` and records `model_served` (#26); per-agent clients not wired | Needs the three router deployments (#47). Until then everything uses `model-router`, which is behind the timeouts in #39 |
| 4 | ✅ **#10:** check the agents get real replies from the live `model-router` | Done Oct 25: all five agents answer live, 0 failures (fixed in #26) | First real test against Azure |
| 5 | ✅ **Localizer agent**, **personalizer prompt** and the **fallback bug** (#17) | Merged in #27; the `CRQ_LANGS` part of #17 is in #26 | Decided Oct 24: five agents, with Spanish and Hindi from a dedicated Localizer |
| 6 | **`register_agents.py`** for the **five** agents (Saturday), **evaluations** and the README table (Monday) | Do not exist | Saturday and Monday deliverables |

### Details

**1. ✅ Fix #9 (`services/agents/agents/clients.py`)**
- The client is built once at import time for every agent (`lru_cache`), so a bad endpoint, a missing
  credential or a constructor change in `agent-framework` stops the whole API from starting.
- ✅ Make startup survive a client failure: log it and let each agent fall back to its template, so the API
  still serves the console.
- ✅ Add a test that builds `MomentPipeline` with `CRQ_OFFLINE=0` and a stubbed client, so a constructor or
  import error fails CI instead of the Azure deploy.

**2. `scheduler.py` (pure code, unit tests with hand-built on-air lists)**
- `schedule(proposal, on_air, state) -> proposal`, run in `workflow.py` after the producer.
- No collisions per layer; earliest free gap; one story per 30 s window; a goal or red card preempts the
  lower third (`replaces`); respect `min_hold_ms` and per-kind `max_delay_ms`; set `t_in_ms` / `t_out_ms`
  (the API already treats `t_out_ms > t_in_ms` as "placed by the scheduler").
- `hold_advice` when `pressure_trend == "rising"` and the proposal is not a goal. Nothing computes it today.
- **Already done in the API, do not rebuild:** the 20 s auto-hold, the 10 s warning and expiry of stale held
  graphics (`api/timing.py`), and the goal routine's three items (`api/goal_package.py`). The scheduler should
  place the goal routine's follow-ups after the lead, using their `package_offset_ms`.
- Layers to expect: speed moments now use the **lower third** (not the player tag); standout passes the stat panel.
- ✅ Done elsewhere, do not rebuild: **supersession** (a goal takes over the pending cards of its move) is in the
  API (#60), and the producer's slot length is capped per layer (#60).

**3. Router clients (`clients.py`, `config.py`)**
- One client per router deployment: explainer and producer → `ROUTER_QUALITY`, narrator → `ROUTER_BALANCED`,
  personalizer and localizer → `ROUTER_COST`. `agents/config.py` now has `AGENT_ROUTING` and `deployment_for(agent)`,
  which falls back to `MODEL_ROUTER_DEPLOYMENT`; `make_agent` should build each agent's client from it.
- ✅ The model client itself works against `model-router`: it uses `OpenAIChatCompletionClient`, because the
  router rejects the Responses API (#10, in #26). Code also records `model_served`, `latency_ms` and routing `balanced` on every model-written
  output (#26). Still to do: per-deployment clients and per-agent routing.
- Read `response.model` into `meta.model_served` and `meta.routing` on each output; span attributes
  `crq.agent`, `crq.routing`, `crq.model_served`. The README promises "the model that served each call is
  recorded".
- The three deployments in `infra/modules/ai.bicep` and the `ROUTER_*` settings in `apps.bicep` are #47; removing
  the Speech resource is #48. Both moved from Swami to Siranjeevi on Oct 25.

**4. ✅ #10 live check**
- ✅ Foundry User role assigned; live run on Oct 25 with every agent model-written (the router
  served large models such as `grok-4-1-fast-reasoning` and `gpt-5.6-terra`). Timing is in #39.
- After 1 and the Foundry User role: run the reference match with `CRQ_OFFLINE=0`, confirm every agent
  returns a model reply (not a fallback), and note the served models for the README.

**5. ✅ Localizer, personalizer prompt and fallback (merged in #27)**
- New **Localizer** agent (`prompts/localizer.md`, `router-cost`): renders the personalizer's English versions
  into Spanish and Hindi in one call, keeping numbers, units and names exactly. Code keeps only the requested
  targets, copies the English version's cites and drops anything labeled English (`keep_localized`).
- `prompts/personalizer.md` rewritten: English only; personas newcomer, fan, analyst; `deaf` is an access
  setting; the old `accessibility` persona and Arabic are gone; the match-intelligence rules stay.
- `fallback_variants` (#17): English only. Offline or on a localizer failure, Spanish and Hindi viewers get the
  API's template line, never English labeled as their language.
- The unused squad-author prompt is removed. Tests: `services/agents/tests/test_localizer.py`.
- **`fan_card`: no longer needed from the agents.** The API builds the deaf fan's card in code
  (`api/fan_card.py`, on `main` (#23)). If the workflow ever builds one, the API
  uses it instead.

**6. `register_agents.py` and evaluations**
- `register_agents.py`: create or update the five agents by name (explainer, narrator, producer, personalizer,
  localizer) in Foundry Agent Service
  (`azure-ai-projects`), so they are inspectable in the portal; the runner still executes them locally.
- `evals/run_eval.py`: replay the reference match offline, submit a Foundry evaluation run (groundedness,
  relevance, fluency per language), run the planted-falsehood set (Pranav's `evals/datasets/`), write
  `evals/results/latest.md` for the README table. Optional nightly `.github/workflows/evals.yml`.

### Also on Siranjeevi (not code)

- Bring the Azure resources up and deploy from CI with Swami (first `azd up`).
  - ✅ Resources provisioned in the sandbox (Oct 24). Deploy still waits on #13, #14 and #22.
  - ✅ Data roles for local runs (Oct 25): Foundry User and Azure Event Hubs Data Sender for all four of us.
    Event Hubs receive, Cosmos DB data access and the managed identity's Storage Blob role are still to do; the
    last two need the RBAC condition extended (#16, #37).
- Review the match-intelligence agent changes from #19.
- After the first deploy: `docs/evidence/` (resource table, App Insights traces showing the served model,
  managed-identity role assignments, security recommendations snapshot).

### Taken over from Swami (Oct 25): Azure and API hosting

| Area | Issues |
| --- | --- |
| Deploy blockers | #13 (match and tracking files in the images), #14 (web app can't reach the API), #22 (operator token, replay file allowlist), #42 (✅ in #60) |
| Bicep | #47 (three router deployments), #48 (remove Speech, cap Event Hubs auto-inflate), #36 (shared keys off), #16 (roles for whoever runs `azd up`), #37 (checkpoint store role), #38 (doc and infra names) |
| API, from the end-to-end test | #50 and #51 (✅ in #60), #53 (held-graphic expiry), #55 (xG number check), #56 (Undo and faithfulness: build or drop), #57 (metrics on windowed replays) |
| Agents | #34 (agent status in `/healthz`), #35 (fallback model), #39 (latency and timeouts), #40 (team codes in lines) |

### If time runs short

Items 1 and 5 are done. Of the rest, 2 and 3 change what the demo does, so do those first, with 3 after the
router deployments in #47. Anything from 3 or 6 that does not ship by Monday comes out of the README's "Built on
Microsoft Foundry and Azure" table.
