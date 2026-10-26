"""Evaluate what the agents write on the reference match: Foundry evaluators, our own code checks, planted errors.

    python evals/run_eval.py                 # 10 moments of match-042, Foundry evaluation, writes evals/results/
    python evals/run_eval.py --moments 4     # fewer moments (each moment is 5 model calls)
    python evals/run_eval.py --no-foundry    # code checks and planted errors only, no evaluation run

Three measures, written to evals/results/latest.md (the README table) and latest.json:
1. **Foundry evaluation** (built-in evaluators, run in the Foundry project): groundedness against the moment's facts,
   relevance, coherence and fluency (an LLM judge), and violence (a safety model), per output kind and language.
2. **Code checks**, the same ones the API applies before anything airs: numbers on an English line that the stats
   engine never produced (`unsourced_numbers`), and every Spanish and Hindi version checked against its English line
   (`check_variant`: numbers, names, cites, length, banned topics, actually translated).
3. **Planted errors**: real lines with one number changed. The code check must catch every one; the groundedness
   evaluator scores them too, so the table shows whether the judge would have noticed.

Needs CRQ_OFFLINE=0 with the routers and FOUNDRY_PROJECT_ENDPOINT set, and the Foundry User role (Entra ID).
The judge model is EVAL_JUDGE_DEPLOYMENT (default: the fallback deployment, gpt-4.1-mini); it only scores, it
writes nothing that airs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

os.environ.setdefault("CRQ_OFFLINE", "0")

from agents.config import settings  # noqa: E402
from agents.workflow import MomentPipeline, wants_proposal  # noqa: E402
from api.variant_checks import build_context, check_variant, unsourced_numbers  # noqa: E402
from crq_schemas import MatchEvent, MatchMeta  # noqa: E402
from ingest.stats import StateFolder  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results"
DEFAULT_MATCH = ROOT / "data" / "reference" / "match-042.jsonl"

# Built-in Foundry evaluators. The judge-based ones get the judge deployment; violence uses Foundry's safety model.
EVALUATORS = [
    ("groundedness", "builtin.groundedness", True, {"query": "{{item.query}}", "context": "{{item.context}}",
                                                    "response": "{{item.response}}"}),
    ("relevance", "builtin.relevance", True, {"query": "{{item.query}}", "response": "{{item.response}}"}),
    ("coherence", "builtin.coherence", True, {"query": "{{item.query}}", "response": "{{item.response}}"}),
    ("fluency", "builtin.fluency", True, {"response": "{{item.response}}"}),
    ("violence", "builtin.violence", False, {"query": "{{item.query}}", "response": "{{item.response}}"}),
]

QUERY = {
    "explanation": "Explain to a television audience why this moment matters, using only the facts given.",
    "line": "Write the single on-air line for this moment, using only the facts given.",
    "card": "Write the line for the on-screen graphic for this moment, using only the facts given.",
    "variant": "Render this English broadcast line for a viewer in {lang}, keeping every number and name exact.",
}
LANG_NAME = {"en": "English", "es": "Spanish", "hi": "Hindi"}
FOUNDRY_TIMEOUT_S = 20 * 60


# ---------- 1. what the agents write ----------

def select_moments(file: Path, count: int):
    """The match's meta, its moments as the API would hand them to agents, and the first `count` that get a card."""
    with file.open(encoding="utf-8") as f:
        meta = MatchMeta.model_validate_json(f.readline())
        folder = StateFolder(meta)
        moments = [m for line in filter(str.strip, f) for m in folder.apply(MatchEvent.model_validate_json(line))
                   if m.beat != "chance" and m.importance >= 0.3]
    # Every goal first (what airs biggest), then the most important of the rest; evaluated in match order.
    candidates = [m for m in moments if wants_proposal(m)]
    ranked = sorted(candidates, key=lambda m: (m.kind.value != "goal", -m.importance, m.play_ms))
    return meta, sorted(ranked[:count], key=lambda m: m.play_ms)


def facts(m, intel) -> str:
    """What the agents were given that a reader can check: the moment, the score and the stats engine's numbers."""
    s = m.state
    minute = m.t_ms // 60000 + (45 if m.period == 2 else 0)
    return json.dumps({
        "moment": m.kind.value, "minute": minute, "summary": m.summary,
        "score": {"home": s.home.goals, "away": s.away.goals},
        "xg": {"home": s.home.xg, "away": s.away.xg},
        "possession_pct": {"home": s.home.possession_pct, "away": s.away.possession_pct},
        "shots": {"home": s.home.shots, "away": s.away.shots},
        "metrics": m.metrics.model_dump(mode="json", exclude_none=True) if m.metrics else None,
        "intel": intel,
    }, ensure_ascii=False, default=str)


