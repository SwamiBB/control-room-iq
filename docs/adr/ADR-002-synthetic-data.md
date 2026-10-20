# ADR-002: Own deterministic simulator plus LLM squad authoring

Decision: a seedable possession-phase match engine produces the event stream (ground truth); a Foundry
agent generates fictional squads and storylines that seed it.
Why: evaluation of narrative faithfulness needs deterministic ground truth; LLM-authored squads satisfy
the data-innovation prong without making the stream itself non-reproducible.
Consequences: no real club, player, venue, or competition data anywhere in the repo.
