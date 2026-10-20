# ADR-003: Model router over fixed per-agent deployments

Decision: all agents call one `model-router` deployment; routing mode and model subset are tuned per
agent via request metadata; `gpt-4.1-mini` is a fixed fallback.
Why: demonstrates Foundry's routing, keeps cost down for the high-volume personalizer, and records the
model chosen per call in traces for the judges.
Consequences: latency varies per call; the agent timeout + template fallback guarantees the feed.
