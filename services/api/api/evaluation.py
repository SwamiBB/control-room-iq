"""EvaluationRecorder: one row per agent output, the table the Foundry evaluation reads.

Rows are built from the MomentPipeline result, so the agents code is untouched: explainer, narrator and
producer give one row each, the personalizer one row per persona and language. If the pipeline result
carries per-call details (`calls`: [{agent, latency_ms, routed_model}]), they are used; otherwise every row
gets the whole moment's latency and routed_model stays empty (offline runs use templates, so there is none).
An operator decision is attached afterwards, with any edited line, so the edit can be scored too.
"""

from __future__ import annotations

import json
from typing import Any

from crq_schemas import EvaluationRecord, Moment


def _source(agent: str, res: Any, offline: bool) -> str:
    if offline or any(f.startswith(f"{agent}:") for f in res.failures):
        return "template"
    return "model"


def records_for(m: Moment, res: Any, latency_ms: int, offline: bool) -> list[EvaluationRecord]:
    calls = {c["agent"]: c for c in getattr(res, "calls", None) or []}
    snapshot = m.snapshot or {"summary": m.summary, "event_ids": m.event_ids}

    def row(agent: str, output: str, cites: list[str], suffix: str = "", **kw: Any) -> EvaluationRecord:
        c = calls.get(agent, {})
        return EvaluationRecord(record_id=f"{m.moment_id}-ev-{agent}{suffix}", match_id=m.match_id, moment_id=m.moment_id,
                                agent=agent, routed_model=c.get("routed_model"), snapshot=snapshot, output=output,
                                cites=cites, latency_ms=int(c.get("latency_ms", latency_ms)),
                                source=_source(agent, res, offline), **kw)  # type: ignore[arg-type]

    e = res.explanation
    rows = [row("explainer", f"{e.headline}. {e.why_it_matters}", list(e.cites)),
            row("narrator", res.line, list(e.cites))]
    for v in res.variants:
        rows.append(row("personalizer", v.text, list(v.cites or e.cites), f"-{v.persona.value}-{v.lang}",
                        persona=v.persona, lang=v.lang))
    if res.proposal:
        cites = [x["event_id"] for x in res.proposal.evidence if "event_id" in x] or list(m.event_ids)
        rows.append(row("producer", res.proposal.line, cites))
    return rows


def attach_decision(rows: list[EvaluationRecord], moment_id: str, decision_id: str, edited_line: str | None) -> None:
    for r in rows:
        if r.moment_id == moment_id:
            r.decision_id = decision_id
            if edited_line and r.agent == "producer":  # the operator rewrote the on-air line, nothing else
                r.edited_line = edited_line


def to_foundry_jsonl(rows: list[EvaluationRecord]) -> str:
    """query / context / response per row (the shape Foundry evaluators read), ids kept for joining back."""
    out = []
    for r in rows:
        out.append(json.dumps({
            "id": r.record_id, "moment_id": r.moment_id, "agent": r.agent, "lang": r.lang,
            "persona": r.persona.value if r.persona else None, "source": r.source, "routed_model": r.routed_model,
            "query": f"Describe this football moment for the {r.persona.value if r.persona else 'broadcast'} audience",
            "context": json.dumps(r.snapshot, sort_keys=True, default=str), "response": r.edited_line or r.output,
            "cites": r.cites, "decision_id": r.decision_id,
        }, ensure_ascii=False))
    return "\n".join(out) + ("\n" if out else "")
