# ADR-0261: The routing report is advisory and open-world

**Status:** Accepted (2026-09-03, #3563). Extends ADR-0258; related ADR-0259.

**Context.** A GM authors branching between episodes as `TransitionRequiredOutcome`
rows: "if beat 4 fails go to episode C", "if the hostage stake is lost go to D". Until
#3563 the only place a rule was readable was the per-edge edit dialog, and the only
authoring-time check was `validate_routing_readiness`, which flagged pairs of edges that
could both be eligible (ADR-0258). Nothing told the author that a failure-shaped outcome
had nowhere to go; the run simply paused at the frontier mid-session.

**Decision.** `services/routing.py::routing_report` builds one `RoutingReport` per episode
from the same rows the runtime evaluates: dead ends (a beat's FAILURE, its EXPIRED when it
has a deadline, each of its stakes' LOSS, none of which any outbound transition accepts)
and ambiguities (ADR-0258's contradiction test). Two properties are deliberate:

1. **Advisory.** The report never blocks saving, resolving or running. It rides the
   episode payloads as `routing_problems` (GM text, gated like `description`) and renders
   as markers on the graph and the author tree. The frontier pause stays the safety net;
   an unready plan never blocks play.
2. **Open-world.** A dead-end check pins exactly one subject to its failure-shaped outcome
   and treats every unpinned beat, stake and option key as satisfiable. So a rule about
   some other beat never disqualifies an edge, an unreferenced stake is never a dead end,
   and a frontier edge with no rules accepts everything. Lines are one per (subject,
   outcome), which is what the author can act on.

**Rejected alternative: closed-world.** Treating every unpinned subject as unsatisfiable
reports more holes, but they are combinations ("B fails while A also fails") the author
cannot read off a single line, it flags every beat that is merely referenced by a
different edge, and it would make an unreferenced stake a dead end. The noise would teach
GMs to ignore the report. The cost of open-world is under-reporting those combination
cases; the frontier pause still catches them at runtime, and the report is advisory.

**Also decided here.** `validate_routing_readiness` and `RoutingReadinessReport` are
retired into the report rather than wrapped (one implementation of the contradiction
test); an episode with no outbound transitions gets an empty report, because zero
transitions is the authoring frontier by design, not a mistake; and a rule on another
episode's beat never yields a dead-end line but stays in the contradiction test, because
at runtime it does discriminate between edges.
