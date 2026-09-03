# ADR-0265: The scenario graph is the stage engine; situations stay flat

**Status:** Accepted (#3568, 2026-09-03). Related ADR-0110, ADR-0258, ADR-0237.

**Context.** Negotiation, infiltration, chase and heist reduced to one roll. The situation engine's only sequencing primitive, `SituationChallengeLink.depends_on`, never had a runtime reader (roadmap Phase 5.7 "still needs design"), while the scenario graph (`MissionNode`/`MissionOption`/routes per tier) already sequences and routes.

**Decision.** Multi-stage scenes are authored on the scenario graph. It gains two primitives: `OptionKind.CONTEST` (the party's check against the template's difficulty plus `level_opposition` for an authored opposition sheet at its effective combat level; the NPC never rolls) and track nodes (`track_successes` before `track_failures`, counted per run in `MissionTrackProgress`, reset on entry, routed at a threshold to an authored target or a terminal with an authored beat outcome). Situations stay flat obstacle sets that scenario nodes pull in; `depends_on` is removed (deliberate discard: no reader ever existed).

**Why.** One sequencing engine, not two: the graph already owns routing, consequences, narration, group resolution and the beat report. A track node reuses a CHECK option's whole route table; only the terminal decision moves from the route to the node.

**Rejected.** Wiring `depends_on` with stage routing (a second engine beside the graph). An active-resistance contest where the NPC rolls (`compute_resist_increment`; two rolls hide the authored difficulty). A JSON progress blob on `MissionInstance` (its invariant forbids state blobs; a counter row per node is queryable).
