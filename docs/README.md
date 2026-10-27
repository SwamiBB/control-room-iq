# Documentation map

Reading order for someone new to the repository:

1. [`../README.md`](../README.md) — project overview, live demo URLs, enterprise controls block
2. [`ENTERPRISE-OVERVIEW.md`](ENTERPRISE-OVERVIEW.md) — enterprise architecture claim with code pointers
3. [`../SECURITY.md`](../SECURITY.md) — security posture, trust boundary, deployment-posture section
4. [`THREAT-MODEL.md`](THREAT-MODEL.md) — eleven named threats, today's mitigation, residual deferred items

## For judges and reviewers

| File | What's in it |
| --- | --- |
| [ENTERPRISE-OVERVIEW.md](ENTERPRISE-OVERVIEW.md) | Judge-facing enterprise claim: the gate is in the schema, numbers from code, model choice auditable, full audit trail, enterprise substrate. Every claim points at a file. |
| [ARCHITECTURE.md](ARCHITECTURE.md) | End-to-end architecture: principles, system context, logical architecture (five stages), runtime flows, core logic, data contracts, interfaces, Azure deployment topology, observability, reliability, security, repo map, quality gates, ADR summary, open questions. |
| [THREAT-MODEL.md](THREAT-MODEL.md) | STRIDE-adjacent threat model: eleven threats as a table (unauth operator, prompt injection, model outage, data exfiltration, public URL abuse, supply chain, decision log tampering, credential theft, network path, replay drift, unsafe content). Each row has a current mitigation and a deferred residual. |
| [RUNBOOK.md](RUNBOOK.md) | On-call operations: service inventory with health probes; starting the reference replay; reading `/metrics`; downloading `/decisions.csv`; incident playbooks (Foundry quota, API crash, demo URL dark, public endpoint abuse); keys and secrets (there are none to rotate). |
| [COPILOT-REVIEWS.md](COPILOT-REVIEWS.md) | AI-assisted code and architecture review records produced using GitHub Copilot code review. Each review carries a Resolution notes block naming the findings already addressed on `main`. |
| [adr/](adr/) | Decision records: ADR-001 Python + Agent Framework, ADR-002 synthetic data, ADR-003 model router, ADR-004 Container Apps over AKS. |

## Reference

| File | What's in it |
| --- | --- |
| [DESIGN.md](DESIGN.md) | Design-level detail: data contracts, state engine, agent orchestration, approval loop, overlay feed, personalization, evaluation, failure handling, UI. Companion to ARCHITECTURE.md. |
| [SETUP.md](SETUP.md) | Local development setup. |
| [CALIBRATION.md](CALIBRATION.md) | Simulator realism table: 200-seed averages for goals, shots, passes, accuracy, cards, distance, top speed, all within top-flight ranges. |
| [GALLERY-TERMS.md](GALLERY-TERMS.md) | Broadcast gallery vocabulary mapped to the UI (running order, fire, drop, goal routine). |
| [evidence/](evidence/) | Screenshots and runtime evidence captures. |
| [img/](img/) | Hero and section screenshots for the README. |

## Historical / internal context

| File | What's in it |
| --- | --- |
| [internal/](internal/) | Preliminary scoping draft, build-week plan, project summary, change log, individual-named task handoff documents. Preserved as team context from the October 2026 build week. **Not** current product documentation; use the files above instead. |
