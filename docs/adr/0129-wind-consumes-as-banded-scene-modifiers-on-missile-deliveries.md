# Wind consumes as banded SCENE check modifiers on missile deliveries only

The WIND exposure axis (`world.locations.services.felt_exposure`, `StatKey.WIND`, #1522)
gets its first combat consumer (#1555): `wind_penalty(felt) -> int` maps felt WIND to one of
four authored bands — CALM (<15) → 0, BREEZY (15-39) → -5, WINDY (40-69) → -10, GALE (70+) →
-20 — and that value is injected as a `ModifierContribution(source_kind=SCENE,
label="Wind", ...)` into `collect_check_modifiers`, exactly like every other check
contribution (effort, pull, bond, charge). It only touches missile-classified attacks: on
the PC offense side (`CombatTechniqueResolver._roll_check`), the penalty applies when the
attacker's strongest equipped weapon (the same `_select_equipped_weapon` pick the damage
path uses) has `gear_archetype` RANGED or THROWN — melee and lance attacks skip the
`felt_exposure` lookup entirely. On the NPC side, the symmetric case ("the gale that ruins
your shot ruins theirs") adds the same-magnitude *positive* contribution to the PC's
defense roll when the attacking `ThreatPoolEntry.delivery` is MISSILE
(`resolve_npc_attack`); flat `base_damage` entries with no defense check are structurally
untouched, since the wind seam lives only inside the defense-roll path. Three alternatives
were rejected: **per-point raw modifier** (felt WIND fed straight into the roll as a 1:1
penalty) — illegible, since a player can't reason about "37 wind" the way they can about
"windy"; **a hard gale inhibitor** (a boolean immunity/block on missile attacks above the
GALE threshold) — rejected as a different pattern (hard gates belong to
`hazard_is_covered`-style shelter checks, not a graded combat penalty) that would make gale
weather swing missile combat from "harder" to "impossible," out of proportion to every other
banded exposure effect; and **an anima surcharge** (folding wind into spell-cast anima cost
instead of the check roll) — rejected because it punishes casters for weather they didn't
choose and only reaches magical missile techniques, missing mundane bows/thrown weapons
entirely.

> Status: accepted · Source: issue #1555 · Related: ADR-0010 (FK/consumer direction), #1522
> (WIND exposure axis provider)
