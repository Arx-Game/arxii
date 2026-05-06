# Player and GM Experience — Brainstorm Design Capture

**Status:** brainstorm capture (not yet a spec)
**Date:** 2026-05-06
**Scope:** Player day-in-the-life UX + GM authoring/run-session UX + cross-cutting systems surfaced during the brainstorm

## Why this exists

Originated as a brainstorm of "what GMs need" so we could plan toward an
end-to-end GM-loop integration test. The brainstorm rapidly surfaced that
GM tooling assumes a player-experience baseline that is only partially
specified across `rp-scenes.md`, `events.md`, `gm-system.md`, and
`stories-gm.md`. We pivoted to capturing the full player and GM experience
shape end-to-end so the roadmap has somewhere to anchor concrete spec work.

This document is a **brainstorm capture**, not a settled design. It records
the principles, design decisions, system overlaps, and open questions
surfaced during the conversation. Subsequent specs should reference and
refine these.

## Bedrock principles (HARD RULES + design principles)

Twelve principles emerged. The first six are **HARD RULES** — non-negotiable
constraints that any future spec must respect. The remaining six are
**design principles** — strong defaults that shape system shape.

### HARD RULES (non-negotiable)

1. **Cooperative RP bedrock.** PC antagonism / conflict only happens when
   both players want it. The game must never put two players at
   cross-purposes without their consent. Subsumes "No PVP killing" and
   "Escape valves everywhere" from the existing roadmap.

2. **Frictionless RP entry.** Zero ceremony to start RP. No form-filling,
   no "declare scene" toggle, no "I am now RPing" flag. The Interaction
   model accommodates RP without explicit player action; organic RP
   remains unmarked even when DB can detect it.

3. **No invisible characters in rooms, ever.** No staff, GM, or player is
   ever hidden from other PCs in a room. Structural defense against
   voyeurism abuse with concrete community history. Stealth is a
   perception-check resolution, never a presence-erasure toggle.

4. **Public means public.** GM sessions / encounters / events in public
   rooms are open to anyone who wanders in. No "locked encounter in
   public" mechanic. Party-only sessions must use instanced/temporary
   rooms.

5. **Display by persona, never out alts.** Every player-facing surface
   that lists or counts characters uses persona identity. Account-scoped
   displays are staff-only and explicitly permission-gated.

6. **Never parse pose text for mechanical effects.** No keyword sniffing,
   no sentiment analysis, no length scoring. Mechanical state is opt-in
   via player toggles (mood, stance, intent), never inferred from creative
   writing.

### Design principles

7. **Risk visibility.** Players always know what risk they're walking
   into. Roaming is mostly atmospheric; forced "must deal with this to
   escape" encounters are dungeon-only. Dangerous areas are clearly
   flagged before entry.

8. **Constrained bystander reactions.** When a player is mid-action,
   witnesses get pop-up choice menus with pre-authored options
   (CK2 event-tree model), filtered by character traits. Conflict-flavored
   options fire AFTER the active player's moment resolves. Pro-active-
   player options ("cover for the thief") are first-class. "Do nothing"
   is always available; pop-ups auto-dismiss.

9. **GM authority is constrained — authors not arbiters.** GMs author
   story trees with pre-defined rolls and routing. Outcomes are determined
   by player rolls, not GM fiat. GMs CAN modify check difficulty (umpire
   role) but CANNOT override outcomes. Live tooling is secondary to
   authoring tooling.

10. **Bite-sized encounters.** Story encounters resolve per-session;
    "PC stuck in jail until next session" is a rare exception, not the
    norm. Players have busy lives; the game accommodates the gaps.

11. **IC-vs-UI placement test.** Abstract bookkeeping (AP allocation,
    vote tweaks) → general UI / command. Room-bound concrete features
    players invest in (research libraries, alchemy labs) → physical
    space. The test is "does the IC fiction add immersion or just
    friction?"

12. **Brainstorm UX organically.** Don't ask players "what's primary"
    categorical questions; walk concrete post-action steps. Players
    experience their UX as simultaneous; categorical sorting is an
    agent reflex.

## Player experience design

### Login moment

Whether logging in via telnet or via a web-frontend account portrait,
the post-login state converges: the same information set is available
to the player, rendered differently per transport. Information set:

