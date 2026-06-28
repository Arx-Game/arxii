# Magic glossary

**Affinity**:
One of the three magical sources — Celestial, Primal, or Abyssal — modeled as a first-class domain entity with an optional link to the modifier system. Every Resonance belongs to one Affinity.

**Aura**:
A character's soul-state expressed as percentages across the three Affinities (celestial / primal / abyssal), constrained to sum to 100. Its presence is the derived gate for whether a character can work magic at all.

**Anima**:
A character's pool of magical energy (current / maximum). It governs the *safety* of casting, not access — magic can always be attempted, and a shortfall is paid from life force rather than blocking the cast.
_Avoid_: mana, magic points.

**Gift**:
A thematic collection of Techniques (e.g. Pyromancy, Shadow Majesty), associated with a set of Resonances. A character acquires a Gift to gain access to its Techniques.

**Major Gift**:
The Gift chosen at character creation — a character's primary magical calling (one per character). Same `Gift` model as a Minor Gift, distinguished by a `kind` column. (ADR-0050.)
_Avoid_: main gift.

**Minor Gift**:
A smaller, shared, more-easily-acquired Gift (e.g. Sight → Soulsight/Magesight; Travel → teleportation). **Species abilities (vampire/lycan/khati) are delivered as species-granted Minor Gifts.** (ADR-0050.)
_Avoid_: lesser gift, sub-gift.

**Gift-thread**:
The Thread woven into a Gift: its level sets the Gift's strength (more and stronger techniques) and its resonance sets the Gift's affinity. The costliest thread kind, because it gates magical power. (ADR-0051, ADR-0052.)

**Signature**:
A Thread woven into a single Technique, deepening just that technique above its Gift baseline; it carries its own resonance, which usually matches the Gift but may deliberately diverge (a *discordant signature*). (ADR-0056.)
_Avoid_: technique thread (use "signature").

**Specialization engine**:
The one shared `(entity × resonance) → customized capability` resolution (a generalization of covenant sub-role resolution): the same Gift down different Paths, or with a different resonance, yields different specialized techniques, derived on read. (ADR-0055.)

**Technique**:
A specific, player-created magical ability that lives within a Gift, carrying base intensity, control, and anima cost plus a style and effect type. It is the primary unit of magical action.
_Avoid_: power, spell, ability.

**Cantrip**:
A staff-curated starter Technique template selected during character creation; at CG finalization it produces a real Technique in the character's Gift. Its mechanical fields are hidden from the player.
_Avoid_: starter spell, baby technique (informal only).

**Intensity**:
The magnitude a caster *channels* — it drives cost and risk (anima cost, control mishap, Soulfray, Audere gating, resonance attribution). It is a base/static value on the Technique and is never reduced by a ward.

**Power**:
The effective magnitude the working carries into the world — it drives landed effect (damage budgets, condition severity, capability grants, clash progress). Power is always derived and recomputed each cast, never stored; it is seeded by intensity and then diverges.

**Control**:
A Technique's base safety/precision stat. High control reduces anima cost and eliminates mishap risk; it is the efficiency lever opposite intensity.

**Control Mishap**:
An additional consequence drawn when runtime intensity exceeds control (the `control_deficit`), routed through the consequence pool whose deficit band matches via `MishapPoolTier`. It never replaces the intended effect and never carries character-loss consequences.
_Avoid_: fumble, miscast.

**Soulfray**:
The magical strain a character accrues by casting while anima is depleted below the configured threshold ratio; severity scales with depletion and is tested against a resilience check. Tuned by the `SoulfrayConfig` singleton.

**Overburn**:
The condition where a cast's effective anima cost exceeds the available pool and the deficit is drawn from the caster's life force. Non-lethal encounters clamp cost to available anima instead.

**Penetration**:
The contest run when a Technique's Power meets a target's ward: a check against the ward's strength whose success level selects a factor from the authored ladder, applied as the `PENETRATION` stage of power derivation. Unwarded casts record no penetration entry.

**Ward**:
A target's defensive barrier (a positive `barrier_strength`) that Power must penetrate to land its effect. A ward reduces Power only; it must never reduce intensity.
_Avoid_: shield, barrier (as the canonical term).

**Backfire**:
The adverse consequence resolved when a cast is worked in an environment whose Affinity is OPPOSED to the caster's, drawing from the pairing's authored consequence pool. The opposed half of the resonance-environment interaction.

**Resonance Environment**:
The directed pairing between a caster's Affinity and the place's Affinity that conditions a cast — an ALIGNED pairing amplifies (and may grant a boon), an OPPOSED pairing backfires or defiles. Modeled as nine `AffinityInteraction` rows plus a tuning singleton.

