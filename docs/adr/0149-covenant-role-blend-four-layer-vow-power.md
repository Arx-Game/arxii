# Covenant-role combat identity is a SWORD/SHIELD/CROWN blend, not a single archetype — Layer 1 of a four-layer vow-power model

ADR-0108 modeled a character's engaged `CovenantRole` as picking exactly one combat
archetype (SWORD, SHIELD, or CROWN) via a single `CovenantRole.archetype` field, with
three power pillars keyed off it. That single-value field couldn't express hybrid roles
(a role that is meaningfully both a striker and a rallying voice) and coupled unrelated
concerns onto one enum column. #2529 replaces it: `CovenantRole` now carries three
`DecimalField` weights — `sword_weight` / `shield_weight` / `crown_weight` — that sum to
1 on primary roles (`blend_weight_for(axis)` delegates a sub-role's read to its parent,
per ADR-0055, so specialization can never drift the blend). This is **Layer 1** of a
four-layer vow-power model, the always-on floor every engaged vow contributes regardless
of what else is built on top:

- **Layer 1 (#2529, this ADR)** — the blend itself, plus an always-on baseline power
  term (`covenant_role_blend_power_term` in `world.magic.services.power_terms`):
  Σ over engaged roles of `total_thread_level_across_all_kinds(sheet) × blend_weight[technique.archetype_alignment] × CovenantRoleBlendConfig.multiplier_tenths / 10`.
  Kept as its own power-term provider (not folded into an existing term) so the
  contribution stays attributable in cast breakdowns — Layer 4's presentation contract
  (#2536) needs to show "this much came from your vow" as a distinct line. Every
  `Technique` gets a designer-authored `archetype_alignment` (SWORD/SHIELD/CROWN,
  migration-seeded from `effect_type.category`: attack→sword, defense→shield,
  else→crown) so the floor applies to every cast, not just role-granted techniques.
  Combat-side consumers (`ComboSlot.required_archetype`, shield-bearer targeting,
  `_participant_has_archetype`) now read `blend_weight_for(axis) > 0` instead of an
  equality check against a single enum value — a dual-axis role can satisfy either slot
  requirement, which a single-value `archetype` field could never do.
- **Layer 2 (#2443, shipped via #2546)** — per-vow technique specialty. See the
  "Amendment (2026-07-20, #2443 implementation)" section below.
- **Layer 3 (#2533, shipped)** — defense styles + gear substitution. This re-scopes
  ADR-0108's stat/gear pillars: `vow_stat_scaling_bonus` (`VowStatScaling`, keyed on
  `ModifierTarget`) is unaffected by this change and stays live; `vow_gear_scaling_bonus`
  (`VowGearScaling`, keyed on the retired `role_archetype` field) was short-circuited to a
  flat 0 by #2529 — it was already inert (never seeded in a real game) and keyed on the
  removed enum, so #2529 made its actual runtime behavior explicit rather than leaving a
  latent bug. #2533 removed `VowGearScaling` entirely and substituted the
  `CovenantRoleDefenseProfile` gear-additive fraction; see the "Amendment (2026-07-20,
  #2533 implementation)" section below.
- **Layer 4 (#2536, tracked separately)** — deterministic, situational perks. This is
  "the point of vows": when your situation comes up you really shine, deterministically
  and legibly. Layer 1's baseline is the floor that keeps every engaged vow relevant in
  every cast; Layer 4 is the fantasy on top. Vow power is meant to read as stark, and
  stacking multiple vows is encouraged rather than balanced against.

`ArchetypeActionScaling` (keyed `(action_key, role_archetype)`) is replaced by
`CovenantRoleActionScaling` (keyed `(covenant_role, action_key)`, natural-key content,
read via `covenant_role_action_scaling_bonus(character, action_key)` with anchor-role
normalization — rows and COVENANT_ROLE threads key on the parent role, engaged roles may
be resolved sub-roles). The renamed service sums `thread_level × multiplier` across
every engaged role's own row for the action, not a shared archetype-wide row — the same
per-role authoring granularity the blend weights give the power term. Seed content
authors interpose scaling on Bulwark (SHIELD) and rally scaling on Luminary (CROWN)
only; the Vanguard's old `cast_technique` row is not recreated because that scaling
moved to the Layer 1 power term. Authored `CovenantRole` blend values (and
`CovenantRoleActionScaling` rows) are lore-repo content (`NaturalKeyMixin`,
`content_export.py`'s `CONTENT_MODELS`) — arxii's own seeds carry only placeholder-pure
1/0/0 blends for its three canonical roles, not tuned hybrid values.

**Deliberate ADR-0013 exception:** both migrations (`covenants.0029`,
`magic.0115`) carry a `RunPython` data derivation — archetype→weights,
`effect_type.category`→`archetype_alignment`, and the old per-archetype scaling rows→
per-role rows — instead of the usual schema-only migration. Spec §7 calls this out
explicitly: a schema-only migration would have silently dropped every existing role's
combat identity and every seeded action-scaling row on deploy, which is worse than the
narrow, no-op-on-empty-database backfill actually shipped. This is a one-time transition
migration for pre-existing rows, not a precedent for routine data migrations.

**Rejected: keep the single-`archetype` enum and add a per-category modifier lookup
table.** A lookup table keyed on the enum still can't express a role that is
legitimately both SWORD and CROWN — it only adds more rows per enum value, not a second
axis. The blend is the structural fix; a modifier table on top of the old enum would
have been more machinery for the same ceiling.

This ADR supersedes ADR-0108. ADR-0108's stat/gear/technique-specialization framing is
superseded by the four-layer model above; its Capability-grant-wiring and
role-source-variant-resolution decisions are unaffected by #2529 and remain accurate.

> Status: accepted · amended 2026-07-20 (#2443, #2533) — verified against code · Source:
> issue #2529 · Supersedes: ADR-0108 · Related: ADR-0055 (sub-role specialization engine),
> ADR-0013 (no data migrations pre-production — narrow exception documented above),
> #2536 (Layer 4, remaining)

## Amendment (2026-07-20, #2443 implementation)

All claims below were verified against `src/world/magic/` and `src/world/covenants/` on
this branch before writing. **Layer 2 (per-vow technique specialty) has shipped.**

**Shared `TechniqueFunction` vocabulary — the decision worth recording.** Layer 2 needed
a fine-grained "what job does this technique do" label (damage buff, barrier, weaken,
fear, ...) to key specialty rows on — a technique's `archetype_alignment`
(SWORD/SHIELD/CROWN, Layer 1) is too coarse for "this vow rewards Weaken casts
specifically." Rather than authoring that vocabulary as free-text or duplicating it
per consumer, `TechniqueFunction` (`world.magic.constants`, a 12-value `TextChoices`:
`DAMAGE_BUFF_SELF`/`DAMAGE_BUFF_ALLY`/`DEFENSE_BUFF`/`BARRIER`/`CLEANSE`/`MOBILITY`/
`CHARM`/`DISTRACTION`/`FEAR`/`WEAKEN`/`PERCEPTION`/`CONCEALMENT`) is **one code-defined
vocabulary shared by two independent consumers**: Layer 2's per-vow specialty
(`CovenantRoleTechniqueSpecialty`, this ADR) and Layer 4's situational perks (#2536,
tracked separately). `TechniqueFunctionTag` (`world.magic.models.techniques`, NK
`(technique, function)`) is the content-authored join — *which* labels a technique
carries is lore-repo data (`CONTENT_MODELS`), same as `archetype_alignment`; the
vocabulary itself stays a code enum so both consumers can validate against stable,
extensible values instead of drifting free-text tags. Extending the list is a
deliberate one-line code change, same posture as `RoleArchetype`.

**`CovenantRoleTechniqueSpecialty`** (`world.covenants.models`, NK `(covenant_role,
function)`, `CONTENT_MODELS` content) carries `multiplier_tenths` (integer-tenths,
default 10 = ×1.0) and is valid on **both primary roles and sub-roles** — unlike the
Layer 1 blend weights, which sub-roles must leave at zero and delegate to the parent via
`blend_weight_for`, there is no such restriction here. `covenant_role_specialty_power_term`
(`world.magic.services.power_terms._PROVIDERS`) is the new always-on power-term provider:
for each engaged (resolved) role, it collects the anchor role's own specialty rows **plus**
the resolved sub-role's own rows when it differs, and sums
`total_thread_level_across_all_kinds(sheet) × row.multiplier_tenths / 10` over every row
matching one of the cast technique's `TechniqueFunctionTag`s. **Sub-role rows ADD to the
anchor's, they never replace it** — the opposite of the anchor-only normalization
`covenant_role_action_scaling_bonus` uses (Layer 1's action-scaling sibling). This is a
deliberate divergence, not an oversight: a specialized (promoted) member should read as
strictly more specialized than an unpromoted one, whereas action-scaling and the blend
weights are shape properties of the anchor role itself and would double-count if summed
across anchor+sub-role.

`CovenantRoleSerializer.technique_specialties` (prefetched via
`Prefetch(..., to_attr="cached_technique_specialties")`) exposes the rows on both the
`covenant_role` (resolved) and `anchor_role` (stored parent) fields of
`CharacterCovenantRoleSerializer`; the frontend's `specialtySummaryForMembership`
(`frontend/src/covenants/pages/CovenantDetailPage.tsx`) unions the two, summing the
anchor and resolved sub-role's `multiplier_tenths` on a same-function collision — matching
the power term's own summed payout, so the displayed chip is never an understatement.

## Amendment (2026-07-20, #2533 implementation)

All claims below were verified against `src/world/covenants/` and `src/world/combat/` on this
branch before writing.

**Layer 3 shipped: `DefenseStyle` vocabulary + the niche ruling.** `DefenseStyle`
(`TextChoices` in `world.covenants.constants`) is code-defined, not lore-repo content, per the
shared-vocabulary ruling: `GEAR_SOAK` (armor is the defense), `EVASION` (not being there is the
defense), `BARRIER` (force/warding is the defense). **The ratified niche ruling (2026-07-20):**
each style MUST have distinct shine-situations in Layer 4's (#2536) first perk set — a style
with no situation where it clearly outshines the other two is an authoring bug at the perk-set
level, not a code defect. Exact tuning numbers for those perks are secondary to that coverage
requirement; get the niche right first, balance the numbers after.

**Substitution rule.** `CovenantRoleDefenseProfile` (one row per `CovenantRole`, including
sub-roles; OneToOne to `CovenantRole`, NK `["covenant_role"]`, lore-repo content) carries
`style` (`DefenseStyle`) and `gear_additive_tenths` (default 10 = fully additive). Sub-role rows
are valid with no model-level parent/sub-role constraint — resolution is entirely a read-time
decision. `gear_additive_fraction(character)` (`world.covenants.services`) resolves, per engaged
role, the role's own profile when present else its anchor's, then takes the **MAX** fraction
across all engaged roles (gear is physical and counts once — the most gear-friendly engaged vow
governs; multi-vow stacking lives on the vow side, never by re-counting armor). No engaged role
has a profile anywhere → `Decimal(1)`, byte-identical to pre-#2533. `apply_equipped_armor_soak`
(`world.combat.services`, #1174) applies this fraction to the COMPATIBLE armor bucket **only,
once**, right after the role-compatibility split and before the compatible-additive/
incompatible-max blend:

    compat_soak = int(compat_soak * gear_additive_fraction(character))
    soak = compat_soak + max(incompat_physical, resonant)

The resonant pool and the incompatible-`max` branch are untouched by this change. Durability
still wears on every compatible piece whose (now-scaled) soak contributes — unchanged from
#1174. `ArmorSoakRoleGateTests` (the original #1174 suite) passes unmodified, which is the
enforced proof that the no-profile path stays byte-identical.

**Pillar fates.** `VowStatScaling` (keyed `(covenant_role, modifier_target)`, scales by
COVENANT_ROLE **thread level**) is Layer 3's stat-power pillar and was already unaffected by
the #2529 rework; #2533 additionally wires it onto the lore-repo content pipeline
(`NaturalKeyMixin`, `covenants.vowstatscaling` in `CONTENT_MODELS`), with a wiring-proof test
showing thread-level scaling aggregate into `equipment_walk_total` end-to-end. It stays the
**thread-scaled stark-power dial**: unlike `CovenantRoleBonus` (scales on raw character level,
peer-independent), a deepened vow makes its holder substantially stronger in a way ordinary
leveling does not — the mechanical heart of "solo darkness." `VowGearScaling` (formerly keyed
`(gear_archetype, role_archetype)` off the now-removed `CovenantRole.archetype` field, already
short-circuited to a flat 0 by #2529 because it was never seeded in a real game) is **removed
entirely** — model, migration (`covenants.0031_delete_vowgearscaling`), `vow_gear_scaling_bonus`,
and both its call sites in `world.mechanics.services` (`equipment_walk_total` and
`equipment_walk_total_unblended`). Its intended job — a per-archetype gear multiplier — is
subsumed by the single authored `gear_additive_tenths` fraction on
`CovenantRoleDefenseProfile`: one dial per role that substitutes for gear at the armor-soak
seam, rather than a full `(gear_archetype × role_archetype)` matrix layered on top of the blend
model. `CovenantRoleBonus` and `GearArchetypeCompatibility` also joined the lore-repo content
pipeline in this branch (`NaturalKeyMixin`, `CONTENT_MODELS`) — pure plumbing, no behavior
change.

**Rejected: re-key `VowGearScaling` onto the blend model instead of removing it.** A
per-`(gear_archetype, covenant_role)` multiplier table would let each role tune gear synergy
per archetype rather than with one flat fraction — but it never had real seed data even under
the old single-archetype key, and Layer 3's actual design need (a vow whose defense style isn't
gear should be able to substitute for gear, not fine-tune which gear archetype it likes) is
fully served by the coarser per-role fraction. The matrix would have been more authoring
surface for a need the simpler dial already meets.