- **Room scroll** — immersive anchor. Telnet renders it as the
  welcome scroll; web renders it as a side panel.
- **Friends online** — visible friends + watched players (per-relationship
  color coding).
- **GM notifications** — story updates, scheduling pings; high-salience,
  these ping.
- **IC messengers waiting** — in-character correspondence.
- **OOC mail** — OOC correspondence (separate from messengers).
- **OOC notifications** — system pings (scheduling, GM/staff responses).
- **Offline-time story summary** — what advanced in your arcs while
  you were gone.

The information appears *simultaneous* to the player even though the
underlying delivery is sequential. Web should render as calm, dismissable
alerts; telnet as a single login scroll (a constraint, not a target).

### Post-login onion

Players naturally engage with these layers in (rough) order, though all
are visible:

```
1. OOC social hello       — covenant / org channels; friends notice, you greet
2. OOC async triage       — pages, IC messengers, OOC mail, notifications
3. IC weekly admin        — AP this week, vote tweaks, research, mission allocation
4. IC active venture      — mission giver, scene to walk into, organic exploration
```

**Inbox proliferation flagged:** notifications, pages, messengers, OOC
mail are 4 distinct surfaces. Some may collapse in design; needs a
follow-up brainstorm.

### Room arrival and presence model

Web side panel splits room contents into two groups:

- **Puppeted characters** — distinct list, top of panel. PCs ICly present.
- **Other contents** — collapsible: unpuppeted NPCs, furniture, pets,
  retainers.

Three-tier presence model:

```
absent → OOC-present → IC-in-scene
            ↑              ↑
   walks into room   first IC act
                     (pose / speak / Make an Entrance)
```

Walking in flips you to OOC-present (visible in the side panel with an
OOC marker). Your *first IC command* (pose, speak, `+enter` from the
resonance system) flips you to IC-in-scene.

Scene-vs-organic split:
- **Scene** = explicitly started, logged, may be public. Public scene
  arrivals can see backscroll. OOC notification fires.
- **Organic RP** = no scene marker, no log. No arrival notice. Invisible
  to outside discovery (per frictionless RP entry).

Arrival event display:
- Telnet: `PersonaName arrived.` (classic MU convention).
- Web: no event in scroll; side panel gains an OOC-marked row.

GM characters and staff characters are visible with OOC markers, likely
their own column (separate from PC OOC-present rows).

### Discovery surfaces

Three distinct surfaces:

- **Scene list + event scheduler** (combined) — active scenes, scheduled
  upcoming events, GM sessions. Conceptually unified for players.
- **`where` command** (Arx 1 inheritance) — who's in public grid spaces
  *right now*. Default scope: city region + adjacent. Optional global.
  Public rooms only. Active-scene marker on room name.
  Friends/watched characters color-coded by relationship level.
- **Organic RP is invisible by design.** Per frictionless RP entry: room
  presence visible (via where), the *act of RPing* is not surfaced.

### Movement

- **Telnet:** named exits. Outer grid rooms get cardinal + intercardinal
  defaults (N/NE/E/SE/S/SW/W/NW) plus named building entries (e.g.,
  "Guard Tower Central").
- **Web:** type or click in room panel; map / minimap toggle.
- **In-city travel:** AP-free, time-free, walked.
- **Inter-city travel:** abstracted. Magic-cost portals between major
  city hubs. Wilderness is *node-shaped*, not built room-by-room
  (abstracted journeys with time + money cost).
- **Fast travel rule:**
  - ✓ For **scheduled / committed** activity (events, GM sessions,
    invited scenes) — fast travel allowed (IC fiction: portals).
  - ✗ For **organic / discovered** RP — walk the grid. Roaming is the
    ambient content layer.

Roaming itself is mostly atmospheric. Forced encounters are dungeon-only
(per risk visibility).

### Story tracking — the "sheet"

In MU shorthand, "looking at my sheet" means *everything about my
character*: vitals, stats, skills, written history, relationships,
magic, knowledge, AND a stories panel. The stories panel is a
first-class part of the character self-view.

Stories panel design:
- Shows personal story progress, what you've discovered, what you've
  experienced
