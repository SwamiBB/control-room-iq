"""Foundry agents for Control Room IQ, built on the Microsoft Agent Framework.

Agents (see prompts/), with their router deployment:
- explainer     why a moment matters, citing event IDs                (quality)  -> Explanation
- narrator      the English on-air line; half/full-time recaps        (balanced) -> str
- producer      the graphic, its evidence and alternatives            (quality)  -> OverlayProposal
- personalizer  English versions per persona x access                 (cost)     -> NarrativeVariant[]
- localizer     Spanish and Hindi from the English versions, one call (cost)     -> NarrativeVariant[]

Placement (scheduler), numbers, the strike cue and the deaf fan's card are code, not agents.

Orchestration lives in `workflow.py`. Each agent has a deterministic fallback so the overlay feed
never stalls when a model call fails or times out.
"""
