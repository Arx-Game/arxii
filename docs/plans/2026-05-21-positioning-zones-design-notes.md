# Positioning & Zones in Combat — Preliminary Design Notes

**Date:** 2026-05-21
**Status:** Pre-spec design notes. Pending cohort review before a full design spec is written.
**Position in sequence:** After the Clash spec; alongside or before the spatial-Challenges follow-up. Clash is intentionally positioning-independent so it can ship without waiting on this.

## Why this needs its own spec

Combat currently has no concept of *where* in an encounter participants are — every participant is "in the encounter," targetable by every other. That's been workable so far, but several upcoming concerns all share the same missing primitive:

- **Magical flight in combat.** Flying as a per-participant Property doesn't actually capture what's going on — the flier has moved into an aerial *region* that ground attacks can't reach.
- **Magical barriers separating combatants.** A barrier doesn't just apply a Property; it *partitions* the encounter into sides that can no longer freely target each other.
- **Magical movement as a narrative pillar.** Blink, teleport, acrobatic leap, phase-step, dimensional shift, wall-running, swing-from-chandelier — high-Path mages should feel mythic, and a flat encounter model can't carry that weight.
- **Floors, levels, obstacles.** Multi-level encounters (balcony / pit / catwalk / chasm) want to mean something tactically.
- **Spatial Challenges.** Avalanches, hazard zones, fires, anti-magic fields all want to occupy *some part* of the encounter, not just exist as opt-in toggles.
- **Beyond magic.** Battle scenes, open encounters, and missions will all eventually want positioning. The shape we pick affects them all.

Positioning is the kind of substrate where the wrong shape early creates years of regret. It warrants its own dedicated spec.

## How this surfaced

During the 2026-05-21 brainstorm on "what's left to make magic real," three families surfaced:

1. **Clash of Wills** — multi-round contested casting (its own spec, going first).
2. **Per-character state effects** — flight, invisibility, intangibility, etc. as Properties.
3. **Challenges-in-combat** — avalanches, fires, barriers, hazard zones.

Family 2 and Family 3 both leaned on positioning. Specifically: the proposed approach of "state effects are Properties on participants" works for invisibility / ethereal / soaked-in-flame, but breaks down for flight (which is fundamentally about being in a different region than ground attackers can reach). And barriers as "Challenges with structural side-effects" require partitioning the encounter, which needs a zone primitive to be coherent.

Decision: positioning gets its own spec. Clash ships first since it's positioning-independent. Cohort review happens in parallel so the positioning spec can move forward as soon as alignment is reached.

## Cross-cutting decisions already made in the brainstorm

These hold regardless of how positioning is shaped — they're context the positioning spec inherits:

- **Properties are the universal abstraction.** No gating logic ever references specific ability names ("requires_not(`Flight Spell`)" is wrong; "requires_not_target_property(`aerial`)" is right). Multiple sources can grant the same Property; multiple consumers reason about Properties uniformly. This applies to zone-edge Properties too — `gap_ranged_passable`, `barrier_permeable_to_holy`, etc.
- **Character POV is the source of truth for `get_player_actions`.** The system never surfaces options the character wouldn't consider. This applies to spatial reasoning: a character doesn't see "melee the flier" as an option because the character knows melee can't reach the air. Implementation: `get_player_actions` filters by zone reachability, the same way Family 2 filters by target Properties.
- **NPCs aren't piloted; their behavior is authored.** NPC threat-pool entries declare `target_required_properties` / `target_excluded_properties` and have authored fallback actions for "no eligible target." This extends to positioning: threat-pool entries will declare zone reachability requirements; a melee-only boss whose target is flying picks a fallback action (or a per-boss anti-flight contingency if authored).
- **Challenges are situational, not opt-in.** If you're in the scene, you're in the avalanche. Participants can act against Challenges (Approaches) or move themselves out of the affected area, but they don't get to "decide not to engage." This extends to spatial Challenges: being inside the fire-zone applies its Properties; moving zones is a movement action.

## Proposed zone model (sketch, subject to cohort review)

The shape gestured at in the brainstorm:

### Core primitives

- **`EncounterZone`** — a named region within an encounter. Examples: `"primary"` (the default auto-created zone), `"aerial"` (implicit when first participant becomes flying), `"balcony"`, `"the_pit"`, `"side_A"` / `"side_B"` (carved by a barrier).
- **`CombatParticipant.current_zone`** — FK to the zone the participant is currently in. Defaults to the encounter's primary zone.
- **`EncounterZoneEdge`** — adjacency between two zones, carrying Properties that determine what crosses (`gap_ranged_passable`, `gap_melee_impassable`, `barrier_impermeable_until_destroyed`, `requires_aerial_or_traversal_to_cross`, etc.).
- **Challenges** declare which zones they occupy or affect.