- Hints at what to do next (explicit beats or implied — "appears you
  need to find out more about X")
- **No dead space** — always communicates something
- **GM-pause fallback:** "OOC: Waiting on GM updates" when literally
  nothing is authored next. Ideal: player never sees this.
- **IC-knowledge-gated visibility** — branches not taken, outcomes not
  derived, things you didn't do are all hidden. You see only what
  your PC knows / experienced.

Three modes of player interaction with stories:

1. **Review** — read past, re-read for enjoyment, work puzzles / mysteries
2. **Schedule** — confirm/decline/tentative on sessions, suggest days
3. **Independent progression** — between-session beats workable solo or
   small-group; personal stories often level-gated or world-involvement-
   gated. *Most* stories have independent progress parts.

Scheduling display: by persona always (per alt privacy hard rule).

## GM experience design

### Authoring (the primary GM activity)

GM authoring artifact is a **story tree**:

- **Plot points** = encounters / situations / scene beats
- **Pre-defined rolls** with authored DCs and check types
- **Pre-defined routing** — success → branch A, failure → branch B,
  some randomization (X / Y / J)
- **Branches are graphs** — can converge, loop back, diverge

Concrete example walked: "Big Trouble In Little Luxen" — Junior GM
authors a story about an abyssal cult in lower Luxen. Plot point 1 is
a thief stealing a magical artifact from a merchant; success branches
to "PCs hold artifact, pursued by cult"; failure branches to "cult has
artifact, NPCs come to PCs for help."

GMs are authors and narrators, not arbiters. Outcomes determined by
player rolls. Live emergency-authoring is allowed but exceptional.

### Live session run

**Convening players:**
- Notification with "join session" button
- Players fast-travel to the session location (per fast-travel rule)
- "Move a player" command stays staff-only

**Session location:**
- Most GM sessions in **temporary instanced rooms** the GM creates
- If in public, the public-means-public rule applies: anyone can
  participate, including non-story PCs
- Story-membership-scoped information visibility: in-story PCs see
  authored plot context; out-of-story participants see IC reality only

**NPC instantiation:**
- NPCs designed as part of the encounter, tied to the session
- Spawn timing is GM-controlled — "When X happens, then Y" flows
- GM has narrative-flow control (when NPCs appear, when checks fire)
  even though they don't have outcome control
- Example: GM gives entry pose → players Make Entrances → GM gives
  flavor → players respond → GM clicks "spawn thief" → spawn fires →
  players get authored notice check

**GM live UI surfaces:**
- Full story tree view (overall arc, current position)
- Current scenario / encounter / situation tree (immediate context)
- "Ready for next event" prompts when authored conditions met
- See success/failure history, see branching ahead

**GM authority during live session:**
- ✓ Apply check-difficulty modifiers (umpire role: +/- difficulty)
- ✓ Pose as NPCs (puppet)
- ✓ Narrate outcomes
- ✓ Emergency-author new branches when story tree doesn't cover
- ✗ Override roll outcomes
- ✗ Fiat-decide success / failure

## Cross-cutting systems surfaced

These are systems implied or named during the brainstorm. Each likely
needs its own design pass.

### Mission system (currently `not-started` on roadmap)

The thief example exposed how much hidden work the "missions:
not-started" line is doing. A mission has:

- **Society / organization origin** (Criminal Underworld of Luxen →
  Thief Guild)
- **NPC mission-giver** with IC location
- **Multiple authored approach options** (sleight-of-hand,
  flirt-as-distraction, grab-and-run) — likely uses existing
  Capability / Property / Application matching from `world.mechanics`
- **Bystander reaction trees** authored per mission (witness pop-ups
  with CK2-style filtered options)
- **Pre / post / aftermath state** — sub-mission spawning (the fence /
  ransom path), world-state mutation (crime ↑ in district)

The mission system is the load-bearing connective tissue between
PC daily play, society/organization gameplay, GM authoring, and
world-state evolution. **It deserves its own roadmap stub.**

### CK2-style authored choice menus

Pop-up choice menus with pre-authored options, filtered by character
traits (Path, covenant role, species, background, skill thresholds).
The pattern applies to **whichever character is the relevant actor at
a given moment** — primary actor, bystander, scene participant, or
story-event recipient. Bystanders are one application of the pattern,
not its scope.

**Applications:**

- **Primary-actor menus.** The thief at the merchant shop is offered
  authored approach options ("flirt to distract" / "sleight of hand"
  / "grab and run"), each with check rules and branch consequences.
  Different traits (high-Streetwise, noble class, specific covenant
  role) surface different options or unlock additional ones.
- **Bystander menus.** Witnesses to an action get reaction trees
  ("tip off the merchant" / "make up a cover story" / "call the
  guard" / "say nothing"), trait-filtered and fired post-action. Per
  the constrained-bystander hard rule, these are NOT freeform.
- **Scene-participant menus.** At a story beat, characters with the
  right trait may be offered a contextual choice (a noble PC gets an
  option to invoke privilege that a commoner PC doesn't see, etc.).
- **Story-event menus.** A character experiences a personal event
  (dream, encounter, premonition, omen) and is offered authored
  choices for how their character reacts; choices feed independent
  story progression.
- **Occupation / mission task menus.** Routine occupation tasks
  surface trait-filtered choices for how to perform them (a thief
  scout choosing a target, a healer selecting a patient).

**Common properties across all applications:**
- Authored options filtered by character traits
- Each option has authored consequences — check rules, branches,
  world-state mutations, IC narrative emits, follow-up event
  spawning
- "Do nothing / dismiss" always available; auto-dismissal on
  logout / hour
- Conflict-flavored bystander options fire post-action (preserves
  active player's agency)
- Pro-active-player options first-class (the bystander menu can
  include "cover for them," not only "report them")

Used by: missions (primary + bystander), scenes (participant +
bystander), public technique casts (caster + targets + bystanders),
social manipulations in crowds, GM-run events, personal stories
(independent progression), occupation tasks. **Pattern needs spec —
extremely high reuse value across the game.**

### Story-membership-scoped information visibility

Multiple stories can coexist in the same room. Each PC's story-context
visibility is per-PC, per-story. Public participants see IC reality
without contaminating context. **Schema: per-PC × per-story
membership relation, with content rendering filtered through it.**

### Room state tracking

Rooms have **stats** beyond static description: crime, order,
cleanliness, lighting (named); full taxonomy unknown. Stats:
- Drive ambient encounter generation
- Provide check-difficulty modifiers (infiltrating a "high-order"
  district is harder than infiltrating a "seedy" one)
- Update from aggregate PC actions over time
- May decay

Room-as-system: includes player-investable features (research
libraries, alchemy labs, sparring grounds, command centers, lairs,
traps, defenses). Players buy / install / advance / upgrade these.
**Needs its own roadmap stub.**

### World-state feedback loop

Aggregate PC actions → room state mutations → emergent NPC content.
Example: thief mission completes → merchant district crime ↑ → NPC
pickpockets spawn for non-society PCs walking through.

This is the engine that makes the world feel alive. **Needs spec.**

### Occupations system

PCs have IC occupations aside from adventuring (mentioned in passing,
not yet specced). Different tasks earn money. Performing tasks in
rooms produces subtle changes in the room state. Guilds / societies /
organizations dispatch missions tied to occupation. **Needs roadmap
stub — does not exist yet.**

### GM authoring tools (the "GM Workshop")

Beyond story trees, GMs need first-party (non-Django-admin) tools
for:
- **Story tree designer** — episodes, beats, branches; tree visualization
- **NPC / bestiary designer** — author antagonists; spawn at session
  time; tied to session
- **Item designer** — story-tied items; GM-tier-gated; staff version
  uncapped
- **Room / area builder** — same tool staff uses; supports session-
  specific rooms AND worldbuilding-for-its-own-sake areas; player-
  facing variant for home buying / construction (stylized conceit,
  not sterile)

**No Django admin for GMs ever.** Minimize even staff use of admin.

## Open questions

These were flagged during the brainstorm and remain unresolved:

- **Inbox rationalization** — pages, messengers, OOC mail, OOC
  notifications are 4 distinct surfaces. Do some collapse? What's the
  triage model?
- **Channel binding to IC org** — when's the noble house IC vs the
  noble-house chat OOC? Is it membership-derived?
- **Mission allocation vs mission giver** — pre-commit-and-go-do, or
  two systems?
- **Vote tweaking** — what's being voted on (kudos / story upvotes /
  GM feedback / all)?
- **Research allocation system** — does this exist or is it new?
- **Public scene backscroll length** — last N? Last hour? Since
  player's last logout?
- **Pets / retainers** — do they have their own behavior or are they
  passive objects?
- **Persona-name disclosure on arrival** (telnet: `PersonaName
  arrived.`) — what if you don't know the persona? Short-desc
  fallback?
- **Reward dispatch UX** — Phase 4 was cut and moved to Stories;
  what does "you got XP for this beat" look like to the player?
- **Player feedback / trust loop UX** — how do upvotes/feedback
  flow back to GMs? Tied to kudos system?
- **GM trust progression UX** — how does a GM know they leveled up?
  what does that look like?
- **CK2-style choice menu authoring** — how does a GM (or staff) build
  the authored option trees into their encounters / scenes / missions /
  story beats / event triggers? Same authoring tool across applications,
  or per-application surfaces?
- **NPC pickpocket spawning** (reactive emergent content) — does this
  use Scope 5.5 reactive layer? authored by who?
- **Room state full taxonomy** — what dimensions does a room track,
  beyond crime / order / cleanliness / lighting?
- **Room state update mechanics** — service function? decay curve?
  who triggers updates?
- **Society / organization hierarchy data model** — the Society →
  Organization → guild structure; how does it FK to mission origins?
- **Map / minimap design** — implied but not specced
- **Calendar UX** — combined with scene list per the discovery
  brainstorm; what does it look like?

## Roadmap implications

Updates to existing roadmap files this brainstorm implies:

- **`docs/roadmap/missions.md`** — currently `not-started`. The thief
  example shows it's load-bearing across multiple gameplay layers.
  Needs a real stub describing: society/organization origins, mission-
  giver pattern, authored approach options, bystander reaction trees,
  pre/post/aftermath state, sub-mission spawning, world-state feedback.
- **`docs/roadmap/rp-scenes.md`** — needs the three-tier presence model
  (absent / OOC-present / IC-in-scene) and the scene-vs-organic
  distinction explicitly documented if not already there.
- **`docs/roadmap/gm-system.md`** — Phase 5 (UI/dashboards) is
  deferred until after Stories. This brainstorm provides input for
  what the dashboard should look like (story tree viewer, current
  scenario tree, "ready for next event" prompts, NPC spawn controls).
  Probably worth adding a "GM Workshop authoring tools" subsection
  capturing: story tree designer, NPC designer, item designer, room
  builder.
- **`docs/roadmap/stories-gm.md`** — covers the backend; should
  reference the player-side stories panel design here, the three
  modes of player interaction (review / schedule / independent
  progression), and the IC-knowledge-gated visibility rule.
- **New: `docs/roadmap/rooms.md`** — the rooms-as-system layer
  (state tracking, player-investable features, defense/offense loops,
  room-stat-driven check difficulty) doesn't have a home in the
  current roadmap. This brainstorm's "rooms cluster" content is
  large enough to warrant its own stub.
- **New: `docs/roadmap/occupations.md`** — same; occupations were
  named as a real PC system but have no roadmap stub.
- **`docs/roadmap/ROADMAP.md`** — table needs new entries for
  rooms, occupations, missions (to match the elevated status).

## Next steps

In rough priority order:

1. **User review and amend this doc.** Capture is best-effort; the
   user should validate, correct, and add anything missed before
   we treat it as authoritative.
2. **Spec the missions system.** Currently `not-started`. Highest
   leverage because it's connective tissue across many other
   systems and the brainstorm exposed how much hidden work it does.
3. **Spec the CK2-style choice menu pattern.** Reusable across
   missions, scenes, public technique casts, story events, and
   occupation tasks (primary actors AND bystanders). The CK2
   event-tree model is well-understood and can become a single
   authoring surface that all consumer systems hook into.
4. **Spec the rooms-as-system layer.** Room state tracking, player-
   investable features, defense/offense loops.
5. **Spec the player stories panel.** Three interaction modes, IC-
   knowledge-gated visibility, GM-pause fallback.
6. **Audit roadmap files** for stale references that don't match
   the bedrock principles (e.g., any system that assumes invisible
   characters, account-attributed displays, or pose-text parsing).
7. **Plan the GM-loop integration test.** Once the above specs land,
   write `test_gm_pipeline.py` for `seed-and-integration-tests.md`
   Phase 2 covering the option B loop (existing Junior GM authors
   story → PCs join → session runs → bystander reactions → resolution
   → reward dispatch → feedback → trust delta).
