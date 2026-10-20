"""Foundry agents for Control Room IQ, built on the Microsoft Agent Framework.

Agents (see prompts/):
- explainer     why a moment matters, citing event IDs           -> Explanation
- narrator      on-air line + running narrative + recaps         -> str
- personalizer  persona x language variants                      -> NarrativeVariant[]
- producer      what goes on screen, when; proposal for approval -> OverlayProposal
- squad_author  generates fictional squads and storylines        -> Team (data innovation)

Orchestration lives in `workflow.py`. Each agent has a deterministic fallback so the overlay feed
never stalls when a model call fails or times out.
"""