### Zone lifecycle

- Every encounter auto-creates a `"primary"` zone. Encounters with no spatial structure use only this zone — zero authoring burden for simple encounters.
- Encounters can declare additional zones at creation (authored: "this is a multi-level encounter with `balcony` and `floor`").
- Zones can be *implicit*: the first time a participant gains the `aerial` Property in an encounter, an `"aerial"` sub-zone is auto-created and the participant transitions into it. When they lose the Property, they transition back.
- Zones can be *dynamic*: a barrier-spawning Challenge carves the primary zone into `"side_A"` / `"side_B"`, partitioning the existing participants by author rule or by which side they happen to be on when it spawns. Destruction of the barrier merges the zones back.

### Movement

- Movement is a category of action: focused (high-cost, big transitions like teleport across the encounter), passive (low-cost, small repositioning), or free in some cases.
- Each zone transition is gated by **Movement Capabilities** on the actor + **edge Properties** between the zones:
  - `traversal` — general "I can get over/around stuff" (climbing the wall, leaping the gap)
  - `aerial` — flight; required for transitions into / out of aerial zones
  - `teleport` / `blink` — instantaneous transitions that bypass edges entirely
  - `acrobatics` — empowered movement; bypasses some edge restrictions
  - More as authored
- Forced movement: Challenges and NPC threat-pool entries can move participants involuntarily (avalanche pushes from `upper_path` to `buried`; a grapple drags a target into melee zone).

### Targeting

- Targeting checks consult: actor's zone + target's zone + edges between them + the action's requirements (`permits_target_property`, `requires_traversal_capability`, `requires_target_zone_property`).
- Same Property-driven abstraction as Family 2, just applied to inter-zone reasoning instead of per-participant Properties.

### Narrative integration

- Movement actions carry pose-grade narrative: a `teleport` action's pose differs fundamentally from an `acrobatics` action's pose, even when they accomplish the same zone change. Authoring captures this.
- Failed movement is its own narrative moment — a failed acrobatic leap (mishap rider) lands the participant in a worse zone or with a condition.

## Open questions for cohort discussion

These are the questions the cohort discussion should answer before the spec gets written:

1. **Do we want a rich positioning model at all?** The cohort may prefer to stay flat for longer and special-case barriers / flight rather than introduce zones as a first-class concept. This is the foundational call.
2. **Granularity.** If we do zones, how fine? Coarse named regions per encounter, or finer-grained sub-zones for tactical play?
3. **Encounter authoring burden.** How much does an encounter author have to declare up front (zones, edges) vs how much is implicit / dynamic?
4. **Cross-system reach.** Do battle scenes, missions, and open encounters use the same zone primitive, or do those systems get their own positioning model?
5. **Edge cases for implicit zones.** What happens when multiple participants are aerial — one shared aerial zone, or per-participant sub-zones? What about when a flier dispels and falls — graceful re-entry, or possible damage?
6. **Movement-action economy.** Movement as focused vs passive vs free is a major balance lever. Where does each kind of magical movement land?
7. **NPC threat-pattern integration.** How does NPC behavior degrade gracefully when authored threat-pool entries don't anticipate the zone state? (E.g., melee boss facing all-flying party.)
8. **Mass combat and battle scenes.** The cohort owns this space. Does a positioning primitive serve battle scenes, or do those want their own model?

## Why this matters narratively (in addition to mechanically)

The brainstorm called this out explicitly: blink, teleport, acrobatic leap, magically-empowered movement aren't just tactical conveniences — they're the moments where a high-Path mage feels different from a mundane combatant. Movement is one of the largest narrative palettes in combat. A positioning model that supports it well lets every mage's identity show in how they cross the room. A positioning model that doesn't will leave magical movement feeling no different than walking.

## Related work

- `docs/roadmap/combat.md` — combat overview, Phase 7 unified action interface, Clash entry under "What's Needed for MVP"
- `docs/roadmap/magic.md` — magic system overview, Scope 5.5 reactive layer, resonance-environment work
- `docs/architecture/resonance-environment-universal-path.md` — the recent precedent for "Properties drive behavior, not source names"
- `docs/architecture/unified-player-action.md` — `PlayerAction` / `ActionRef` / `get_player_actions` — the seam where zone-aware filtering will plug in

## Action items

- [ ] Cohort discussion: does positioning warrant its own first-class system in combat?
- [ ] If approved: this notes file becomes the input to a full design spec at `docs/superpowers/specs/YYYY-MM-DD-positioning-zones-design.md`
- [ ] After Clash spec ships and positioning spec is approved, sequence: positioning → Family 2 follow-up (flight-as-zone, etc.) → spatial Challenges (barriers, hazard zones, anti-magic fields)
