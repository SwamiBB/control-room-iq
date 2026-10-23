## Agents work: Siranjeevi's consolidated list

Last updated: Friday, October 23, 2026, night (Central). Checked against `main` at `3464296` (#20). Merges
Siranjeevi's own list with the agent items from `CHANGES-2026-10-23.md`, `HANDOFF-2026-10-23-agents-web.md` and
`HANDOFF-2026-10-24-match-intelligence.md`. #19 added `agents/match_intel.py` and touched the prompts and
`workflow.py`; none of the items below are done yet.

| # | Task | Status | Why it is next |
| --- | --- | --- | --- |
| 1 | **Fix #9:** the API crashes on startup in Azure (`clients.py`), plus a test that builds the pipeline in online mode | Still broken | About 30 minutes. Blocks deploying the API and checking the live models |
| 2 | **`scheduler.py`** with tests | Does not exist | A Friday must-have, now overdue. Until it lands, a fired graphic airs at once, unscheduled |
| 3 | **Router clients per agent** with `model_served` | Settings exist, nothing wired | Needs the three router deployments in Bicep (Swami). Until then everything uses `model-router` |
| 4 | **#10:** check the agents get real replies from the live `model-router` | Waiting on 1, and on the Foundry User role | First real test against Azure |
| 5 | **Personalizer prompt** and the **fallback bug** (#17) | Open | Asked in the Oct 23 handoff; wrong text reaches viewers until fixed |
| 6 | **`register_agents.py`** (Saturday), **evaluations** and the README table (Monday) | Do not exist | Saturday and Monday deliverables |

### Details

**1. Fix #9 (`services/agents/agents/clients.py`)**
- The client is built once at import time for every agent (`lru_cache`), so a bad endpoint, a missing
  credential or a constructor change in `agent-framework` stops the whole API from starting.
- Make startup survive a client failure: log it and let each agent fall back to its template, so the API
  still serves the console.
- Add a test that builds `MomentPipeline` with `CRQ_OFFLINE=0` and a stubbed client, so a constructor or
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

**3. Router clients (`clients.py`, `config.py`)**
- One client per router deployment: explainer and producer → `ROUTER_QUALITY`, narrator → `ROUTER_BALANCED`,
  personalizer → `ROUTER_COST`. Fall back to `MODEL_ROUTER_DEPLOYMENT` when a mode's deployment is missing.
- Read `response.model` into `meta.model_served` and `meta.routing` on each output; span attributes
  `crq.agent`, `crq.routing`, `crq.model_served`. The README promises "the model that served each call is
  recorded".
- Swami adds the three deployments to `infra/modules/ai.bicep` and the `ROUTER_*` settings to `apps.bicep`
  (and removes the Speech resource).

**4. #10 live check**
- After 1 and the Foundry User role: run the reference match with `CRQ_OFFLINE=0`, confirm every agent
  returns a model reply (not a fallback), and note the served models for the README.

**5. Personalizer prompt and fallback**
- `prompts/personalizer.md`: remove the old `accessibility` (audio description) persona and Arabic. Personas
  are newcomer, fan, analyst; `deaf` is an access setting on top of any of them; languages en, es, hi. The
  match-intelligence rules already in the prompt stay.
- `workflow.py` `fallback_variants` (#17): stop copying the English line into `es` / `hi` and labeling it with
  that language. Emit English only; the API then sends the proper template line.
- **`fan_card`: no longer needed from the agents.** The API builds the deaf fan's card in code
  (`api/fan_card.py`, in the pending `feat/readme-and-followups` patch). If the workflow ever builds one, the API
  uses it instead.

**6. `register_agents.py` and evaluations**
- `register_agents.py`: create or update the four agents by name in Foundry Agent Service
  (`azure-ai-projects`), so they are inspectable in the portal; the runner still executes them locally.
- `evals/run_eval.py`: replay the reference match offline, submit a Foundry evaluation run (groundedness,
  relevance, fluency per language), run the planted-falsehood set (Pranav's `evals/datasets/`), write
  `evals/results/latest.md` for the README table. Optional nightly `.github/workflows/evals.yml`.

### Also on Siranjeevi (not code)

- Bring the Azure resources up and deploy from CI with Swami (first `azd up`).
- Review the match-intelligence agent changes from #19.
- After the first deploy: `docs/evidence/` (resource table, App Insights traces showing the served model,
  managed-identity role assignments, security recommendations snapshot).

### If time runs short

Items 1, 2, 3 and 5 change what the demo does; do those first. Anything from 3 or 6 that does not ship by
Monday comes out of the README's "Built on Microsoft Foundry and Azure" table.
