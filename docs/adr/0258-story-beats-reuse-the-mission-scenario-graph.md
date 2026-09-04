# Story beats reuse the mission scenario graph

A story beat's body is the mission scenario graph, not a second implementation of
it. The unit a GM designs before a session is the same unit `MissionNode` /
`MissionOption` / `MissionOptionRoute` / route candidates already express:
authored options with a catalog check, one route per outcome tier, weighted
candidates with consequences, and a next node. `Beat.predicate_type` gains no
choice member; nothing new is built to hold "what can the party try here." This
is ownership, not code duplication: `StoryScenario` (`world.stories`) links a
`MissionTemplate` to the story whose beat it belongs to, read only through the
reverse relation `template.story_scenario.story`, so `world.missions` never
imports `Story` (ADR-0010, ADR-0085's precedent for keeping the general side
dependency-free). A story-owned scenario is authorable by the story's own Lead
GM under the trust ladder (#2000) and canon review (#2003), not staff-only, and
is created RESTRICTED with zero draw weight so it never surfaces as a public
quest.

**Rejected: a new option engine on `Beat`.** A parallel action -> check ->
tier -> consequence -> next model scoped to stories would have been a third
implementation of a pattern the codebase already has two working copies of
(the scenario graph itself, and the stakes-resolution branch structure) - pure
duplication with its own bugs, its own authoring UI, and its own drift from
the mission version over time. The scenario graph already covers the unit;
reusing it costs one ownership link, not a second engine.

**Rejected: keeping Mission Studio staff-only, GMs assign staff templates.**
The alternative to opening authoring was leaving GMs to pick from a
staff-curated catalog and drop it on a beat, the way `gm_assign_mission`
already works. That leaves player choice at the table unauthorable by the GM
actually running the story - the table's options would always be someone
else's prep, never the GM's own. Trust-ladder gating (`GMLevelCap`,
`max_risk_tier_for`) plus canon review are exactly the abuse-case scaffolding
this needs, and both already exist for other GM-authoring surfaces.

**Objective-first: a fight grades its node, never the beat.** `OptionKind.ENCOUNTER`
lets a scenario option resolve through combat. The fight's mapped outcome
routes that option's route table through `EncounterOutcomeMapping`
(`start_encounter_for_option`/`complete_encounter_for_option`), stamped on
`CombatEncounter.scenario_deed` - never on the linked story beat directly. The
graph's eventual terminal is what decides the beat, exactly as any other
ending would. This mirrors #3559's objective-first rule for a beat-level
ENCOUNTER kind at the layer above it: a fight is incidental to the objective,
never the objective's grader by default.

**GM_CHOICE retired; the lowest authored edge fires.** `TransitionMode` and the
`Transition.mode` field are removed, along with `AmbiguousTransitionError`.
Zero eligible outbound transitions is the authoring frontier; several eligible
transitions fire the lowest `(order, pk)` edge; the routing report
(`services/routing.py::routing_report`, #3563) warns the author tree when two
transitions could both be eligible at once,
since that pair is a silent authoring mistake rather than a runtime choice
point. The GM's judgment call is authoring the option table and the transition
order before the session, and pausing at the frontier to write the next node
when nothing is authored yet - never picking among outcomes once the party has
already rolled.

**OUTCOME_TIER becomes the default predicate type.** `GM_MARKED` stops being
the fallback every richer beat resolved through while its real engine was
pending; a new beat now resolves from its graph, an encounter, a battle, or a
decisive check by default, and GM-marked is authored deliberately for an
out-of-band fact no machine grader can see.

## Prior record this supersedes or completes

- **Completes** follow-up 2 of the 2026-05-15 stories authoring redesign
  ("Situation/Encounter resolution + Sessions"), which shipped only its
  session-prep half (#3425) and left "placeholder GM-mark until their engines
  land" as the permanent default. That sketch resolved by GM mark; this
  resolves by the roll-driven graph.
- **Answers** Q5 of the 2026-05-22 challenge-missions integration findings,
  recorded there as open: missions and situations "coexist as parallel
  scenario tooling... whether that stays permanent is a broader architectural
  question." It does not stay permanent - the situation beat's body is now the
  scenario graph.
- **Supersedes** the framing of the 2026-05-18 missions design's first tenet
  ("A Mission is not 'the inside of a Story beat'"). Its substance, that the
  engine runs with no GM operating it, is kept - only the framing that a
  mission graph could never also be a beat's interior is reversed.
- **Reaffirms with a refinement** the 2026-04-20 stories design's
  "episode-level branching only, beats never chain": transitions still see
  only the beat's result (`outcome` and `outcome_key`), never the scenario
  graph's interior nodes or routes. **Reverses** the same design's
  `TransitionMode.GM_CHOICE`.
- Mission Studio was designed (2026-05-22) as "solo trusted author, no
  abuse-case scaffolding"; opening it to a story's own GM is exactly that
  scaffolding, now supplied by the trust ladder (#2000) and canon review
  (#2003).
- Applies **ADR-0030** ("GMs author story trees; outcomes resolve by player
  roll, not fiat") to the last runtime GM-fiat point the stories engine still
  had: the transition pick.
- This area already retired one reinvention - the missions-local `Affordance`
  system (Q1, same 2026-05-22 findings). Options come from authored rows and
  challenge approaches only; a scenario option never gets a third source.

> Status: accepted · Source: #3565