async def generate(meta, moments, pause_s: float) -> list[dict]:
    """Run the five agents on each moment, as the API does, and keep every model-written output."""
    pipeline = MomentPipeline()
    rows, i = [], 0
    for m in moments:
        if i:
            await asyncio.sleep(pause_s)  # stay under the routers' tokens-per-minute limits
        i += 1
        started = time.perf_counter()
        res = await pipeline.process(m, meta=meta)
        print(f"  {m.kind.value:<15} {time.perf_counter() - started:5.1f}s  failures={len(res.failures)}", flush=True)
        context = facts(m, res.intel)
        base = {"moment_id": m.moment_id, "moment": m.kind.value, "context": context, "planted": "no"}
        if res.explanation.meta.routing != "template":
            rows.append({**base, "kind": "explanation", "lang": "en", "query": QUERY["explanation"],
                         "response": f"{res.explanation.headline}. {res.explanation.why_it_matters}"})
        rows.append({**base, "kind": "line", "lang": "en", "query": QUERY["line"], "response": res.line,
                     "_moment": m})
        if res.proposal is not None and not res.proposal.fallback:
            rows.append({**base, "kind": "card", "lang": "en", "query": QUERY["card"], "response": res.proposal.line,
                         "_moment": m, "_proposal": res.proposal})
        # Versions are written from the card's line when there is a card (#90), else from the narrator's line.
        source_line = res.proposal.line if res.proposal is not None else res.line
        for v in res.variants:
            if v.lang != "en" and v.persona.value == "fan" and v.access == "none" and v.meta.routing != "template":
                rows.append({**base, "kind": "variant", "lang": v.lang,
                             "query": QUERY["variant"].format(lang=LANG_NAME[v.lang]),
                             "context": f"English line: {source_line}\nFacts: {context}", "response": v.text,
                             "_moment": m, "_proposal": res.proposal, "_variant": v})
    return rows


# ---------- 2. code checks, the ones the API runs before air ----------

def code_checks(rows: list[dict], meta) -> dict:
    lines = [r for r in rows if r["kind"] in ("line", "card")]
    flagged = [r for r in lines if unsourced_numbers(r["response"], r["_moment"])]
    variants = [r for r in rows if r["kind"] == "variant" and r.get("_proposal") is not None]
    failures = defaultdict(int)
    passed = 0
    for r in variants:
        codes = check_variant(r["_variant"], build_context(r["_proposal"], r["_moment"], meta))
        passed += not codes
        for c in codes:
            failures[c] += 1
    return {"english_lines": len(lines), "lines_with_unsourced_numbers": len(flagged),
            "flagged_examples": [r["response"] for r in flagged][:5],
            "variants_checked": len(variants), "variants_passed": passed, "variant_failures": dict(failures)}


# ---------- 3. planted errors ----------

_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _replace_first_number(text: str, candidates) -> str | None:
    """The text with its first number replaced by the first candidate that shows differently, else None."""
    match = _NUMBER.search(text)
    if not match:
        return None
    original = float(match.group())
    decimals = "." in match.group()
    for value in candidates:
        shown = f"{value:.1f}" if decimals else str(round(value))
        if float(shown) != original:
            return text[:match.start()] + shown + text[match.end():]
    return None


def planted_errors(rows: list[dict], limit: int) -> tuple[list[dict], dict]:
    """Two kinds of wrong number, alternating, in real lines and cards:
    - absent: a value the match data doesn't contain. The code check must catch every one.
    - swapped: a real value from elsewhere in the facts (another team's xG, a different count). The code check
      accepts any number the data contains, so it can't catch these by design; the groundedness judge has to."""
    planted = []
    for i, r in enumerate(r for r in rows if r["kind"] in ("line", "card")):
        if len(planted) >= limit:
            break
        kind = "absent" if i % 2 == 0 else "swapped"
        m = r["_moment"]
        if kind == "absent":
            candidates = [v for v in (77.0, 13.0, 4.4, 9.9, 61.0, 133.0) if unsourced_numbers(f"{v:g}", m)]
        else:
            candidates = [float(t) for t in _NUMBER.findall(r["context"]) if 0 < float(t) < 200]
        wrong = _replace_first_number(r["response"], candidates)
        if wrong:
            planted.append({**r, "response": wrong, "planted": kind, "original": r["response"]})
    report = {}
    for kind in ("absent", "swapped"):
        ps = [p for p in planted if p["planted"] == kind]
        caught = [p for p in ps if unsourced_numbers(p["response"], p["_moment"])]
        report[kind] = {"planted": len(ps), "caught_by_code": len(caught),
                        "missed": [p["response"] for p in ps if p not in caught]}
    return planted, report


