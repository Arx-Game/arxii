# Magic glossary

**Affinity**:
One of the three magical sources — Celestial, Primal, or Abyssal — modeled as a first-class domain entity with an optional link to the modifier system. Every Resonance belongs to one Affinity.

**Aura**:
A character's soul-state expressed as percentages across the three Affinities (celestial / primal / abyssal), constrained to sum to 100. Its presence is the derived gate for whether a character can work magic at all.

**Glimpse**:
The narrative of a character's first magical awakening — prose living on `CharacterAura.glimpse_story`. Authored at character creation via a guided, tag-driven flow (#2427) and revisable afterward through the "finish your Glimpse later" editor on the own-character sheet.

**Glimpse Tag**:
An authored catalog choice (`GlimpseTag`) on one of four narrative axes (`GlimpseTagAxis`: Tone, Consequence, Witness & Secrecy, Sensory & Discovery) that a player picks while composing their Glimpse. Content model, lore-repo authored — no factory-seeded catalog. Curated `GlimpseTagDistinctionSuggestion` rows link a tag to distinctions worth considering; the suggestion grants nothing. (#2427.)
_Avoid_: conflating with `Ritual.glimpse_eligible` — an unrelated ritual-gating flag (whether a `Ritual` may be performed pre-formal-training), not a tag from this catalog.

**Glimpse State**:
`CharacterAura.glimpse_state` — the NOT_STARTED/TAGS_ONLY/COMPLETE deferral cache tracking whether a character's Glimpse has any chosen tags and/or written prose. Maintained exclusively by `world.magic.services.glimpse`, mirroring the `CharacterDistinction.secret`/`.from_glimpse` FK-presence-is-state precedent — never written directly. (#2427.)

**Anima**:
A character's pool of magical energy (current / maximum). It governs the *safety* of casting, not access — magic can always be attempted, and a shortfall is paid from life force rather than blocking the cast.
_Avoid_: mana, magic points.

**Anima Check**:
The stat + skill pair every one of a character's casts rolls, chosen explicitly during the CG Gift stage (closing the Tradition → Gift → Technique funnel alongside a ritual name) instead of the old silent Willpower + highest-skill default. Embodied as the character's personal `RitualCheckConfig` on their `CharacterAnimaRitual`, provisioned by `provision_player_anima_ritual`. Deliberately **not** called "Signature" — ADR-0072 already owns that term for the Motif-flourish mechanic. (#2426, ADR-0136.)

**Gift**:
A thematic collection of Techniques (e.g. Pyromancy, Shadow Majesty), associated with a set of Resonances. A character acquires a Gift to gain access to its Techniques.

**Major Gift**:
The Gift chosen at character creation — a character's primary magical calling (one per character). Same `Gift` model as a Minor Gift, distinguished by a `kind` column. (ADR-0050.)
_Avoid_: main gift.

**Minor Gift**:
A smaller, shared, more-easily-acquired Gift (e.g. Sight → Soulsight/Magesight; Travel → teleportation). **Species abilities (vampire/lycan/khati) are delivered as species-granted Minor Gifts.** (ADR-0050.)
_Avoid_: lesser gift, sub-gift.

**Tradition**:
A school of magical practice. Every character has exactly one — the self-taught `Unbound` tradition is a real Tradition row, not a NULL special-case. A Tradition gates which Gifts are pickable at CG via `TraditionGiftGrant` rows (tradition × gift, plus a `signature_techniques` M2M of that tradition's unique extras for the gift); non-Unbound traditions are further gated at tradition selection by `BeginningTradition.required_distinction`. Organizations may serve as a Tradition's teaching structure — many orgs per tradition (chapters, academies) — via the nullable `Organization.tradition` FK (specific→general, ADR-0010; `Tradition` itself stays dependency-free). (#2426, ADR-0136.)
Membership in play is `CharacterTradition`, history-preserving via `left_at` (nullable — one active row per character, enforced by a partial-unique constraint mirroring `societies.OrganizationMembership.left_at`). `join_tradition(sheet, tradition, *, via_membership=None)` ends the active row and creates a new one (wired from accepting an `OrganizationMembershipOffer` on a tradition's teaching org, #2441 ruling 1); `leave_tradition(sheet)` stamps `left_at` with no replacement, no live caller yet. Learned techniques are never revoked on a switch ("learned is learned" — only future signature-list *access* changes). See "Unbound (drawback)" below for what auto-attaches/sheds on switch.

**Tradition Training**:
A rankable distinction that scales a character's CG starting-technique-pick budget: baseline (Unbound, no distinction) is 1 pick, and each rank of Tradition Training adds +1 (rank 1 → 2 picks, rank 2 → 3). Data-modeled as a `ModifierTarget` ("Starting Technique Picks") + `DistinctionEffect`, read at draft time via the existing `CharacterDraft._get_distinction_bonus` — no new mechanism. Real (non-Unbound) traditions require this distinction at CG via `BeginningTradition.required_distinction`. (#2426, ADR-0136.)

**Unbound (drawback)**:
The `Distinction` (slug `unbound`, negative `cost_per_rank`) auto-carried by picking the Unbound Tradition — CG's own `select_tradition` endpoint auto-adds it to the draft when missing, a one-off exception to the normal "must already hold the required distinction first" gate (Orphaned Tradition keeps that normal gate; Unbound is CG's tradition-agnostic default and must stay completable with zero manual steps). Its `DistinctionEffect` carries a +50% surcharge on the `magic_learning_ap_cost` `ModifierTarget`: self-taught mages pay more Action Points to learn techniques (`charge_and_learn`'s AP scale, both front doors) — TIME, not power; resonance is untouched. Shed automatically on joining a living Tradition (`join_tradition`), re-applied on leaving one (`leave_tradition`) — the underlying `CharacterModifier` cascade-deletes with the distinction, so the surcharge tracks membership with no separate cleanup. (#2441, #2442.)
_Avoid_: conflating this with the `Unbound` Tradition row itself (see "Tradition" above) — the Tradition is the school-of-practice entity; this is the drawback distinction a traditionless character carries while in it.

**Gift-thread**:
The Thread woven into a Gift: its level sets the Gift's strength (more and stronger techniques) and its resonance sets the Gift's affinity. The costliest thread kind, because it gates magical power. (ADR-0051, ADR-0052.)

**Signature**:
A Thread woven into a single Technique, deepening just that technique above its Gift baseline. The character applies their Motif to the signed technique via a `SignatureMotifBonus` — an ADDITIVE flourish (intensity delta, conditions, cosmetic prose) that fires alongside the technique at cast time. The bonus is NOT a `TechniqueVariant` and does NOT change the technique's identity. (ADR-0072, supersedes ADR-0056.)
_Avoid_: technique thread (use "signature"); discordant signature (the resonance-divergence model was closed by ADR-0072).

**Signature Motif Bonus**:
The staff-authored catalog row (`SignatureMotifBonus`) that a player attaches to a TECHNIQUE-kind Thread to sign that technique. Gated on the character's Motif (facet and/or resonance). Carries `flat_intensity_delta`, `narrative_snippet`, and payload child rows (capability grants, damage profiles, applied conditions) sharing the `Abstract*` bases from `models/techniques.py`. (ADR-0072, #1582.)
_Avoid_: signature variant, signature specialization (it is additive, not a variant form).

**Specialization engine**:
The one shared `(entity × resonance) → customized capability` resolution (a generalization of covenant sub-role resolution): the same Gift down different Paths, or with a different resonance, yields different specialized techniques, derived on read. (ADR-0055.)

**Technique**:
A specific magical ability that lives within a Gift, carrying base intensity, control, and anima cost plus a style and effect type. It is the primary unit of magical action. At character creation, players pick 1 + `Tradition Training` bonus Techniques from a staff-authored catalog (their Path × Gift's availability pool, plus their Tradition's signature extras) rather than authoring one; personalization (custom flavor, signature variants) is a level-3+ thread mechanic, not CG. (#2426, ADR-0136.) The rest of a Gift's pool is filled in **play**, not at CG: `charge_and_learn` (`services/gift_acquisition.py`) is the one shared charge+acquire seam behind both player-to-player `TechniqueTeachingOffer` accepts and the Academy's `TRAIN` offers (`world.npc_services`) — the latter additionally spend one Golden Hare per technique (see `currency` glossary), gated on the learner's Academy entrance obligation being settled. Reaching character level 2 requires knowing ≥3 techniques of the character's major Gift (`progression.MajorGiftTechniqueRequirement`, #2440 ruling 4). (#2428, #2440, ADR-0137.)
_Avoid_: power, spell, ability; **cantrip** (retired #2426 — see ADR-0136; CG used to mint a personal Technique from a staff-curated `Cantrip` template, now it links to catalog `Technique` rows directly, no per-character row created).

**Technique Function**:
The fine-grained "what job does this technique do" vocabulary — a code-defined `TechniqueFunction` `TextChoices` (damage buff, barrier, cleanse, weaken, fear, ...) distinct from the coarser SWORD/SHIELD/CROWN `archetype_alignment`. One shared vocabulary consumed by two independent systems: `covenants`' per-vow technique specialty (#2443) and situational perks (#2536). `TechniqueFunctionTag` (NK `(technique, function)`) is the content-authored join recording which labels a given Technique carries — a lore-repo authoring decision, while the vocabulary itself stays a code enum so both consumers validate against stable values. (#2443, ADR-0149 amendment.)
_Avoid_: conflating with `archetype_alignment`/the SWORD-SHIELD-CROWN blend axis (Layer 1) — Technique Function is the finer-grained Layer 2/4 vocabulary, not a replacement for it.

**Consequence-Pool Catalog**:
The curated set of `ConsequencePool` rows selectable when authoring a technique — structurally, the single-depth children of the base "Magic: Technique Cast" pool (`ConsequencePool.parent`). Each catalog entry has a matching `ActionTemplate` sharing the base template's `check_type`/`pipeline`/`target_type`; only `consequence_pool` differs. (#1320.) CG no longer has an "Outcome Flavor" pick from this catalog — dropped in #2426 (ADR-0136) because it only worked by baking a pool into a per-character technique row, which shared catalog techniques make impossible without new cast-path machinery.

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

**Style Binding**:
A player-authored link (`MotifResonanceStyle`) between a staff-curated `Style` word
(`world.items.Style`) and one of the character's own claimed motif resonances —
individualized, so two characters binding the same `Style` name attach it to
different resonances. Capped at 3 bindings per resonance. Authored via
`bind_motif_style`/`unbind_motif_style` (`services/motif_style.py`), telnet
`CmdMotif`, or the web `MotifStyleViewSet`; consumed by the coherence walker and the
peer style-presentation endorsement. (#2030.)
_Avoid_: facet binding (a Facet is a different, hierarchical imagery axis).

**Mantle**:
A specific, storied, attunable ItemInstance in the world (a particular sword, amulet, banner) with authored progression levels. A character attunes by weaving a MANTLE-kind Thread anchored on the Mantle, gated on having cleared at least its first level; the Thread's level cannot exceed the character's max-cleared mantle level.

**Touchstone**:
A resonance-tied `ItemInstance` a character has personally attuned via `attune_touchstone` (requires holding it, an unset `attuned_to_character_sheet`, and having claimed the item's `tied_resonance`). Attunement does not consume the item. Touchstone-mode component/item requirements (`RitualComponentRequirement`, `ItemRequirement`) match any attuned item whose `ResonanceTier` meets a floor, rather than one fixed catalog item — see ADR-0087.

**Portal Anchor Kind** (#2222, ADR-0121):
A staff-authored catalog row (`PortalAnchorKind`) naming a medium of portal travel (e.g.
"Mirror") plus its narrative arrival/departure verb phrases. A `Technique.travel_anchor_kind`
FK marks a technique as a travel-mode technique through that medium — many gifts can each
unlock travel through the same anchor kind, or their own distinct one.
_Avoid_: anchor type, portal kind.

**Portal Anchor** (#2222, ADR-0121):
A concrete, installed instance (`PortalAnchor`) of a Portal Anchor Kind in one specific room —
"a tall silvered mirror" is a Mirror-kind anchor. Stackable: a room may hold more than one
active anchor of different kinds at once (one active anchor per kind per room, enforced by a
partial unique constraint). `is_network_open` gates whether strangers may travel to it; a
locked anchor is still reachable by anyone with owner/tenant standing at its room. Dissolved
(never hard-deleted) via `dissolved_at`, mirroring Room Feature dissolution. Explicitly NOT a
`RoomFeatureInstance` (one-feature-per-room cardinality is wrong for a stackable network node)
or a `RoomDecoration` (wrong domain — amenity/affinity dressing, not technique-gated travel
connectivity) — see ADR-0121.
_Avoid_: portal, waypoint, travel node.

**Travel-Mode Technique** (#2222):
A `Technique` whose `travel_anchor_kind` FK is set — knowing it lets a character portal-travel
through anchors of that kind. A character "knows" an anchor kind for travel purposes by
knowing any one `CharacterTechnique` bound to it; the technique's own `anima_cost` is the
per-use cost (0 for the seeded "Mirrorwalk" starter). Distinct from a technique's ordinary
combat/social effect — a travel-mode technique's payload IS the instant relocation, resolved
by `world.magic.services.portal_travel.perform_portal_travel`, not a damage/condition/
capability-grant row.
_Avoid_: portal technique, teleport spell.

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

**Technique Entrance** (#2183):
An Entrance whose check IS a technique cast (`enter <technique>[=<target>]` / the web `EntranceTechniqueAttachment`) — the cast's own success level substitutes for the entrance's social roll entirely, one check driving every downstream consequence (see ADR-0113). Distinct from **Entry Flourish** (the resonance self-grant this success level unlocks alongside), **Dramatic Moment** (the GM-tagged reward category a qualifying entrance may *suggest*, never auto-grant), and **Dramatic Surge** (`world/combat/AGENT_GLOSSARY.md` — a different system entirely: an intensity-modifier jump at a combat beat, not a recognition/reward mechanism). A qualifying success creates a `DramaticMomentSuggestion` — a PENDING, GM-facing suggestion (not an automatic tag) — via `maybe_suggest_dramatic_moments`, resolved by `resolve_dramatic_moment_suggestion` (confirm mints a real `DramaticMomentTag`; dismiss closes it with no reward).
_Avoid_: technique-cast entrance (use "Technique Entrance"); auto-tag, auto-grant (recognition is never automatic — see ADR-0113).

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

**Target-Aware Pull**:
A thread pull whose numeric payload can be modulated by the live target the pull's
action is directed at, via `apply_target_modulation` (#1831). Distinct from an
ephemeral/untargeted pull, which always resolves unmodulated.
_Avoid_: targeted pull (ambiguous with targeting a technique, not a pull).

**Pull Target Modulation**:
The per-`target_kind` extension seam (`apply_target_modulation`,
`world/magic/services/pull_modulation.py`) that `resolve_pull_effects` calls for every
numeric-payload pull effect row, dispatching on `thread.target_kind`. A no-op unless a
rule is registered for that kind. Two rules registered: COVENANT_ROLE (Court Regard
Modulation, below) and RELATIONSHIP_TRACK (Relationship Bond Pull Modulation, below).
(#1831, #1849.)

**Regard Polarity**:
`ThreadPullEffect.regard_polarity` (`RegardPolarity`: OFFENSIVE / PROTECTIVE / NEUTRAL) —
authored on a pull-effect row to say how Court-role (COVENANT_ROLE) pull modulation
responds to the Court leader's signed `NpcRegard` for the live target: OFFENSIVE is
empowered by negative regard (a disfavored target), PROTECTIVE by positive regard (a
favored target), NEUTRAL by either nonzero sign. Ignored for every other `target_kind`.
(#1831.)

**Court Regard Modulation**:
The only `Pull Target Modulation` rule wired today (`court_regard_modulation`,
`world/magic/services/pull_modulation_court.py`): empowers a COVENANT_ROLE thread pull
by the covenant leader's signed `NpcRegard` (#1717) for the live target, sign-directed
by the effect row's `Regard Polarity`. The combat-UI picker
(`compute_thread_applicability`) surfaces `InapplicabilityReason.COURT_LEADER_NO_STAKE`
when no candidate effect on the thread would ever be empowered against the given target.
(#1831.)

**Relationship Bond Pull Modulation** (#1849):
The `RELATIONSHIP_TRACK` sibling to Court Regard Modulation
(`relationship_bond_modulation`, `world/magic/services/pull_modulation_relationship.py`):
empowers a relationship-thread pull by the owner's own bond strength
(`CharacterRelationship.developed_absolute_value`) to the thread's threaded person
(`Thread.target_relationship_track.relationship.target`), when the live target IS
that person or holds a net-negative (`affection < 0`) relationship toward them
(they're "threatening" them). Deliberately **no** `Regard Polarity` gate — unlike
Court's NPC-preference sign-matching, this rewards any PC-to-PC relationship
investment unconditionally (rival or lover alike). Magnitude is a staff-tunable
saturating curve (`RelationshipBondPullTuning`), not a fixed ratio, since
`CharacterRelationship` values are unbounded (unlike `NpcRegard`'s `0..REGARD_MAX`).
The combat-UI picker surfaces `InapplicabilityReason.RELATIONSHIP_NO_STAKE`.
_Avoid_: regard bonus, court modulation (different mechanic, different narrative
purpose — see Court Regard Modulation above).

**Relationship Trigger Check**:
`_relationship_pull_would_trigger(x_sheet, y_sheet)`
(`world/magic/services/pull_modulation_relationship.py`) — shared between
`relationship_bond_modulation` and the picker's
`_relationship_pull_would_have_effect`, so the trigger rule can't diverge between
the two call sites (mirrors `_regard_polarity_matches`'s role for Court
modulation). True when `x_sheet == y_sheet` (direct) or `x_sheet` holds an active,
mutually-consented, net-negative `CharacterRelationship` toward `y_sheet`
(indirect — "threatening"). (#1849.)

**Bounded Percent Lane** (#2643, ADR-0158):
A percent-buff/debuff mechanic whose SUMMED contribution is clamped to a flat cap
before it multiplies damage — the EQ2 lane guard against percent sources
compounding into an unbounded spike. Two live lanes: the `team_damage_percent`
lane (Uplift, ally-side, `TEAM_BUFF_LANE_CAP_PERCENT`) and the
`ConditionDamageInteraction.damage_modifier_percent` lane (Undermine, enemy-side,
`ENEMY_LANE_CAP_PERCENT`). Any future percent lane reuses one of these two rather
than adding a third.
_Avoid_: "damage multiplier stack" (ambiguous with the unbounded legacy
`power_multiplier` target, which this deliberately does NOT fold into).

**Vow-Keyed Stacking** (#2643, ADR-0158):
Diminishing returns applied WITHIN one vow's contributions to the bounded
team-damage-percent lane (100/50/25/25%... descending), while distinct vows stack
FULLY against each other — `world.magic.services.techniques
.vow_keyed_diminished_total`, grouped by `conditions.ConditionInstance.source_vow`.
Mechanically rewards multi-vow engagement over single-vow spam, echoing the
four-layer vow-power model's own incentive (ADR-0149).

**Execute** (#2643):
A damage-profile authored ramp (`AbstractDamageProfile
.execute_missing_health_multiplier`) that scales a landing hit's damage up as the
TARGET's PRE-hit health runs low — `1 + multiplier * missing_health_fraction`,
never computed off post-hit health (which would be self-referential). Strike-family
techniques opt in; default 0 elsewhere.

_Avoid_: invisible (use "intangible" when referring to the game-mechanical untargetable state)