**PowerLedger**:
The transient, never-persisted record of how a cast's Power was derived — an ordered list of entries each carrying a stage, source label, operation, amount, and running total. It is recomputed on every cast and surfaced for transparency.

**PowerStage**:
The enum naming each phase of power derivation in the ledger (base, flat modifier, multiplier, term, environment, reactive, combat pull, penetration, clamp). Each ledger entry is tagged with one stage.

**Thread**:
A per-character attachment owned by a CharacterSheet, anchored to exactly one anchor (Trait / Technique / Facet / relationship track / relationship capstone / covenant role / Mantle / Sanctum) and channeling a single Resonance. It accrues `developed_points` into a `level` and is the unit of long-term magical investment.

**Imbue**:
Spending Resonance currency to advance an existing Thread's developed points and level. Player-facing it is the Rite of Imbuing, a CEREMONY-kind Ritual completed by the `imbue` finisher.

**Weave**:
Creating a new Thread on an anchor the character is unlocked to weave on. Player-facing it is the Rite of Weaving, a CEREMONY-kind Ritual completed by the `weave` finisher.

**Ritual**:
An authored magical procedure dispatched in one of four ways: SERVICE (invokes a service-function path), FLOW (invokes a flow definition), CEREMONY (creates a pending effect a finisher command later consumes), or SCENE_ACTION (fires a check via a `RitualCheckConfig` sidecar). Performance converges on the single `perform_ritual` Action.

**Sanctum**:
A leveled room that serves as a Thread anchor via `target_sanctum_details`, capped at the sanctum feature's level × 10. A Sanctum-anchored Thread is pull-applicable (an in-sanctum boost) while the character is in the Sanctum's room.

**Mantle**:
A specific, storied, attunable ItemInstance in the world (a particular sword, amulet, banner) with authored progression levels. A character attunes by weaving a MANTLE-kind Thread anchored on the Mantle, gated on having cleared at least its first level; the Thread's level cannot exceed the character's max-cleared mantle level.

**Mage Scar**:
The player-facing name for a magical alteration imprinted on a character by magical exposure — a queued, tiered cosmetic-to-profound change carrying social, weakness, and resonance effects. Backend class and table names retain the `MagicalAlteration` naming.
_Avoid_: Magical Scar, Magical Alteration (as the player-facing name).

**Soul Tether**:
A bond mechanic between two PCs whose tuning lives in the `SoulTetherConfig` singleton, providing a rescue-and-resolution mechanism with a dramatic advancement/modifier surface (sineating, rescue rituals, stage-advance bonuses). The Sinner and Sineater are its two roles.

**Sineater**:
One of the two roles in a Soul Tether bond — the participant who performs Sineating actions on the bond. The complementary role is the Sinner.

**Dramatic Moment**:
A staff-tagged scene moment of an authored category that simultaneously grants a character Resonance and fires a renown award. Tags are immutable provenance records, capped per character per scene.

**Entry Flourish**:
A self-grant of Resonance triggered on a successful Entrance social action, where the entrant declares one of their claimed Resonances to broadcast. Idempotent per scene; it is the actor-side complement to the peer-side scene-entry endorsement.

**Endorsement**:
A peer's recognition of another character's pose (`PoseEndorsement`) that settles at the weekly tick to grant Resonance from a shared pot. A legitimate, live Resonance-award mechanism alongside scene-entry and style-presentation endorsements.

**Renown**:
The reputation/legend award fired alongside certain magical events (Dramatic Moments, Audere Majora crossings) via `fire_renown_award`. A live award mechanism; when an event's configured risk is NONE, no deed is minted.

**Effect palette**:
The seeded set of nine castable combat effects (`ensure_effect_palette_content()` in
`world/magic/effect_palette_content.py`): Summon Spirit, Aegis Field (force-field), Mirror
Ward (reflect), Phase Step (blink), Phase Jump (teleport), Barricade (obstacle), Ghostform
(incorporeal), Earthmeld (sink), Force Grip (telekinesis). Each is a full Technique + Condition
+ Flow + Trigger bundle wired idempotently via `get_or_create`. Handlers and adapters live in
`world/magic/services/effect_handlers.py`.

**Intangibility**:
The status of being untargetable in combat, conferred by a `ConditionInstance` whose
`ConditionCategory.grants_intangibility` is True. Checked by `is_untargetable(objectdb)` in
`world/conditions/services.py` at NPC targeting and PC AoE filter sites. Ghostform and
Earthmeld are the seeded intangibility conditions (#1584).
_Avoid_: invisible (use "intangible" when referring to the game-mechanical untargetable state)
