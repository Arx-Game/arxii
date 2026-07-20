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
- **Layer 2 (#2443, tracked separately)** — per-vow technique specialty.
- **Layer 3 (#2533, tracked separately)** — defense styles + gear substitution. This
  re-scopes ADR-0108's stat/gear pillars: `vow_stat_scaling_bonus` (`VowStatScaling`,
  keyed on `ModifierTarget`) is unaffected by this change and stays live; `vow_gear_scaling_bonus`
  (`VowGearScaling`, keyed on the retired `role_archetype` field) is short-circuited to a
  flat 0 by #2529 — it was already inert (never seeded in a real game) and keyed on the
  removed enum, so #2529 makes its actual runtime behavior explicit rather than leaving a
  latent bug. #2533 decides `VowGearScaling`'s real fate under the blend model.
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

> Status: accepted · Source: issue #2529 · Supersedes: ADR-0108 · Related: ADR-0055
> (sub-role specialization engine), ADR-0013 (no data migrations pre-production —
> narrow exception documented above), #2443/#2533/#2536 (Layers 2-4)
