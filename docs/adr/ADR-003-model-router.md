# ADR-003: Model router over fixed per-agent deployments

Decision: all agents call one `model-router` deployment; routing mode and model subset are tuned per
agent via request metadata; `gpt-4.1-mini` is a fixed fallback.
Why: demonstrates Foundry's routing, keeps cost down for the high-volume personalizer, and records the
model chosen per call in traces for the judges.
Consequences: latency varies per call; the agent timeout + template fallback guarantees the feed.

Update (Oct 26, #47): the routing mode is a deployment setting, not request metadata, so there is one
model-router deployment per mode: `router-quality` (explainer, producer), `router-balanced` (narrator) and
`router-cost` (personalizer, localizer). The single `model-router` deployment was removed. Agents send
`reasoning_effort` low: on the demo window that cut the average moment-to-card time from 19.7 s to 15.3 s
with no call over 8 s.