# ---------- 4. the Foundry evaluation run ----------

def run_foundry(items: list[dict], judge: str, name: str) -> tuple[list[dict], str | None]:
    """Submit the rows to a Foundry evaluation run and return per-row scores plus the portal report URL."""
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import TestingCriterionAzureAIEvaluator
    from azure.identity import DefaultAzureCredential

    project = AIProjectClient(endpoint=settings.foundry_project_endpoint, credential=DefaultAzureCredential())
    client = project.get_openai_client()
    fields = ["query", "context", "response", "kind", "lang", "moment", "moment_id", "planted"]
    evaluation = client.evals.create(
        name=name,
        data_source_config={"type": "custom", "item_schema": {
            "type": "object", "properties": {f: {"type": "string"} for f in fields}, "required": fields}},
        testing_criteria=[TestingCriterionAzureAIEvaluator(
            type="azure_ai_evaluator", name=label, evaluator_name=evaluator, data_mapping=mapping,
            **({"initialization_parameters": {"model": judge}} if needs_judge else {}))
            for label, evaluator, needs_judge, mapping in EVALUATORS],
    )
    run = client.evals.runs.create(
        eval_id=evaluation.id, name=f"{name}-run",
        data_source={"type": "jsonl", "source": {"type": "file_content",
                                                 "content": [{"item": {f: str(r.get(f, "")) for f in fields}}
                                                             for r in items]}},
    )
    print(f"  Foundry evaluation {evaluation.id}, run {run.id}: waiting", flush=True)
    deadline = time.monotonic() + FOUNDRY_TIMEOUT_S
    while run.status not in ("completed", "failed", "canceled"):
        if time.monotonic() > deadline:
            raise RuntimeError(f"the Foundry evaluation run was still {run.status} after {FOUNDRY_TIMEOUT_S} s")
        time.sleep(10)
        run = client.evals.runs.retrieve(run.id, eval_id=evaluation.id)
    if run.status != "completed":
        raise RuntimeError(f"the Foundry evaluation run {run.status}: {getattr(run, 'error', None)}")
    scored = []
    for out in client.evals.runs.output_items.list(run.id, eval_id=evaluation.id):
        item = (getattr(out, "datasource_item", None) or {})
        results = {r.name if hasattr(r, "name") else r["name"]:
                   (r.score if hasattr(r, "score") else r.get("score")) for r in (out.results or [])}
        scored.append({**{k: item.get(k) for k in ("kind", "lang", "planted", "moment")}, "scores": results})
    return scored, getattr(run, "report_url", None)


def summarize(scored: list[dict]) -> dict:
    """Mean score per evaluator, by output kind and language, real rows and planted rows apart."""
    table = defaultdict(lambda: defaultdict(list))
    for s in scored:
        planted = s.get("planted")
        group = f"planted ({planted})" if planted not in (None, "no") else f"{s.get('kind')}/{s.get('lang')}"
        for name, score in (s.get("scores") or {}).items():
            if isinstance(score, (int, float)):
                table[group][name].append(float(score))
    return {group: {name: {"mean": round(statistics.mean(v), 2), "n": len(v)} for name, v in by.items()}
            for group, by in table.items()}


# ---------- report ----------

