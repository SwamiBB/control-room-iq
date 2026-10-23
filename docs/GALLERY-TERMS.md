# Gallery terms

Control Room IQ sits in the production gallery (the live production control room) at the **graphics** stage:
match data comes in, approved graphics go out to the graphics engine, and the vision mixer and director carry
on as today. Screens, docs, the README and the video use the gallery's own words for people and actions. The
API keeps its field and route names (`approve`, `hold`, `reject`) so the contract does not change.

## Who uses which screen

| Gallery role | What they do today | In Control Room IQ |
| --- | --- | --- |
| Producer | Owns the editorial running order; decides on stories, stats and packages | Sets the editorial call: what is worth a graphic. Reads the "why it matters" notes |
| Graphics operator | Fires score, clock, line-up and stats graphics | Uses the console: fires, holds or drops each proposal. The person named in the decision log |
| Statistician / data operator | Feeds match data to graphics and commentators | Replaced by the official data feed (synthetic in the hackathon) and the stats engine |
| Director | Calls shots and replays | Unchanged. The goal routine waits out the replay before the scorer's stats |
| Engineer in charge | Technical systems, routing, fault-finding | Watches the metrics view and the audit trail |

## Words on screen

| Use | Instead of | Where |
| --- | --- | --- |
| Running order | Queue, Next on screen | Console list of proposals |
| Fire | Approve | Primary button: "Fire" (one item) or "Fire all 3" (a package) |
| Hold | Hold | Unchanged |
| Drop | Reject | Button and decision log label |
| Override | Override | Unchanged; airs marked unverified |
| Graphics operator | Operator | Console header, decision log actor label |
| Goal routine | Package | The goal's three graphics fired with one click |
| Lower third, full-screen, ticker, caption | Layer names in code | Shown as written, without underscores |
| Gallery metrics | Metrics | Turnaround, error rate, workload panel |
| Program feed | Preview | The pitch view with what is on air |

Decision log and CSV keep the API values (`approved`, `held`, `rejected`, `overridden`, `sla_held`). The
console shows them as Fired, Held, Dropped, Overridden and Held by the timer.

## Sentences to reuse

- "The AI proposes; the graphics operator fires every graphic. Nothing reaches air without that click."
- "At a goal, one click fires the goal graphic, the scorer's stats after the replay, and the ticker."
- "We sit at the graphics stage and hand approved graphics to the existing graphics engine; we do not replace it."