def write_report(summary: dict, checks: dict, planted: dict, meta: dict) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "latest.json").write_text(json.dumps(
        {"meta": meta, "foundry": summary, "code_checks": checks, "planted": planted}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    names = [label for label, *_ in EVALUATORS]
    lines = [
        "# Evaluation results", "",
        f"Run {meta['when']} on `{meta['match']}`: {meta['moments']} moments, {meta['rows']} model-written outputs "
        f"(routers at `reasoning_effort={meta['effort']}`). Judge for groundedness, relevance, coherence and fluency: "
        f"`{meta['judge']}`; violence uses Foundry's safety model. Scores are 1–5 (higher is better), except "
        "violence, where lower is safer (0–7).", "",
    ]
    if summary:
        lines += [f"| Output | {' | '.join(names)} |", f"| --- | {' | '.join('---' for _ in names)} |"]
        for group in sorted(summary):
            cells = [f"{summary[group][n]['mean']:.2f} (n={summary[group][n]['n']})" if n in summary[group] else "–"
                     for n in names]
            lines.append(f"| {group} | {' | '.join(cells)} |")
        lines += ["", "The full run, with every output and score, is in the Foundry project under Evaluations."]
    elif meta.get("foundry_error"):
        lines.append(f"_The Foundry evaluation didn't complete: {meta['foundry_error']}_")
    else:
        lines.append("_No Foundry evaluation in this run (--no-foundry)._")
    lines += [
        "", "## Code checks (the API applies these before anything airs)", "",
        f"- English lines and cards with a number the stats engine never produced: "
        f"**{checks['lines_with_unsourced_numbers']} of {checks['english_lines']}** (flagged to the operator).",
        f"- Spanish and Hindi versions that pass every check: **{checks['variants_passed']} of "
        f"{checks['variants_checked']}**; failures by check: {checks['variant_failures'] or 'none'}. A version "
        "that fails is replaced by the template line in that language.",
        "", "## Planted errors (real lines with one number changed)", "",
        f"- **A number the match data doesn't contain:** {planted['absent']['caught_by_code']} of "
        f"{planted['absent']['planted']} caught by the code check."
        + (f" Missed: {planted['absent']['missed']}" if planted["absent"]["missed"] else ""),
        f"- **A real number from the wrong place** (another team's xG, a different count): "
        f"{planted['swapped']['caught_by_code']} of {planted['swapped']['planted']} caught by the code check, which "
        "accepts any number the data contains; this is the case the groundedness judge is for.",
    ]
    for kind in ("absent", "swapped"):
        group = summary.get(f"planted ({kind})", {})
        if "groundedness" in group:
            lines.append(f"- Groundedness on the planted ({kind}) lines: **{group['groundedness']['mean']:.2f}**, "
                         "against the real lines above.")
    (RESULTS / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--match", type=Path, default=DEFAULT_MATCH)
    ap.add_argument("--moments", type=int, default=10)
    ap.add_argument("--planted", type=int, default=10)
    ap.add_argument("--pause", type=float, default=20.0, help="seconds between moments (router TPM limits)")
    ap.add_argument("--judge", default=os.environ.get("EVAL_JUDGE_DEPLOYMENT", settings.model_fallback))
    ap.add_argument("--no-foundry", action="store_true", help="skip the Foundry evaluation run")
    args = ap.parse_args(argv)
    if settings.offline:
        sys.exit("CRQ_OFFLINE=1: the evaluation scores model-written output, so it needs the routers")
    if not args.no_foundry and not settings.foundry_project_endpoint:
        sys.exit("FOUNDRY_PROJECT_ENDPOINT is not set (azd env get-values > .env)")

    meta, moments = select_moments(args.match, args.moments)
    print(f"{len(moments)} moments from {args.match.name}", flush=True)
    rows = asyncio.run(generate(meta, moments, args.pause))
    checks = code_checks(rows, meta)
    planted_rows, planted = planted_errors(rows, args.planted)
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    run_meta = {"when": when, "match": args.match.name, "moments": len(moments), "rows": len(rows),
                "effort": settings.reasoning_effort or "default", "judge": args.judge}
    summary = {}
    write_report(summary, checks, planted, run_meta)  # the code checks are kept even if the Foundry run fails
    if not args.no_foundry:
        try:
            scored, report_url = run_foundry(rows + planted_rows, args.judge, f"crq-eval-{when[:10]}")
        except Exception as ex:  # noqa: BLE001 - report it alongside the results we already have
            run_meta["foundry_error"] = f"{type(ex).__name__}: {ex}"
            write_report(summary, checks, planted, run_meta)
            print((RESULTS / "latest.md").read_text(encoding="utf-8"))
            return 1
        summary = summarize(scored)
        # Printed, never written: the portal URL names the Azure resources, and the results go in the public repo.
        print(f"Foundry report (not saved): {report_url}")
        write_report(summary, checks, planted, run_meta)
    print((RESULTS / "latest.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
