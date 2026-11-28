# Magic App

The magic system for Arx II. Power flows from identity and connection.

## Core Concepts

- **Affinity**: Three magical sources (Celestial, Primal, Abyssal) - proper domain models with optional ModifierTarget link
- **Aura**: A character's soul-state as percentages across affinities (their lifetime resonance); who they ARE is `CharacterAuraShare.settled_percent` per affinity, and growing another affinity past it makes them **unsettled** (#5123, ADR-5123-B)
- **Resonance**: Style tags that define magical identity - proper domain models with FK to Affinity and optional ModifierTarget link
- **Motif**: Character-level magical aesthetic containing resonances and facets
- **Facet**: Flat vocabulary of imagery/symbolism (Wolf, Silk, Scythe — 2026-09-11 ruling, #3776) assigned to resonances
- **Threads**: Per-character attachments anchored to a trait/technique/facet/
  relationship-track/relationship-capstone/covenant-role/gift/mantle/sanctum, one thread per
  anchor. Each Thread holds one or more Resonances (currency) on its `ThreadResonance` rows
  (the cumulative amount of each ever imbued; `Thread.resonance` is the denormalized LEADING
  one, written only by `refresh_leading_resonance`, #5123, ADR-5123-A) and accrues
  `developed_points` → `level` via the Imbuing ritual. The legacy 5-axis Thread family was removed and replaced
  in Phase 4 of the resonance pivot.
- **Resonance currency**: `CharacterResonance.balance` is spendable currency
  earned via `grant_resonance` (Spec C surfaces will write here) and spent
  via `spend_resonance_for_imbuing(sheet, thread, resonance, amount)` (spends that held
  resonance, grows the thread's row for it, advances Thread level — also charges a flat
  AP cost, with the Unbound +50% surcharge applying via the same
  `magic_learning_ap_cost` modifier as technique learning, #2467) or
  `spend_resonance_for_pull` (low-level spend called by the pull helpers).
  `lifetime_earned` is monotonic audit. **Thread pulls are declaration modifiers**
  on `cast`/`clash`, or declared on their own for the round (`combat_pull`, #5066), or
  committed by the automatic defensive pull (`world/combat/services/auto_pull.py`). Every
  pulled thread pays its tier's resonance and anima (`threads.pull_cost_totals`, #5066) from
  its **paying resonance**: the one the player names per thread (`payers`, thread id to
  resonance id; telnet `pull=<thread>:<resonance>`), else the thread's leading one (#5123).
  The payer is stored on the pull's through rows (`CombatPullThread`, `ScenePullThread`),
  resolved from the wire by `services/pull_payers.resolve_pull_payers` (a held resonance
  only, which need not have a row on the thread), and a pull boosts only the uses its
  threads relate to (`round_pull_bonus`). The perks are the payer's (see "Pull perks by
  payer" below). The shared commit path
  lives in `world/combat/pull_helpers.py`:
  `commit_combat_pull` (combat contexts), `build_cast_pull_declaration`,
  `resolve_pull_from_kwargs`. Non-combat cast uses `request_technique_cast(cast_pull=…)`.
  Preview: `preview_resonance_pull` (`POST /api/magic/thread-pull-preview/`): read-only;
  takes `payers` and returns `per_thread`: every resonance the character holds as a
  `PayerOption` (cost, balance, affordable, the perks it would resolve with and the
  `level_read`) for each pulled thread.
  A tier with no authored `ThreadPullCost` row is refused with "That pull tier is not
  available yet." on preview, cast and commit: `get_pull_cost` raises `PullTierNotAvailable`
  (an `InvalidImbueAmount`) and `build_cast_pull_declaration` checks it up front.
- **Burning resonance (#4736)**: a pull may also burn resonance as a Strain option
  (`services/burn.py`: `resolve_resonance_burn`, `value_burn`, `preview_burn`). The burn rides the
  pull and is debited with it in `spend_resonance_for_pull(burn=)`; a combat burn is resolved and
  valued at declaration, stored on `CombatPull`, and strains only the action it was declared with
  (`use_technique(combat_burn_for=)`). A hasty fall (Abyssal acting aura burning another affinity)
  converts at the Fall pair rate and corrupts at `CorruptionConfig.hasty_fall_multiplier`.
  `docs/systems/magic.md` "Burning Resonance as a Strain Option" has the full flow.
- **ThreadWeaving**: Acquisition layer. `ThreadWeavingUnlock` is the authored
  catalog (per anchor scope); `CharacterThreadWeavingUnlock` is the per-character
  purchase record; `ThreadWeavingTeachingOffer` is the teacher-facing offer
  (mirrors `CodexTeachingOffer`).
- **Ritual**: Authored magical procedures with four dispatch kinds —
  `execution_kind=SERVICE` invokes a registered service function path;
  `execution_kind=FLOW` invokes a `FlowDefinition`;
  `execution_kind=CEREMONY` creates a `PendingRitualEffect` that a finisher
  command (`weave`, `imbue`) later consumes to complete the ritual;
  `execution_kind=SCENE_ACTION` fires a check via `RitualCheckConfig`.
  The two canonical CEREMONY rituals are **Rite of Weaving** (finisher:
  `CmdWeaveThread` / `WeaveThreadAction`) and **Rite of Imbuing** (finisher:
  `CmdImbue` / `ImbueThreadAction`).
  Ritual *performance* is the `perform_ritual` `Action`
  (`actions/definitions/ritual.py`, key `"perform_ritual"`) — both telnet
  (`commands.ritual.CmdRitual`) and the web (`RitualPerformView`) converge on
  `PerformRitualAction.run()` (#1331). There is no standalone executor; the
  action catches the ritual-surface exceptions (`RitualComponentError`,
  `ResonanceInsufficient`, `AnchorCapExceeded`, `InvalidImbueAmount`,
  `XPInsufficient`) and returns a failure `ActionResult` whose `message` the
  view maps to HTTP 400.
- **PendingRitualEffect**: In-progress CEREMONY record. Created by
  `PerformRitualAction` when `execution_kind=CEREMONY`; unique per
  `(character, ritual)`. Consumed (deleted) by the finisher action on success.
  Fields: `character` (FK → `CharacterSheet`), `ritual` (FK → `Ritual`),
  `created_at`. If a finisher fires without a matching `PendingRitualEffect` the
  action returns a failure result — no side effects.

## Models

### Domain Models
- `Affinity` - Three magical affinities (Celestial, Primal, Abyssal); `mechanics.ModifierTarget.target_affinity` is the OneToOne that points at it (reverse accessor `modifier_target`)
- `Resonance` - Magical identity tags with FK to Affinity, optional opposite (self OneToOne); `mechanics.ModifierTarget.target_resonance` is the OneToOne that points at it (reverse accessor `modifier_target`)

### Character State
- `CharacterAura.cached_glimpse_tags` (#5193) - the aura's chosen glimpse tags as a `PrunedCachedProperty`, read by the character sheet and cleared by `set_glimpse_tags` and by a `CharacterGlimpseTag` row's save or delete; any new writer of those rows clears it too. `GlimpseTag.stands_alone` marks a tag that cannot be chosen with another tag of its axis (`set_glimpse_tags` refuses it, `keep_stand_alone` reduces a list)
- `CharacterAura` - A character's aura; the affinity percentages are `CharacterAuraShare` rows (one per affinity, read through `cached_shares` / `percent_for(affinity)` / `dominant_affinity`). Each share carries `percent` (the aura now, from lifetime resonance via `recompute_aura`) and `settled_percent` (who the character IS, 0-100, summing to 100 once set; #5123): written at creation (`set_settled_shares`, weights plus the Glimpse nudge) and by `accept_aura_change`. The main affinity is the largest `settled_percent` (a tie goes to Primal, then to the lowest affinity id, in `_main_affinity` and in `CharacterAura.dominant_affinity` alike, #5231). `set_aura_shares` keeps a share row whose `settled_percent` is above zero even at `percent` 0, so a faded streak's line survives
- `CharacterResonance` - Per-character per-resonance row. Identity anchor AND
  spendable currency bucket. Fields: `character_sheet` FK, `resonance` FK,
  `balance` (spendable), `lifetime_earned` (monotonic audit), `claimed_at`,
  `flavor_text`, `lifetime_helped` (the Sineater's monotonic Sineating counter; sizes their
  resistance), `corruption_current` / `corruption_lifetime`. (`mire_lifetime`, #5123's marker of
  the part of a Sineater's lifetime taken from the Mire, was removed in #5177: the Mire is
  corruption now, held in `MireHolding`.) Unified per Spec A §2.2: the old `scope`/`strength`/`is_active`
  shape was dropped; row existence replaces `is_active`.
- `CharacterAnima` - Magical resource (anima) tracking
- `ANIMA_BANDS` / `anima_band_for(current, maximum)` (`constants.py`, #1446) - Qualitative
  anima vocabulary (PLACEHOLDER labels pending Apostate rewrite) mirroring
  `vitals.constants.WOUND_DESCRIPTIONS`; `CharacterAnimaSerializer.band` surfaces it, shared
  by the web Status tab and the `sheet/status` telnet section

### Gifts & Techniques
- `Gift` - Thematic collections of magical techniques (M2M to Resonance — a default only: it limits no Gift thread, any held resonance can be woven, imbued or retuned into one; the cast reads the character's GIFT-thread resonance via `gift_resonances_for`, ADR-0052). Carries a `kind` column (`GiftKind`: `MAJOR` = the one CG-chosen gift, `MINOR` = shared/acquirable — species abilities and in-play powers are delivered as Minor Gifts; ADR-0050, #1577)
- **Gift lineage (#2891, ADR-0192)** — `Gift.parent` (self-FK, PROTECT, `related_name="children"`)
  hangs a gift beneath an umbrella gift. **Holding a gift reaches the techniques of that gift and
  of every ancestor, and the GIFT thread on the held gift is the thread for all of them** — one
  `CharacterGift`, one thread, one technique cap, so a subspecies character doesn't pay the Rite
  of Imbuing twice. Model surface: `Gift.lineage` / `lineage_ids` / `inherited_techniques`
  (mirrors `Species.lineage`, cycle-safe seen-set). `Gift.cached_techniques` still means the
  gift's OWN techniques — it is the `Prefetch(to_attr=)` target for the gift API; don't widen it.
  Service seams: `resolve_owned_gift(sheet, gift)` (`services/gift_acquisition.py`) answers both
  "does the learner own this?" and "which gift's thread and cap govern it?"; `gift_threads_for`
  (`specialization/services.py`) returns the GIFT threads covering a gift. Deliberately NOT
  lineage-aware: `cg_catalog` (authored at technique granularity), `CharacterTechniqueHandler
  ._state` (explicit `CharacterTechnique` rows), `GiftSerializer.techniques`. A *different* axis
  from `species.SpeciesGiftGrant.inheritable`, which walks the species chain — both are needed.
  See `docs/systems/magic.md`'s "Gift lineage" section for the full call-site table.
- **Content pipeline (#2486):** the catalog (`Gift`/`Technique` + grant tables
  `PathGiftGrant`/`TraditionGiftGrant`/`species.SpeciesGiftGrant` + `GiftUnlock` + `Technique`'s
  payload rows) is lore-repo exportable via `CONTENT_MODELS` with natural keys —
  `GiftUnlock` is keyed `["gift"]` (#2967; one row per gift, DB-enforced). Registering it is what
  makes an authored Minor Gift *learnable*: `charge_and_learn` raises `GiftUnlockMissing` for a
  learner's first technique from a gift they don't own, so a Minor Gift with no `GiftUnlock` is
  reachable only by a Species/Tradition/Path grant. Blank `paths` = in-band for everyone (the
  open-to-all shape). **No seeder may create one.**
  `Technique` is keyed `(gift, name)`, now DB-unique per gift
  (`unique_technique_gift_name`), so authoring a duplicate raises
  `DuplicateTechniqueName` (clean 400) instead of an `IntegrityError`. See
  `docs/systems/magic.md`'s "Content pipeline" section for the full model list.
- `TechniqueStyle` - How a **practitioner** works magic (Manifestation, Subtle, Performance, Prayer, Incantation). A property of the caster's `Path` (`classes.Path.style`), NOT of the technique (#2700, ADR-0167). `StyleCapabilityRequirement` rows let a style gate casting on the caster's capabilities (an Incantation caster who cannot speak cannot incant), evaluated by `technique_performable`. `TechniqueStyle.skill` is the Magic skill casts in that style add (#5002). A Gift may set its own style (`Gift.style`, nullable), which overrides the Path style when resolving `cast_concealment` and the cast skill for that gift's techniques (`services/casting_style.py`; capability gating is unaffected — it still reads the caster's own Path style) — a species gift the character never chose doesn't inherit the Path's manner (#2905, ADR-0199).
- `EffectType` - Types of magical effects (Attack, Defense, Movement, etc.)
- `Restriction` - Limitations that grant power bonuses (Touch Range, etc.), `kind` DESIGN.
  A `kind=PRICE` row is a different thing wearing the same table: a cost a caster attaches
  to their own hold (`CharacterTechnique.price`), offered in creation via
  `creation_point_cost`, whose `power_bonus` is added to every cast as a power-ledger term
  and whose `cast_narration` joins the cast narration (#4099, ADR-4099). A price may
  consume carried items (`PriceComponentRequirement`, the sibling of
  `RitualComponentRequirement`) and inflict `inflicted_condition` on every cast that pays
  it; `price_paid_for_cast` (called once in `use_technique`) is the only decision, and a
  caster lacking a component casts without the price (no bonus, clause, condition or
  consumption). `TechniqueSerializer
  .restriction_ids` and the builder's `Restriction.objects.filter(...)` call sites scope to
  `kind=DESIGN`; `CharacterTechnique.clean()` enforces a price can only be `kind=PRICE`.
- `IntensityTier` - Configurable thresholds for power intensity (Minor, Moderate, Major).
  `control_modifier` is 0 or more: a tier only adds control (#4740); the Required content
  row `intensity-tiers-never-lower-control` lists a negative one
- `Technique` - Authored magical abilities with level, style, effect type (created via the budget builder or staff CRUD — see "Technique authoring" below)
- `TechniqueFunctionTag` - Content-authored `(technique, function)` join recording which
  fine-grained `TechniqueFunction` labels (`constants.py`, 12-value `TextChoices`) a
  technique carries; `Technique.cached_function_tags` accessor. The shared vocabulary
  consumed by covenants' per-vow technique specialty (#2443) and situational perks
  (#2536) — see `docs/systems/magic.md`'s power-term section.
- `CharacterGift` - Links characters to known Gifts. Carries `origin` (`AcquisitionOrigin`,
  #3055 acquisition-provenance ledger — see "Acquisition provenance" in `docs/systems/magic.md`).
- `CharacterTechnique` - Links characters to known Techniques: the character's **hold**.
  Also carries `origin` (`AcquisitionOrigin`, #3055) — every creation site stamps it
  explicitly. Carries the character's own personalization of the technique (#4099,
  ADR-4099, creation-only this release): `custom_name`/`custom_description` (display
  only, never a lookup key; blank = the catalog's), `price` (FK `Restriction`,
  `kind=PRICE` only), `early_form` (FK `TechniqueVariant`, bought before the gift thread
  reaches its level, honored only for its own buyer, never a role-granted hold).
  `display_name` reads `custom_name or technique.name`. See `docs/systems/magic.md`'s
  "Technique personalization" section for the full service surface
  (`services/technique_personalization.py`, `services/creation_personalization.py`).
- `AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` — abstract bases
  (`models/techniques.py`) whose columns are shared by both the committed `Technique*` and the draft
  `TechniqueDraft*` payload rows; each concrete subclass adds only its owner FK.
- `TechniqueDraft` — one-per-`CharacterSheet` in-progress design workbench
  (`related_name="technique_draft"`). Created/returned by `get_or_start_draft`; deleted by
  `discard_draft`. No JSON; every field is a proper column.
- `TechniqueDraftCapabilityGrant` / `TechniqueDraftDamageProfile` / `TechniqueDraftAppliedCondition`
  — payload child rows for `TechniqueDraft`; inherit the abstract bases above.
- `TechniqueMoraleEffect` / `TechniqueDraftMoraleEffect` - one-to-one morale payload row (#4619). Enemy-only: it makes the technique hostile and enemy-aimed, and combat skips allies and charmed enemies. Writers call `invalidate_technique_payload_caches`.
- `TechniqueRemovedCondition` / `TechniqueDraftRemovedCondition` — dispel/cleanse payload rows
  (#1585). Subclass of `AbstractAppliedCondition` (sibling to `TechniqueAppliedCondition`); adds
  `remove_all_stacks` (bool, default True). The inherited severity/duration/stack knobs are inert
  for removal — `clean()` enforces they stay at defaults. Removal diverges from the apply path by
  authoring `target_kind` + `minimum_success_level` (dispel needs SELF/ALLY targeting the apply
  path hardcodes to ENEMY/1). See ADR-0064.
- `TechniqueBudgetConfig` - Singleton (pk=1) of power-cost-per-unit knobs (intensity, control, payload, restriction refund multiplier). Lazy-created via `get_technique_budget_config()` in `services/technique_builder.py`.
- `TechniqueTierBudget` - Per-tier reference power budget + representative level stamped on techniques authored at that tier. Lazy-created via `get_technique_tier_budget(tier)`.
- `SoulTetherConfig` - Singleton (pk=1) of Soul Tether tuning knobs: the Sineating check type and difficulty (`sineating_check_type` is a nullable FK; unset means Sineating refuses), `corruption_per_unit`, `resonance_per_unit`, the per-plea unit cap, the settling-the-Mire sizes (`purify_reward_percent`, the four tie-gauge steps, `succumb_bonus_percent`, `jackpot_percent`, `fall_payout_percent`, `fall_breaker_bonus_percent`), `resistance_full_at`, and the rescue strain thresholds, resonance costs and budget bases and multipliers. Sineating's anima and fatigue costs were removed in #5177. The cap's and the Hollow's level scaling are `ModifierLevelBaseline` lane rows. Lazy-created via `get_soul_tether_config()` in `services/soul_tether.py`. `SineatingOutcomeAward` (an `OutcomeTierAward`, `earned_share`) is the per-outcome-tier share of full resonance a Sineating earns each party.
- `MireHolding` - How much corruption a Sineater carries for one Sinner in one resonance (#5177): `relationship` (the Sineater's own `CharacterRelationship` side toward the Sinner), `resonance` and `amount`; unique per `(relationship, resonance)`. The jackpot's base and the fall's tally are per tether, so they are `CharacterRelationship.mire_purified_since_payout` and `mire_succumbed_since_fall` on that same Sineater-side row. `ImpulseShown` - the record that a character was told of an impulse in a scene (`character_sheet`, `resonance`, `scene`, `kind`); unique per tuple. `CorruptionConfig` carries the impulse stages and the Compulsion condition (see "Corruption impulses").
- `TouchstoneCastConfig` - Singleton (pk=1) of touchstone combat resonance tuning (#2023). `config_scale` (integer-tenths, default 10 = ×1.0) scales the per-tier cast bonus: `resonance_tier.tier_level × config_scale / 10`. Lazy-created via `get_touchstone_cast_config()` in `services/touchstone.py`. The touchstone power-term provider (`touchstone_power_term` in `services/power_terms.py`) scans equipped items for `template.tied_resonance` matches and folds the bonus into `_derive_power`'s TERM stage.

### Technique authoring (budget builder)

`services/technique_builder.py` provides a three-layer authoring stack:

**Unrestricted core** — `build_technique(design, *, creator)` writes a `Technique` + payload rows (`TechniqueCapabilityGrant`, `TechniqueDamageProfile`, `TechniqueAppliedCondition`) + restriction attachments in one `transaction.atomic`. No gating, no character binding. `create_technique(...)` is the extracted low-level row writer shared with the CG starter-gift catalog seed. When `action_template` is omitted (the default), `create_technique` resolves it to the shared **Technique Cast** `ActionTemplate` seeded by `seeds_cast.py` via `get_standalone_cast_template()` — so every technique is castable standalone out of the box. Staff may pass an explicit template FK to override on a per-technique basis.

**Policy layer** — `price_design(design, *, config, budget)` is a pure function that itemizes power cost per dimension and subtracts restriction refunds, returning a `TechniqueCostBreakdown`. It always runs for every author — the breakdown is informational for staff and a gate for players. `AuthoringPolicy` subclasses answer three knobs:
- `StaffPolicy` — `enforced=False`; budget is advisory; any tier allowed.
- `PlayerPolicy` — `enforced=True`; budget is enforced; allowed tiers come from the research-unlock seam (permissive `TODO` today).
- `GMPolicy` — `enforced=True`; calibration is a staff-tunable `TODO` (no grounded GM-level concept yet).

`enforce_policy(design, policy, character)` always prices and returns the breakdown; raises `TechniqueBudgetExceeded(breakdown)` only when `policy.enforced and not within_budget`, or `TechniqueAuthoringNotPermitted` when the tier is disallowed.

**Context wrappers**:
- `author_technique(character, design)` — player path: `PlayerPolicy` (enforced) → build → bind `CharacterTechnique`.
- `author_staff_technique(design, *, creator=None)` — staff path: `StaffPolicy` (advisory) → build; no character binding.

**Draft workbench** (`services/technique_draft.py`, `models/technique_draft.py`):

`TechniqueDraft` is the in-progress design row (one per `CharacterSheet`). Its payload children
inherit the abstract payload bases, so every payload column is identical between draft and committed
rows. Key service functions:
- `get_or_start_draft(character) -> TechniqueDraft` — creates or returns the active draft.
- `discard_draft(character)` — deletes the draft and all child payload rows.
- `set_draft_fields(draft, **fields)` — updates name/description/gift/style/effect_type/level/etc.
- `add_draft_restriction(draft, restriction)` / `remove_draft_restriction(draft, restriction)`
- `add_draft_capability_grant` / `add_draft_damage_profile` / `add_draft_applied_condition`
  and their `remove_*` counterparts — payload row management.
- `draft_to_design(draft) -> TechniqueDesignInput` — validates completeness and converts to the
  design input type; raises `TechniqueDraftIncomplete` on missing required fields, and its
  subclass `TechniqueDraftMoraleRemovesNothing` for a morale row that removes no morale (#4619).

`validate_design_for_character(design, policy, character)` in `services/technique_builder.py` is
the shared player-facing gift-ownership gate — the single source of truth for the gate. Call it
after `draft_to_design` when finalising from telnet or web. Raises
`GiftNotOwned` if the character doesn't own the design's gift.

Draft-specific exceptions (in `exceptions.py`): `NoActiveTechniqueDraft`,
`TechniqueDraftIncomplete` (+ `TechniqueDraftMoraleRemovesNothing`), `UnknownTechniqueVocab`, `UnknownGift`, `GiftNotOwned`.

**Action seam** — `AuthorTechniqueAction` (`actions/definitions/technique_authoring.py`,
key `"author_technique"`, category `"magic"`) is the single commit seam that both the web view
and the telnet workbench converge on. It calls `draft_to_design` → `validate_design_for_character`
→ the appropriate context wrapper, catching budget/permission/gift/draft exceptions and returning
a failure `ActionResult` whose `message` the web view maps to HTTP 400/403.

**API endpoints** on `TechniqueViewSet` (`/api/magic/techniques/`):
- `POST .../author/` — dispatches `AuthorTechniqueAction.run()` for the player path (HTTP contract
  preserved: 201/400/403). Staff-without-character uses `author_staff_technique()` directly (no
  `CharacterSheet` actor). Returns 201 with `TechniqueSerializer` + breakdown, or 400 with
  breakdown when a player is over-budget.
- `POST .../price/` — dry-run; returns the `TechniqueCostBreakdown` for any author without creating rows.
- Base `create`/`update`/`destroy` are staff-only raw admin CRUD (`IsAdminUser` permission).

**Frontend** — `TechniqueBuilderForm` with `mode: "staff" | "player"`. Staff mode shows the budget
meter informationally without blocking; player mode gates submit on `within_budget`. `usePriceTechnique`
(debounced `POST .../price/`) drives the live budget meter; `useAuthorTechnique` handles submission.

**Telnet workbench** — `CmdTechnique` (`commands/technique.py`, key `"technique"`, lock
`cmd:perm(Builder)` — staff/GM-only; not available to base players). Subcommands:
`draft` (create/show draft), `show` (print current draft), `set <key=value…>` (update fields
in-place), `restrict <name>` / `grant` / `damage` / `condition` (add payload rows),
`price` (dry-run breakdown), `author` (finalize via `AuthorTechniqueAction` with `as_staff=True`,
`StaffPolicy` — no `CharacterTechnique` binding), `discard` (delete draft). Registered in
`commands/default_cmdsets.py`.

**Exposure** — technique authoring is currently staff/GM-only. Player self-service (CG
technique-design step or a magical-research unlock — never on-demand) is a deferred
`needs-design` follow-up; the web `author` endpoint and `PlayerPolicy` seam are already wired.

### Anima Recovery
- `Ritual` (execution_kind=SCENE_ACTION) + `RitualCheckConfig` sidecar - Personalized recovery ritual (stat + skill + check_type + two resonance picks, `primal_resonance` and `outward_resonance`)
- `AnimaRitualPerformance` - Historical record of ritual performances

**Note:** During character creation, the magic stage uses the starter Gift/Technique
catalog pick (see below). CG finalization also provisions the anima ritual itself —
the magic writer's `_anima` step (`world.character_creation.magic_writer`) calls
`provision_player_anima_ritual` at finalize, not post-CG. The player-authored `Ritual` row
(SCENE_ACTION) carries check configuration via its `RitualCheckConfig` sidecar (stat, skill,
primal_resonance, outward_resonance, check_type); as of #5280 the two picks are populated at CG
time from the heaviest Primal and the heaviest Celestial or Abyssal pick (`MagicPicks`), since the
anima ritual IS the character's magical identity.

**The ritual is never performed alone (#5280, ADR-5280).** `perform_anima_ritual` is gone. Every door
(persona menu, Rituals page, the ritual's own name, web dispatch, bare `ritual anima`) is refused with
"Name someone else to take part in your ritual."; the one way in is `start_partner_ritual`, which
`check_partner_ritual` guards (an NPC partner needs a GM: `partner_is_run_by_a_gm`; refused in combat).
- **Two picks.** A Primal one (how it feels to her) and a Celestial or Abyssal one (the part of the
  award her partner decides by endorsing), each from the resonances she holds. Held means a
  `CharacterResonance` row, which persists when her aura share falls. The first setup is free
  (`set_up_anima_ritual_resonances`); after that they are locked. A pick stays on the ritual until
  changed even if it leaves her held list, and pays nothing while she does not hold it.
- **The split.** `ritual_succeeded` (`success_level >= 0`) is the one success boundary: a Partial
  Success pays its own tier's anima budget and `AnimaRitualResonanceAward`; Failure and Critical
  Failure recover no anima, ease no Soulfray and grow no Primal resonance. `ritual_earning_parts`
  splits the award by the two affinities' settled aura shares. The part paid to the outward pick is
  the award times the outward affinity's settled share divided by the sum of the Primal and outward
  shares, rounded down; the part paid to the Primal pick is the rest; when both shares are 0 the
  award splits in half (the outward part rounded down); a lone pick gets the whole award. A pick
  whose share is exactly 0 beside a non-zero one is paid 0. A pick keeps paying while she holds the
  resonance, however small its share. A part pays nothing when the performer does not hold that
  resonance, which happens when a pick has left her held list.
- **The ritual is the character's.** `get_character_anima_ritual` and `anima_ritual_open_in_scene`
  read `character_scene_action_rituals(character_id)`: the SCENE_ACTION ritual her roster entry has a
  `CharacterRitualKnowledge` row for (creation writes it beside the ritual), never one her player's
  account authored, so two characters one player plays each have their own, and a character nobody
  is logged in as still has hers (#5280). The telnet name lookup, the sheet's magic section and the
  edit permission (`IsRitualAuthorOrStaff`: a player acting as the character who knows it, `known_ritual_ids_for_request`; the Rituals list
  shows the selected character's anima ritual only) read the same row. `author_account` only records who created it (the content export skips such rows).
- **The answer.** A player partner endorses or withholds the outward part
  (`answer_anima_ritual`; `AnimaRitualPerformance.endorsement`, `outward_amount_pending`). After a failed
  roll, `AnimaConfig.failed_endorsement_percent` of the Success tier's outward part is held. An NPC
  partner gives it on the roll alone. `lapse_pending_endorsements` runs when a scene finishes (and
  when a battle ends its backing scene); a late answer is refused.
- **Attunement.** `attune_anima_ritual` changes the picks after the free setup for the costs on
  `AnimaConfig` (`attunement_anima_cost`, `attunement_resonance_cost`, `attunement_ap_cost`, an optional
  check). It checks only the picks it changes, refuses in combat and before any picks are set, spends
  action points as its check, never refuses for lack of anima (a shortfall is Soulfray), and a failed
  roll keeps the costs and the old picks.

**Anima/severity budget per outcome tier (#1207):** `anima._budget_for_outcome` reads
`AnimaRitualBudgetAward` (`world/magic/models/soulfray.py`) — a per-`CheckOutcome`-tier
authored row — instead of the old `SoulfrayConfig.ritual_budget_critical_success/_success/
_partial/_failure` fields. Every success tier (Partial Success and above) must have a row; a
missing one raises rather than silently granting 0 anima. A failed roll recovers nothing (#5280), so
the Failure and Critical Failure rows are never read.

### Standalone Casting (#1306)

Every technique now carries an `action_template` FK (defaulted by `create_technique`) so
casting never hard-fails with "no template." The resolution chain:

- **Shared "Technique Cast" ActionTemplate** — seeded idempotently by
  `seeds_cast.ensure_technique_cast_content()`, called from the magic dev seed.
  Retrieved at runtime via `get_standalone_cast_template()`. Staff may override
  on a per-technique basis via the `action_template` FK; `None` (omit the kwarg)
  always resolves to this shared template.
- **Per-character magic check** — every caster rolls *their own* magic check, not a
  technique-level authored check. `ensure_character_magic_check_type(character_sheet, *, stat, skill)`
  (`seeds_checks.py`) synthesizes a `CheckType` named after the character (pattern
  `character_magic_check_type_name(character_sheet)`) that weights the character's
  personal stat + skill. `get_character_cast_check(character)` (`services/anima.py`)
  resolves this check type for use by the cast pipeline. `resolve_cast_check(character,
  technique)` (`services/magic_skills.py`) is the single resolver every cast path calls: it
  returns a `CastCheck` whose `check_type` is the personal check when the caster is
  provisioned, else falls back to `template.check_type` (ADR-0096), and whose
  `extra_traits` carries the technique skill term (#4450) — standalone casts, combat round casts, clash
  contributions, and battle technique resolution (`world/battles/resolution.py`)
  all go through it, so none of them can silently roll the shared template check
  for a provisioned caster.
  The same `CastCheck` feeds thread pulls (#4450): `cast_involved_trait_ids(cast_check)`
  (`services/magic_skills.py`) gives the cast's `PullActionContext.involved_traits`, so a TRAIT
  thread on the caster's stat, a personal skill or the technique skill is in the cast's action,
  both as a passive tier-0 thread (`build_cast_applicable_threads(cast_check=)`) and as a declared
  pull (`_charge_cast_pull`, `commit_combat_pull(cast_check=)`). A technique-enhanced social action
  passes the template check plus the technique term, since that is what it rolls.
- **Anima ritual alignment** — `provision_player_anima_ritual` (`services/anima.py`)
  points the anima ritual's `RitualCheckConfig.check_type` at the same per-character
  check type, so the anima ritual and technique casts always roll the same personal check.
  Use `get_character_anima_ritual(character)` to retrieve the anima ritual row.
- **Graded consequence pool** — a single "Magic: Technique Cast" `ConsequencePool`
  (seeded by `seeds_cast.py`) routes graded outcomes (failure / partial success / success)
  through the shared consequence machinery. No per-technique pool is required.
- **Consequence-pool catalog (#1320)** — a technique's author (web builder or telnet
  `technique set consequence_pool=<id>`; CG finalization does NOT expose this pick,
  #2426) may pick a "flavor" from a curated catalog instead of the shared graded
  pool. The catalog
  is `ConsequencePool.objects.filter(parent=<base pool>)` — single-depth children
  of the base pool seeded by `seeds_cast.ensure_technique_catalog_content()`. Each
  catalog entry has its own `ActionTemplate` (same `check_type`/`pipeline`/
  `target_type` as the shared template — only `consequence_pool` differs) so
  the flavor pick cannot affect the rolled check: **every** cast path (standalone,
  combat, clash, battle technique resolution in `world/battles/resolution.py`)
  resolves the check via `resolve_cast_check` (personal check first, template
  fallback — ADR-0096). The combat availability descriptor
  (`actions/player_interface.py`) reads the personal check once per caster and
  calls `cast_check_type(personal_check, technique)`, the same precedence
  helper `resolve_cast_check` uses, so the action-picker UI shows the same check
  the resolver rolls — and none of them read
  `technique.action_template.check_type` directly anymore. Resolution:
  `technique_builder.resolve_cast_action_template()`.

Follow-ups deferred to later issues: the optional resonance→aspect mapping. (The
targeting model — targeting validity + AoE + per-technique target constraints +
frontend target picker — was resolved in #1321; see "Targeting/hostility" below.)

**Property-gated targeting precondition (#1793):** `Technique.target_prerequisites`
(M2M to `mechanics.Prerequisite`) lets a technique require a target currently hold a
Property at or above a threshold. Enforced symmetrically in both cast paths: non-combat
(`validate_cast_target`/`resolve_targets`, `services/targeting.py`) and combat
(`resolve_combat_technique`, `world/combat/services.py`). In both, SINGLE/SELF raise
`InvalidCastTarget` pre-flight (SELF checks the caster directly, since a SELF cast
conventionally supplies no explicit target); AREA/FILTERED_GROUP get NO pre-flight
check at all and instead defer entirely to a silent per-target filter downstream
(`resolve_targets` non-combat, `_filter_by_target_prerequisites` combat) — an AoE cast
skips ineligible targets rather than hard-blocking the whole cast (ADR-0045). This is a
precondition layered on the existing target-resolution machinery — it does not build the
still-deferred general targeting model (AoE constraints, frontend target picker) noted above.

`Technique.properties` (M2M to `mechanics.Property`) are the technique's own marks: the
properties that say how it works (a blink carries `teleport`, #5066, ADR-5066). They are its
effect properties for capability sources, applications and clash opposition
(`services/technique_marks.py`, `effect_property_ids_by_technique`); the gift's resonances
never count. A major gift's `Substance.property` is carried by every technique of the gift and
its child gifts, read at call time by the same seam and stored nowhere, so staff cannot untick
it (#5125). `Technique.has_property(name)` reads through the seam too; this is
separate from `Character.has_property`, which checks a *character's* Property
attachments (both the primary persona's authored identity tags and runtime
`ObjectProperty` rows, #1793) and backs the `has_property` reactive-trigger DSL op.
`Character.has_capability` is the capability-typed sibling — checks
`get_effective_capability_value(sheet, capability_type) > 0` — and backs the new
`has_capability` DSL op (both in `flows/filters/evaluator.py` /
`typeclasses/characters.py`).

### Substances and Primum (#5018, #5125, ADR-5018, ADR-5125)

Full reference: `docs/systems/magic.md` "Substances and Primum". `Substance` is one shared list
(`models/substance.py`); a major gift points at one (`Gift.substance`, null on a minor gift,
`primum.gift_substance` walks the lineage), and places (`PlacePrimum`), creature kinds
(`CreaturePrimum`), call-ups (`PrimumCallUp`), sightings (`PrimumSighting`) and items
(`ItemSubstance`, in `world/items/`) all name it. Rules for code in this area:

- **Compare rows, never names.** A rule reads a substance row and its `SubstanceRelation` rows
  (`relation_kinds_for`), never a gift or a substance by name, and relations never chain.
- **Reads are `primum.py`, writes are not.** `cast_points` returns one `SourcePoints` per source,
  `points_to_power` runs the staff curve, `plan_substance_call_up` is the one pure plan the card,
  the charge and the ledger read. Missing tuning (no steps, no curve, no harvest check) adds no
  line or answers in one plain sentence; it never raises out of a cast.
- **Creatures never feed a cast.** `cast_points` reads the place and her equipped items only; a
  creature's Primum (`creature_substance_amounts`) counts for sensing and harvesting alone.
- **Never name Primum the caster has not perceived.** A source of another substance that is not
  in `perceived_substance_ids` reads "Something here works against your <own>" or "Something
  here strengthens your <own>" on the card and the ledger (`SourcePoints.hidden`).
- **Anima is never a refusal.** A call-up past her anima goes through `deduct_anima` and the
  soulfray path; no resonance is read or written.
- **A technique's substance property is derived on read** through
  `effect_property_ids_by_technique`; never store it or offer a tick.
- **Harvest writes under lock.** `harvest` takes from a source inside `select_for_update`, and a
  slain creature yields once in total (`CombatOpponent.primum_harvested_at`). Primum is only ever
  harvested from a lair or a slain creature. Every attempt, good roll or bad, spends
  `harvest_ap_cost` and adds `harvest_fatigue_cost` physical fatigue before the roll.
- **Transient rows go on the leave hook.** `clear_caster_substance` and `clear_sightings` run
  from `Character.at_post_move` and `_leave_the_grid`; a scene's marks clear in
  `Scene.finish_scene`.
- **Spending Primum on a thread or a cast is `[ABSENT]` by decision** (not alpha).

### Magical skills (#4450, ADR-4450)

Every magical roll adds skills staff chose in admin; no skill is named in code. Full reference:
`docs/systems/magic.md` "Magical skills".

- **Models:** `MagicActivity` (`constants.py`, 23 kinds of roll), `MagicActivitySkill`
  (`models/magic_activity.py`: activity, skill, weight; unique per pair), `TechniqueStyle.skill`
  (#5002: the casting style carries the cast skill; `Path.technique_skill` and
  `Gift.technique_skill` are gone), `Technique.skill` (override),
  `ConditionCategory.adds_loss_of_self_skills`.
- **Services (`services/magic_skills.py`):** `activity_skill_terms(activity)`,
  `technique_skill_term(character, technique)` / `technique_skill_term_for_path(technique, path)`,
  `cast_check_type(personal_check, technique)` (ADR-0096 precedence, once), `resolve_cast_check`, `involved_trait_ids`, `cast_involved_trait_ids`. `loss_of_self_terms(template)`
  is in `world/conditions/services.py`. Terms ride the check engine's `extra_traits`.
- **Technique skill order:** technique override, else the `skill` of the style the cast is
  worked in: `services/casting_style.py`'s `casting_style` (the Gift's own `style`, else the
  caster's current Path style), the same style cast concealment reads (#5002, ADR-5002, which
  retired #4555's own-Path skill rule). Inactive skills give no term.
- **Adding a magical roll:** add a `MagicActivity` member and pass
  `extra_traits=activity_skill_terms(MagicActivity.X)` at the roll. Import it inside the
  function when the caller is `world.conditions` or `world.species` (they sit below magic). A
  member with no `MagicActivitySkill` row adds nothing, and the Required content dashboard lists
  it until staff map one.
- **A new cast path** calls `resolve_cast_check(character, technique)` and passes both the
  `check_type` and `extra_traits` to the roll, and the `CastCheck` to its thread pull context.
- **Anima Check:** the character-creation pick excludes MAGIC-category skills.
- **Magic skills only (#4547):** the four pickers (activity, casting style, technique, harvest
  roll) share `limit_choices_to=MAGIC_PICKER_SKILL_CHOICES` (`skill_choices.py`), so admin and `full_clean()`
  take Magic-category skills only, and never a combat style's own skill (#4921): that one is
  trained in creation and added by the style. `CombatStyle.clean()` refuses the reverse, a style
  taking a skill a picker already adds. `CombatStyle.skill` itself keeps `MAGIC_SKILL_CHOICES`. No seeder
  names, creates or weights a skill for magic; a new magic check type weights its stat and lets
  the roll add skills. Sanctum ritual configs take their skill from the `RITUAL_WORKING` mapping
  (tests call `map_ritual_working_skill()` first).

### Dispel / Cleanse (#1585)

A technique carrying `TechniqueRemovedCondition` rows strips matching conditions from the
resolved target on cast. The removal sibling of `apply_technique_conditions` is
`remove_technique_conditions` (`services/condition_application.py`), wired into the same cast
seam — `request_technique_cast` (`world/scenes/cast_services.py`) for standalone and
`CombatTechniqueResolver._apply_conditions` (`world/combat/services.py`, returns
`(applied, removed)`) for combat. No-op when the technique has no `removed_conditions` rows.

Three independent gates per target, evaluated in order: (1) **cast-SL row gate** —
`success_level < row.minimum_success_level` skips the row (mirrors the apply path; a botched cast
removes nothing); (2) **`can_be_dispelled` hard gate** — a condition whose template has
`can_be_dispelled=False` is a no-op (never an error); (3) **opposed cure check** — when the
condition's `cure_check_type` is set, `perform_check_with_modifiers(caster, cure_check_type,
cure_difficulty_level, extra_modifiers=power_bonus)` is rolled, where `power_bonus =
int(row.cure_power_multiplier * eff_intensity)` (#3391 — power leg); removal succeeds iff
`check_result.success_level > 0`, else resisted (no-op for that target, cast continues). When
`cure_check_type` is null, removal proceeds unconditionally (uncontested dispel) — power has
nothing to modify, so an uncontested dispel is never turned into a coin flip by this leg.
`cure_power_multiplier` (`TechniqueRemovedCondition`, `DecimalField`, default 0) is a caster-power
knob layered on top of `can_be_dispelled`, which stays an absolute hard gate independent of power
(ADR-0064) — a technique authored before #3391, or any row an author leaves at the default, casts
byte-identically to before. Delegates to `world.conditions.services.remove_condition`
(`remove_all_stacks` forwarded → partial-stack decrement or full removal; reuses
`CONDITION_REMOVED` emission + deferred-death resolution).

**Targeting/hostility** (`services/hostility.py` + `services/targeting.py`): stripping an ENEMY's
buff is hostile; cleansing an ALLY's debuff resolves ALLY; a self-cleanse resolves SELF. Dispel
is **not** consent-gated — removing a behavior-altering condition (dispelling a charm) is
beneficial, so `removed_conditions` is intentionally NOT added to
`technique_alters_behavior`/`cast_requires_consent`.

**Authoring:** mirrors `applied_conditions` through the budget builder (`RemovedConditionSpec` →
`TechniqueDesignInput.removed_conditions` → `build_technique`; priced at flat
`payload_base_cost`), draft workbench (`add_draft_removed_condition` / `draft_to_design`),
serializer (`_RemovedConditionSpecSerializer`), admin (`TechniqueRemovedConditionInline`), telnet
(`technique dispel add|remove`), and frontend (`RemovedConditionsEditor` in
`TechniqueBuilderForm`). See ADR-0064 for why dispel is a payload row, not an `EffectKind`.

### Technique Acquisition (non-teaching) (#1732)

- `TechniqueGrant` — Authored sidecar (`models/technique_grant.py`) linking a
  `Technique` to an `ItemTemplate` (on-use delivery) or `Ritual` (SERVICE delivery).
  Exactly one vehicle enforced by `clean()` + partial UniqueConstraints.
- `learn_technique(learner, technique, *, source, ap_cost=0, xp_cost=0, origin=TRAINED,
  completing_progress=False)` — shared commit seam in
  `services/technique_acquisition.py`. When `ap_cost > 0`, creates
  a `TechniqueProgress` meter instead of minting immediately (#2711); the learner
  fills the meter via `contribute_to_technique_progress` in subsequent sessions.
  When `ap_cost == 0`, mints `CharacterTechnique` immediately (the meter-completion
  path or a free grant). Runs gift-owned → duplicate → prerequisite → cap →
  (meter-or-mint) → announce. **Prerequisite gate (#4097 fix round 2):** calls
  `gift_acquisition.enforce_technique_prerequisites` (same gate `charge_and_learn`
  uses), skipped for `origin=AcquisitionOrigin.GM_GRANT` (deliberate GM fiat) and
  for `completing_progress=True` (a meter-fill mint — the check already ran at
  that meter's creation). See `docs/systems/magic.md`'s "Technique Prerequisites"
  section for the full wiring across all three acquisition routes.
- **Technique progress meter (#2711).** `TechniqueProgress`
  (`models/technique_progress.py`) — per-(character × technique) development
  meter. `TechniqueProgressWeekly` — per-week cap tracker mirroring
  `WeeklySkillUsage`. `contribute_to_technique_progress(sheet, progress, amount)`
  (`services/technique_progress.py`) — the per-session training function: spends
  AP (with Unbound surcharge applied per-session, not to the meter total), adds
  meter-progress points, enforces the weekly cap, mints on completion.
  `is_cross_path_learning(teacher_tenure, learner_sheet)` — the style-comparison
  helper used at meter creation.
- **Cross-path friction (#2711).** When the teacher's `Path.style` differs from
  the learner's, the meter total is multiplied by
  `GiftAcquisitionConfig.cross_path_cost_multiplier` (default 2.0). Null style on
  either side = no surcharge (fail-open, mirroring ADR-0164).
  `GiftAcquisitionConfig.weekly_training_cap` (default 50) — max meter-progress
  points per game week. `cross_path_cap_divisor` (default 1) — optionally lowers
  the cap for cross-path learning.
- **No path-style learn gate (#2700).** `can_learn_technique` /
  `TechniqueStyleForbidden` are deleted. Gift ownership plus
  `PathGiftGrant`/`TraditionGiftGrant` curation is the gate, at technique
  granularity; style now gates *casting* (via `StyleCapabilityRequirement`), not
  learning. See ADR-0167.
- `GiftAcquisitionConfig.major_gift_ap_multiplier` — staff-tunable AP multiplier
  for MAJOR-gift techniques on the `has_gift` branch of `accept_technique_offer`.
  Applies to the meter total at creation (#2711).
- `GiftAcquisitionConfig.imbue_ap_cost` — staff-tunable flat AP cost per Rite of
  Imbuing (#2467). The Unbound +50% surcharge applies on top via
  `magic_learning_ap_cost_surcharge_percent`. Default 2 (cheaper than the
  technique-learning base of 5).
- `charge_and_learn(learner, technique, *, base_ap_cost, source, gold_cost=0,
  gold_treasury=None, teacher_tenure=None, teacher_banked_ap=0, instruction_bonus=0)`
  (`services/gift_acquisition.py`, #2440, #2711) — the shared charge+acquire
  core: duplicate gate → has-gift/major-gift multiplier → cross-path multiplier
  → implicit gift acquisition → cap check → teacher banked-AP consumption →
  gold spend → creates `TechniqueProgress` meter (does NOT mint immediately).
  `instruction_bonus` (#2741) is copied onto the new meter's `instruction_bonus`; only the
  Academy TRAIN offer handler passes a non-zero value, from `TrainOfferDetails.instruction_bonus`.
  Two front doors: `accept_technique_offer` (player-to-player teaching) and the
  Academy TRAIN offer handler (`world.npc_services.effects.run_train_offer`).
  Returns `TechniqueProgress`, not `CharacterTechnique`.
- `AccessChangeSource.TECHNIQUE_GRANT` — provenance value for non-teaching
  technique acquisition.
- Ritual SERVICE dispatch (`_dispatch_service` in `actions/definitions/ritual.py`)
  now forwards `ritual=ritual` to the service function, so technique-granting
  rituals can resolve their `TechniqueGrant` row.

### Check-based training + its player-facing trigger (#2727, #2739)

`resolve_training_check(learner, progress, *, ap_to_invest, teacher=None)`
(`services/technique_training.py`, #2727) is the check layer sitting on top of
`contribute_to_technique_progress` (above): the learner rolls intellect (the
"Technique Training" `CheckType`) plus the skill terms from
`magic_skills.technique_learning_terms` (#2740: the skills staff mapped to `TECHNIQUE_LEARNING`,
then the skill the technique is cast with, its own skill or else its casting style's, left out
when it is already a mapped skill or one of the check type's own traits) against
`target_difficulty = (technique.tier × step) − (learner_level // divisor) − teacher_skill_bonus +
(self_study_penalty if the meter is self-study)`. A meter is self-study when no player teacher is
in the room and it is not an Academy meter. An Academy meter (`is_academy_instructed(progress)`,
true when the meter's `source` is `ACADEMY_TRAINING`, #2741) is never self-study: it takes no
penalty, and its stored `TechniqueProgress.instruction_bonus` joins the roll as one
"Academy instruction" `ModifierContribution` through `perform_check_with_modifiers`. The outcome maps to a dev-point multiplier via
`TrainingOutcomeAward(OutcomeTierAward)` (botch/failure 0×, partial 0.5×, success
1.0×, critical 1.5×) — AP is always spent regardless of outcome; only the
dev-point yield varies. Four tuning knobs live on `GiftAcquisitionConfig`. This
seam shipped with no production caller until #2739.

**Content dependency, loud failure (#3043).** The "Technique Training" `CheckType`
and its intellect weighting are content models (`CONTENT_MODELS`, #2698; the seed's
invented "Arcane Theory" skill is gone since #4547), not
unconditionally-seeded config — `ensure_technique_training_content()`
(`world/seeds/game_content/magic.py`) resolves them via `authored_or_sample`
(content-repo lookup first, sample stand-in only under `SEED_SAMPLE_CONTENT`,
off by default) and always seeds the `TrainingOutcomeAward` tuning rows regardless.
As of 2026-08-07 the CheckType/trait have not shipped in the lore repo
(ArxII-lore#72), so a real deploy has no "Technique Training" `CheckType` yet.
`resolve_training_check` used to fall back to `CheckType.objects.first()` on
`DoesNotExist` — an arbitrary, unrelated check silently rolled in training's
place. It now raises `TechniqueTrainingNotConfigured` (`exceptions.py`) instead;
`TrainTechniqueAction`'s existing `except (…, MagicError)` clause already catches
it (no widening needed) and surfaces `user_message` ("Technique training is not
configured on this server yet.") as a failure `ActionResult` — a clean telnet
message and an HTTP 400 `{"detail": …}` on the web endpoint below, never a 500.

- **Action** — `TrainTechniqueAction` (`actions/definitions/technique_training.py`,
  key `train_technique`, REGISTRY, `category="magic"`, `target_type=SELF`). Kwargs
  `technique_id` (the `Technique` pk, resolved against the learner's own open
  `TechniqueProgress` meter — no meter is a clean failure naming the two front
  doors above that create one) and `ap_to_invest` (defaults to 1; a value ≤ 0 is
  rejected; the seam spends it in full and raises on pool/cap overruns rather than
  this action pre-bounding it). Resolves a co-present teacher —
  `progress.teacher_tenure` counts only when that tenure's live character shares
  the learner's room *at session time*; for a player-teacher meter, a teacher who is
  away means self-study rates apply silently (Decision 3a — never a location hard-block).
  An Academy TRAIN meter is the exception (#2741): its NPC trainer is never present, so the
  meter itself says the learner paid for instruction, and `self_study` is false for it. Maps `WeeklyTrainingCapExceeded`/`MagicError` to a failure
  `ActionResult`; also catches a bare `ValueError` from `learn_technique` (reached
  on meter completion, raised when the learner already holds the
  `CharacterTechnique` — a stale meter left open after the technique arrived by
  another route) the same way. Success `data`:
  `{technique_id, outcome_name, points_before, points_after, total_required,
  technique_acquired, self_study}`.
- **Telnet** — `CmdTrain` (`commands/training.py`, key `train`, verified free).
  `train <technique>[=<ap>]` resolves the technique by name and dispatches the
  action; bare `train` lists the caller's open `TechniqueProgress` meters (name,
  progress/total, teacher-or-dash) — a read path, no dispatch.
- **Web** — `TechniqueProgressViewSet` (`views_technique_progress.py`, routed at
  `/api/magic/technique-progress/` in `urls.py`). `list` returns the scoped
  character's own meters via `TechniqueProgressSerializer` (technique id/name,
  `points_accumulated`/`total_required`, `teacher_name` — `RosterTenure
  .display_name`, null for self-study — `source_label` from
  `TechniqueProgress.get_source_display()`, and `weekly_remaining`, computed by one
  batched query over the listed meters' technique ids so the list stays O(1)
  queries regardless of meter count). `POST <technique_id>/train/`
  (`TrainTechniqueRequestSerializer`, body `{ap_to_invest?}`) dispatches the
  action, mapping a failure `ActionResult` to HTTP 400 `{detail}`. `<technique_id>`
  is the `Technique` pk (matching the action's own kwarg), not the
  `TechniqueProgress` row's pk, so a technique with no meter surfaces the action's
  own "you aren't training that" failure as a clean 400 rather than a
  router-level 404. Character scoping mirrors `MotifStyleViewSet` (#2030): an
  `X-Character-ID` header, validated as owned via `CharacterContextMixin`, takes
  precedence over the caller's active puppet.
- **Frontend** — `TechniqueProgressPanel` (`frontend/src/magic/components/`),
  mounted in `SpellbookTab` below `MotifStylePanel`, own-view only. See
  `frontend/src/magic/CLAUDE.md` for the query/mutation wire contract.

### Starter Gift Catalog (CG Technique Picks, #2426; content pipeline #2474)

The pre-#2426 design used a staff-curated `Cantrip` starter-technique-template model
that CG finalization minted into a new `Technique`; that model and its API plumbing
were fully removed in #2426 Task 8. See below for the live mechanism.

The CG magic stage picks a staff-authored catalog `Gift` + `Technique`s directly — no
`Gift`/`Technique` row is minted at CG time; `finalize_magic_data` only *links* the
picks (see `services/cg_catalog.py` above).

**The catalog is content, not seed data (#2474).** `Resonance`, `Gift`, `Technique`
(natural key `(gift, name)`, `unique_technique_gift_name`), `PathGiftGrant`, and
`TraditionGiftGrant` all carry natural keys and ride the ordinary content pipeline —
`CONTENT_MODELS` (`core_management/content_export.py`) → arx2-lore fixtures →
`core_management.content_fixtures.load_world_content()`, called from
`world.seeds.database.seed_dev_database()` before any `CLUSTER_SEEDERS` entry runs.
The formerly in-repo `seed_starter_gift_catalog()` (`world/seeds/game_content/
magic.py`, called by `seed_magic_dev()`) — which authored 5 MAJOR `Gift` rows (one
per `TechniqueStyle`/PROSPECT-`Path` pair), 25 `Technique` rows, `PathGiftGrant`
per (path, gift), and the "Unbound" `Tradition` + its `TraditionGiftGrant` rows — is
retired; that shape now lives as lore-repo fixture content. `MagicContent
.create_starter_gift_catalog()` (same module) is the test-only factory-built
stand-in for suites that need an equivalent-shaped catalog without a real
content-repo checkout (see `world/seeds/tests/content_stub.py`'s `stub_content_root()`
for the enriched fixture-backed alternative). A fresh dev database now requires
`CONTENT_REPO_PATH` — `seed_dev_database()` raises `ContentError` if it's unset or
missing, before seeding anything (ADR-0142).

### Signature Motif Bonus (#1582 — ADR-0072)

A character may *sign* one of their TECHNIQUE-kind Threads by attaching a
`SignatureMotifBonus` (`models/signature.py`) — a staff-authored, Motif-gated ADDITIVE
bonus. It is NOT a `TechniqueVariant`, does NOT inherit `AbstractSpecializedVariant`, and
does NOT participate in `execute_crossing_ceremonies` (the crossing ceremony). Invariant: this
boundary must be preserved.

**Gradual unlock (#4099):** the old hard `thread.level >= 3` floor on `set_signature_bonus`
is gone — `SignatureMotifBonus.min_crossing_level` (a stored thread level, default 30,
authorable lower; restated x10 by #5091) is the only gate on which bonuses unlock at which
thread depth. Staff author higher-value bonuses with `min_crossing_level=60` (or 110, 160,
210), and may author one below 30 for an earlier flourish. `available_signature_bonuses` accepts an optional `thread=`
to filter by crossing level + resonance match; `next_signature_bonus(thread, catalog)`
(`services/signature.py`) returns the nearest not-yet-reached flourish for a "keep imbuing"
progress display. When a bonus with a `discovery_achievement` is selected,
`set_signature_bonus` fires `execute_ceremony_beat` (gamewide first-ever or personal
narrative). The `TechniqueCrossingHandler` still fires a narrative-only depth-milestone beat
at level 3 (the first PathStage crossing) — but, since signing may already have happened
below that level now, the beat no longer claims level 3 is the first time signing becomes
possible; higher crossings produce no beat.

**Creation can weave the thread too (#4099).** `SignatureMotifBonus.creation_point_cost`
(nullable; blank = not offered in creation) is a separate authored decision from
`min_crossing_level`: a flourish is only offered as a CG pick when staff set its creation
cost, and creation weaves the TECHNIQUE thread no higher than
`CREATION_PERSONALIZATION_MAX_LEVEL` (10, a new character's level cap in stored thread
levels, #4585/#5091) via `weave_creation_technique_thread`
(`services/threads.py`), so a creation pick never skips the first crossing. A flourish with
no `creation_point_cost` is still reachable later in play, once a thread reaches its
`min_crossing_level` the ordinary way.

- **Catalog model:** `SignatureMotifBonus` (inherits `DiscoverableContent`) — `name`,
  `narrative_snippet`, `required_facet` FK (Facet, nullable), `required_resonance` FK
  (Resonance, nullable), `flat_intensity_delta`, `min_crossing_level` (a thread level, default 30),
  `creation_point_cost` (nullable, #4099), `discovery_achievement` (nullable FK →
  `Achievement`, from `DiscoverableContent`). At least one of `required_facet`/
  `required_resonance` required (`clean()`). AND semantics.
- **Payload child rows:** `SignatureMotifBonusDamageProfile` /
  `SignatureMotifBonusAppliedCondition` — inherit the shared `Abstract*` bases from
  `models/techniques.py`. (The capability-grant sibling was stripped per ADR-0248 —
  capability-flavored signature effects are authored as applied conditions.)
- **Thread FK:** `Thread.signature_bonus` (nullable FK, TECHNIQUE-kind only — enforced by
  `clean()` + DB `CheckConstraint("thread_signature_bonus_technique_only")`). Migrations
  0066 + 0067.
- **Selection service** (`services/signature.py`): `available_signature_bonuses`,
  `set_signature_bonus`, `clear_signature_bonus`, `signature_bonus_for`.
- **Cast wiring** (`services/signature_effects.py`): `signature_intensity_delta` (folds
  into `use_technique(power_intensity_bonus=…)`) + `apply_signature_bonus_conditions`
  (uses shared `apply_technique_conditions` seam via `applied_condition_rows=` param added
  in #1582). Both cast paths (non-combat + combat) wired.
- **Consent (ADR-0024):** because a signature bonus lands its conditions on the resolved
  target, `technique_alters_behavior` / `cast_requires_consent`
  (`services/targeting.py`) take an optional `caster=` and fold in the caster's active
  signature bonus's `cached_condition_applications`. A benign technique signed with a
  bonus carrying a behavior-altering condition is consent-gated exactly as if the
  technique itself carried it; a non-behavior-altering signature condition (e.g.
  Entangled) stays consent-free. The non-combat cast routes (`world/scenes/cast_services.py`)
  pass `caster=initiator_persona.character_sheet.character` at all three consent gates.
- **Combat damage seam (#1728)** (`services/signature_effects.py`):
  `signature_damage_profiles(character, technique)` returns the signed bonus's
  `cached_damage_profiles` (or `[]` if unsigned); `CombatTechniqueResolver._apply_damage`
  (`world/combat/services.py`) appends these to the technique's own profiles before
  resolving damage — the bonus's authored damage now lands in combat.
- **Non-combat narration** (`narration.py`): `signature_clause(snippet)` builds the
  em-dash cosmetic line; folded into `render_cast_outcome_narration`.
- **Combat narration (#1728)**: `resolve_signature_snippet(character, technique)`
  (`services/signature_effects.py`) resolves the cosmetic clause (preferring
  `bonus.narrative_snippet`, falling back to the first Motif facet name), shared by the
  non-combat cast pose and the combat path — `render_action_outcome_narration` +
  `_record_and_broadcast_pc_action` (`world/combat/services.py`) now surface it.
- **Actions** (`actions/definitions/signature.py`): `SignatureSetAction` (key
  `"signature_set"`), `SignatureClearAction` (key `"signature_clear"`),
  `SignatureListAction` (key `"signature_list"`).
- **Telnet:** `CmdSignature` (`commands/signature.py`, key `"signature"`) — namespaced
  subverbs (`set`/`clear`/`list`) to avoid bare-key collisions.
- **Web (#1728):** `SignatureViewSet` (`views_signature.py`) dispatches the same
  Actions via the shared `PuppetActorMixin` (`views_actor.py`, also used by
  `SanctumViewSet`). Routes (`urls.py`, basename `signature`): `GET
  /api/magic/signatures/`, `POST /api/magic/signatures/set/`, `POST
  /api/magic/signatures/clear/`.
- **Admin:** `SignatureMotifBonusAdmin` with inlines for the two payload child models.
- **Resolved (ADR-0248, #3449):** no capability-grant cast seam will be built — grants
  mean standing possession; cast-time capability boosts are authored as applied
  conditions (`ConditionCapabilityEffect`, outcome-scaled). The formerly-inert
  `SignatureMotifBonusCapabilityGrant` payload family was stripped.

### Motif System

The Motif system is a **wired mechanical axis** — dressing in items whose styles match
a character's Motif bindings buffs that resonance's magic through the modifier pipeline.

- `Motif` - Character-level magical aesthetic (container for resonances + facets)
- `MotifResonance` - Resonances in a motif (from gifts or optional)
- `Facet` - Flat vocabulary of imagery/symbolism, name globally unique (2026-09-11 ruling, #3776 — no longer a Category > Subcategory > Specific tree)
- `FacetEffectBonus` - A facet's always-on bonus to one maneuver effect (#4815): the facet names the effect, whatever its thread's resonance; `passive_facet_bonuses` counts it for a worn, threaded facet, scaled by item and attachment quality and, through `amount_tenths`, the `FACET_EFFECT_BONUS` lane at the thread rung (`thread_rung`, per 10 thread levels, #5093). Inline on `FacetAdmin`; `merge_facets` moves it
- `MotifResonanceLink` - Abstract base for per-resonance attachments. Declares
  NO fields; each concrete subclass declares its own `motif_resonance` FK.
  Provides `clean()`/`save()` cap-enforcement logic (Python-layer count check
  against `MAX_PER_RESONANCE`; no DB constraint). Two concrete subclasses:
  - `MotifResonanceAssociation` - Links a resonance to a facet in the motif
  - `MotifResonanceStyle` - Per-character style→resonance binding: each
    `MotifResonance` can hold up to 3 `MotifResonanceStyle` rows (cap enforced
    by `MotifResonanceLink.clean()`/`save()`, Python-layer). Each row binds one
    `Style` (from `world/items`, staff-curated vocabulary model sibling to
    `Facet`/`FashionStyle`) to the resonance.
    **Individualization core:** two characters can share the same `Style` name yet
    bind it to different resonances — so "Seductive" means different magic for a
    fire-resonant caster vs. a shadow-resonant caster.

**Coherence walker (`passive_motif_style_bonuses` in `world/mechanics/services.py`):**
Wired into `equipment_walk_total` → `get_modifier_total()`. For each `MotifResonanceStyle`
binding on the character's motif, checks which equipped items carry that style
(via `CharacterEquipmentHandler.item_styles_for`), aggregates their quality tiers via
`worn_quality_aggregate`, and applies a coherence bonus to the bound resonance's
`ModifierTarget`. The bonus magnitude and per-resonance cap come from the
`AestheticAxisConfig` singleton (`world/mechanics`, lazy-created by `get_aesthetic_config()`).

**Audacity axis (#2029):** each matched binding's quality contribution is additionally
scaled by `world.items.services.styles.audacity_multiplier_for(binding.style)` before being
aggregated — a daring `Style` (higher `StyleAudacity` tier) contributes more coherence than
a restrained one wearing identically-tiered items. The multiplier itself comes from the
staff-tunable `items.AudacityTuning` singleton (defaults 0.75/1.00/1.35/1.75 for
UNDERSTATED/EXPRESSIVE/BOLD/OUTRAGEOUS). The peer style-presentation endorsement grant
(`create_style_presentation_endorsement`, `world/magic/services/gain.py`) applies the same
multiplier to `cfg.style_presentation_grant`, keyed on the *highest*-audacity worn style
that matches the endorsed resonance binding (an endorsee wearing multiple matching styles
is rewarded for the boldest one, not the first one found).

The per-resonance computation lives in `motif_coherence_bonus(sheet, resonance_id) -> int`
(decoupled from `ModifierTarget`); `passive_motif_style_bonuses` is a thin wrapper that
gates on `target.target_resonance_id` and delegates to it. The same helper is reused by the
thread survivability coherence amplifier (see below) — single source of truth, no parallel walk.

Two composition invariants are tested in `mechanics/tests/test_aesthetic_composition.py`:

- **Style × Facet coexistence:** An item carrying both an `ItemStyle` and an `ItemFacet`
  contributes to `passive_motif_style_bonuses` (style coherence) AND `passive_facet_bonuses`
  (facet resonance) independently and simultaneously. The two walkers operate on disjoint
  data paths and their results are summed by `equipment_walk_total`.

- **Dilution-only (unbound styles are inert):** The walker iterates only the character's
  `MotifResonanceStyle` bindings for the target resonance. Any worn `ItemStyle` not present
  in those bindings is invisible to the walker — it adds no coverage and applies no penalty.
  Characters may wear items tagged with arbitrary styles without degrading their coherence bonus.

**Admin authoring surface (still present, no longer the only path):** Standalone
`MotifResonanceAdmin` (in `world/magic/admin.py`) with a `MotifResonanceStyleInline`
for the style bindings; `ItemStyle` inline on `ItemInstance`.

**Player-facing style-binding surface (#2030):** binding a `Style` to a claimed
resonance is now a normal player action, not an admin-only edit — telnet, web, and
admin all converge on the same service layer.

- **Service** (`services/motif_style.py`): `bind_motif_style(sheet, style, resonance)`
  (lazy-creates `Motif`/`MotifResonance` if absent, replace semantics — rebinding a
  style already bound elsewhere moves it; cap enforcement delegates to
  `MotifResonanceLink.clean()`, not reinvented), `unbind_motif_style(sheet, style)`,
  `motif_style_bindings(sheet)`. Exceptions: `StyleResonanceUnclaimed`,
  `StyleBindingCapExceeded`, `StyleNotBound` (`exceptions.py`).
- **Actions** (`actions/definitions/motif_style.py`, all REGISTRY, `category="magic"`,
  `target_type=SELF`): `BindMotifStyleAction` (key `"bind_motif_style"`),
  `UnbindMotifStyleAction` (`"unbind_motif_style"`), `ListMotifStylesAction`
  (`"list_motif_styles"`).
- **Telnet** (`commands/motif.py`, `CmdMotif`, key `"motif"`): namespaced subverbs —
  bare `motif` / `motif list` shows bindings, `motif bindstyle <style>=<resonance>`,
  `motif unbindstyle <style>` — mirroring `CmdSignature`/`CmdSanctum`'s namespacing to
  avoid bare-key collisions.
- **Web:** `MotifStyleViewSet` (`views_motif_style.py`, routes under
  `/api/magic/motif-styles/`) — `list`/`bind`/`unbind` dispatch the three Actions above.
  **Character scoping:** an `X-Character-ID` header is resolved via
  `web.api.mixins.CharacterContextMixin` (validated as owned by the requesting account)
  ahead of the caller's active puppet — the same header/ownership contract
  `PathIntentViewSet`/`CharacterGoalViewSet` use. This lets a player view/act on a
  specific owned character's bindings rather than always defaulting to whichever
  character they currently puppet; a header naming an unowned character 404s rather
  than silently falling back to the puppet. No header at all preserves the original
  puppet-only resolution. The Style catalog itself (for the bind picker) is a separate
  read-only endpoint, `StyleViewSet` at `/api/items/styles/` (`world/items/views.py`).
- **Frontend:** `MotifStylePanel` (`frontend/src/magic/components/`), mounted in the
  Spellbook tab below the read-only Motif card — see `frontend/src/magic/CLAUDE.md`
  for the wire contract.
- **Facets (#5021):** the same surfaces tie facets to claimed resonances:
  `services/motif_facet.py` (`bind_motif_facet` / `unbind_motif_facet` /
  `motif_facet_bindings` / `tie_creation_facets`), `BindMotifFacetAction` /
  `UnbindMotifFacetAction` (`actions/definitions/motif_facet.py`), `motif bindfacet|
  unbindfacet <facet>=<resonance>`, `MotifStyleViewSet` `bind-facet/` / `unbind-facet/`,
  `MotifFacetPanel`, and `MotifResonanceAssociationInline` in admin. Unlike styles a
  facet may sit on several resonances; the last tie of a facet a signed flourish needs
  cannot be removed (`FacetNeededByFlourish`) until the flourish is cleared. Creation
  picks facets for the gift resonance (`draft_data.selected_gift_facet_ids`), which opens
  flourishes gated on them in `creation_personalization_options(facet_ids=)`; finalize
  ties them before signing. See `docs/systems/magic.md`.

### Thread System (Resonance Pivot Spec A)

**Authored catalogs (lookup, SharedMemoryModel):**
- `ThreadPullCost` - Per-tier pull cost knobs (tier 1/2/3: `resonance_cost`,
  `anima_per_thread`, `label`). Tuning surface — values here are data; cost
  *shape* lives in `pull_cost_totals` (each thread pays both, #5066).
- `ThreadXPLockedLevel` - XP-locked boundary price list (`level` on the
  internal 10/20/30... scale, `xp_cost`). Mirrors skills' XP locks.
- `ThreadPullEffect` - Authored pull-effect template keyed
  `(target_kind, resonance, tier, min_thread_level)`. `effect_kind` chooses
  payload column: `FLAT_BONUS` / `INTENSITY_BUMP` / `VITAL_BONUS` (+ `vital_target`) /
  `CAPABILITY_GRANT` (FK to `CapabilityType`) / `NARRATIVE_ONLY`. Tier 0 is
  always-on passive; tiers 1–3 are paid pulls. `clean()` + CheckConstraints
  enforce payload/effect_kind shape. **Ship sanctum content (#2736, ADR-0188):**
  tier-0 `SANCTUM` rows are also what a ship's sanctum grants the *vessel* —
  `VITAL_BONUS` with a `SHIP_HULL`/`SHIP_HANDLING`/`SHIP_ARMAMENT` `vital_target`
  for the stat lean, `CAPABILITY_GRANT` for the capacity. Two rows per resonance,
  split by `min_thread_level` (0 and 3), because `threadpulleffect_lookup_key`
  admits one row per `(target_kind, resonance, tier, min_thread_level)`. Read by
  `world/ships/sanctum_bonus.py`; the character-side `passive_vital_bonuses` skips
  the three ship targets. Zero rows authored in the lore repo today, so the ship
  grant is currently inert. **Relationship pull content (#2021):**
  `ensure_relationship_pull_content()` seeds survivability-skewed rows for
  `RELATIONSHIP_TRACK` — one 4-tier chain per **authored** resonance. `ThreadPullEffect`
  is seeder-owned tuning data, not `CONTENT_MODELS` content, so covering the whole
  catalog is free. Until #2967 it covered four names the seeder invented itself
  (Light/Sanctity/Radiance/Dissolution) and which no player could hold, so a
  relationship thread woven at a real resonance had no pull effects at all; those
  invented rows are also how the lore corpus ended up with resonances masquerading as
  authored content (#2890). **No seeder may create a `Resonance`** — the canonical set
  is 24 resonances in 12 opposed pairs, authored in the content repo, and seeders
  resolve what they need by affinity via `world/magic/seeds_resonance.py`. Tier 0: VITAL_BONUS(DAMAGE_TAKEN_REDUCTION). Tier 1:
  VITAL_BONUS(DEATH_SAVE). Tier 2: RESISTANCE (all damage types). Tier 3:
  VITAL_BONUS(KNOCKOUT_RESIST). `apply_target_modulation` now handles
  `RELATIONSHIP_CAPSTONE` in addition to `RELATIONSHIP_TRACK` —
  `relationship_bond_modulation` generalized via `_thread_relationship_target`
  to resolve the threaded person from either FK.
- `RelationshipBondPullTuning` - Singleton (pk=1, `get_relationship_bond_pull_tuning()`)
  tuning surface for `relationship_bond_modulation` (`world/magic/services/
  pull_modulation_relationship.py`, #1849, ADR-0092), the RELATIONSHIP_TRACK sibling of
  Court's `court_regard_modulation`. Base term is keyed on `CharacterRelationship
  .pair_depth()` — the tie's depth summed across both sides; two additive valence-aware
  terms (#2034, ADR-0110, redrawn for the side-row/label model in #3957) sit on top, each
  with its own soft-cap columns on the same singleton: **fraught** (`fraught_coefficient/
  _cap/_half_saturation`, keyed on `min(bond.affection, bond.conflict)` — rewards a bond
  that has moved BOTH gauges at once) and **devotion**
  (`devotion_threshold/_coefficient/_cap/_half_saturation`, keyed on
  `max(0, pair_depth() - devotion_threshold)` — rewards raw depth past a
  threshold, no ritual/ceremony gate). All three terms reuse `_soft_cap`
  (`world/magic/services/threads.py`); see docs/systems/magic.md's "Relationship Bond
  Pull Modulation" section for the full formulas.
- `ThreadSurvivabilityTuning` - Per-`VitalBonusTarget` tuning row for the
  universal thread survivability baseline (#1175). One row per target — five
  at launch: `MAX_HEALTH`, `DAMAGE_TAKEN_REDUCTION`, and the three threshold-save
  vectors `DEATH_SAVE` / `KNOCKOUT_RESIST` / `PERMANENT_WOUND_RESIST` (#1250).
  Fields: `vital_target` (unique choice), `coefficient` (linear multiplier on
  investment score S), `cap` (ceiling the baseline asymptotes toward),
  `half_saturation` (S at which baseline = cap/2), plus the coherence-amplifier
  knobs (#1252) `coherence_scale` (per-resonance coherence bonus that yields +1.0
  to a thread's depth multiplier; 0 disables amplification for this target) and
  `coherence_max_multiplier` (Decimal ceiling on the per-thread coherence factor;
  1.00 = inert). Formula: `round(cap × S / (S + half_saturation))` where
  `S = coefficient × Σ depth(t) × coherence_factor(t)` over all owned threads
  (see the baseline section below). Seeded idempotently via
  `seed_thread_survivability_tuning()` (called by the integration-test dev seed);
  inert until rows exist. Staff-tunable in admin.
- `ThreadWeavingUnlock` - Authored catalog of "you can weave threads on X"
  unlocks. Same discriminator + typed-FK pattern as Thread: `unlock_trait`,
  `unlock_gift`, `unlock_type` (a `RelationshipType`). `xp_cost` + M2M to `Path` (in-band) +
  `out_of_path_multiplier`. SANCTUM threads do not require a
  `ThreadWeavingUnlock` — the anchor cap (`sanctum.feature_instance.level × 10`)
  is the only gate at imbue time.
- `ThreadCrossingThreshold` - Authored gate at thread-level PathStage crossing
  levels (30, 60, 110, 160, 210: the Path crossings times ten, stored thread levels,
  ADR-5091). Keyed on `(target_kind, level)` so a level-30 GIFT
  crossing can require different things than a level-30 COVENANT_ROLE crossing.
  Requirements attach via the polymorphic `thread_crossing_threshold` FK on
  `AbstractUnlockRequirement` (the generalized base formerly
  `AbstractClassLevelRequirement`). Possession-only — items are never consumed
  (#1885, ADR-0090). Fail-open: no row for `(target_kind, level)` → no gate.
  The imbuing loop (`spend_resonance_for_imbuing`) checks for a threshold
  before advancing to a crossing level; if requirements are unmet, it sets
  `blocked_by="CROSSING_REQUIREMENT"` and stops. `is_thread_crossing_level(level)`
  in `services/threads.py` names a thread crossing (a multiple of 10 whose `level // 10` is a
  Path crossing per `world/classes/services.is_crossing_level`).
- **Thread caps (#4585).** `compute_level_cap(sheet)` = character level ×
  `PATH_LEVEL_CAP_MULTIPLIER` (10; never 0, since `get_character_path_level` returns at
  least 1). `compute_effective_cap` = min(level cap, anchor cap) is the ONLY place the
  level cap applies; anchor caps hold only what the anchor imposes (ORGANIZATION = the
  org grant cap, GIFT = the level cap, FACET = `lifetime // ANCHOR_CAP_FACET_DIVISOR`).
  No cap reads Path stage. Blocked reason `LEVEL_CAP`; serializer field `level_cap`.
- **One scale (#5091, ADR-5091; was the #4585 shown level).** A thread shows its stored
  level, like stats and skills (a thread at 30 reads 30). Every authored thread threshold
  (crossings, `unlock_thread_level` on variants/sub-roles/`CovenantRoleGiftGrant`/
  `VowAddedEffect`, `min_crossing_level`, `ThreadPullEffect.min_thread_level`,
  `CREATION_PERSONALIZATION_MAX_LEVEL` = 10) is a stored level compared directly against
  `thread.level`. Formulas tuned "per 10 thread levels" (soul tether caps, the Hollow's
  size, facet effect bonuses, vow added-effect and maneuver-effect scaling, derived amounts,
  the outfit trickle, the vow size step, substance power) count `thread_rung(level)`
  (`level // THREAD_RUNG_SIZE`, `services/threads.py`), an internal step never shown.
- `ImbuingProseTemplate` - Fallback prose for the Imbuing ritual keyed on
  `(resonance, target_kind)`. The row with both NULL is the universal fallback.
- `Ritual` - Authored magical procedure. Dispatch kinds: `SERVICE` →
  `service_function_path`; `FLOW` → FK to `FlowDefinition`; `CEREMONY` →
  creates `PendingRitualEffect` (finisher command completes the ritual);
  `SCENE_ACTION` → fires a check via `RitualCheckConfig`.
  `site_property` optionally gates where it can be performed.
  A SERVICE ritual's path is picked in the Ritual admin from the registry
  `service_rituals.SERVICE_RITUAL_FUNCTIONS` (`RitualAdminForm`; unlisted paths refused).
  Add a new SERVICE function there in the PR that adds it.
- `RitualComponentRequirement` - FK to `Ritual`, `quantity`, optional `min_quality_tier`,
  and exactly one of three modes (DB `CheckConstraint`): `item_template` (template mode),
  `min_touchstone_tier` (touchstone mode, #707), or `matches_target_resonance` (target-resonance
  mode, #4733; optional `min_item_meaning` opens the keepsake route, allowed only in this mode).
  Resolved by `resolve_ritual_components` (no writes) and consumed by
  `resolve_and_consume_ritual_components` during ritual dispatch.
- `PendingRitualEffect` - In-progress CEREMONY record. Unique per
  `(character, ritual)`. Created by `PerformRitualAction` on CEREMONY invocation;
  consumed (deleted) by the finisher action (`WeaveThreadAction`, `ImbueThreadAction`)
  on success.

**Per-thread and per-character records:**
- `Thread` - The thread row. Discriminator (`target_kind`) + typed FKs:
  `target_trait`, `target_technique`, `target_facet`,
  `target_relationship` (the weaver's own `CharacterRelationship` side, #3957),
  `target_capstone`, `target_covenant_role`,
  `target_gift`, `target_mantle`, `target_sanctum_details`. Fields: `owner` (FK CharacterSheet), `resonance`
  (FK Resonance: the LEADING resonance, a denormalized copy of the first `ThreadResonance` row,
  never written directly), `name`, `description`, `developed_points`, `level`, timestamps,
  `retired_at` (soft-retire), `slot_kind` (required for SANCTUM threads —
  `SanctumSlotKind`: PERSONAL_OWN / COVENANT / HELPER),
  `signature_bonus` (nullable FK → `SignatureMotifBonus`, PROTECT — only settable on
  TECHNIQUE-kind threads; enforced by `clean()` + DB CheckConstraint
  `"thread_signature_bonus_technique_only"`; #1582 ADR-0072).
  All typed FKs use `on_delete=PROTECT`. Three layers of integrity: `clean()`, per-kind
  CheckConstraints, per-kind partial UniqueConstraints (one live thread per `(owner, anchor)`:
  resonance is not part of the key since #5123; weaving on a taken anchor raises
  `ThreadAnchorTakenError` with a pointer to imbuing it).
  **SANCTUM anchor:** `Thread.target_sanctum_details` (FK to `SanctumDetails`).
  Anchor cap = `sanctum.feature_instance.level × 10`. The thread is pull-applicable
  ("in-sanctum boost") while the character is inside the Sanctum's room.
  **Bare ROOM `target_kind` removed** — use SANCTUM for room-anchored threads.
  `ThreadSerializer.display_name` (#5123) is the thread's own name, else `thread_display_name` (`crossing/handlers.py`): its anchor's label, so a Gift thread reads as its Gift.
- `ThreadResonance` (#5123, ADR-5123-A) - One resonance's `amount` inside a Thread: the
  CUMULATIVE total of that resonance ever imbued, never lowered by a level-up spending
  `developed_points` (so it does NOT sum to `developed_points`). Unique `(thread, resonance)`;
  Meta ordering `(thread, -amount, id)`, so the first row is the leading resonance and a tie
  goes to the row created first. Written only by services in `services/thread_rows.py`
  (`add_to_resonance_row` for imbuing, `write_resonance_rows` for weaving and creation at 0,
  `refresh_leading_resonance` after every write); the retune rite and the Fall and Redemption
  move or scale amounts, and a row that empties is deleted unless it is the only one. Every
  writer calls `character.threads.invalidate()` (the handler caches rows: `resonances_of`,
  `amount_of`). Read-only inline in admin. A row at 0 means the resonance is known but never
  imbued: it pays a pull and gives no perks.
- `ThreadLevelUnlock` - Per-thread XP-locked-boundary receipt. Unique per
  `(thread, unlocked_level)`. Records that a thread paid XP to cross a
  specific boundary (20, 30, ...).
- `CharacterThreadWeavingUnlock` - Per-character purchase record linking a
  CharacterSheet to a ThreadWeavingUnlock. Captures actual `xp_spent`
  (in-band uses unlock.xp_cost; out-of-band multiplies by
  `out_of_path_multiplier`) and optional `teacher` (FK RosterTenure).
- `ThreadWeavingTeachingOffer` - Teacher-side offer. FK to RosterTenure +
  ThreadWeavingUnlock. Mirrors `CodexTeachingOffer` shape (pitch, gold_cost,
  banked_ap). Path multiplier computed at acceptance time, not stored.

**Universal survivability baseline (services/threads.py, #1175 / #1250 / #1251 / #1252):**

A character's breadth × depth of thread investment contributes a passive survivability
bonus across every vector likely to kill them — max-health, damage reduction, and the
death/knockout/permanent-wound threshold saves — independent of authored `VITAL_BONUS`
pull-effects. The baseline is amplified per-thread by the fashion/motif coherence of each
thread's own resonance (dress the part for the resonance you invested in → harder to kill).

- `seed_thread_survivability_tuning()` — idempotently creates the five default
  `ThreadSurvivabilityTuning` rows (DR: coeff=1, cap=20, half=8; MAX_HEALTH: coeff=1,
  cap=80, half=10; DEATH_SAVE / KNOCKOUT_RESIST / PERMANENT_WOUND_RESIST: coeff=1,
  cap=15, half=8). Called by the dev seed.
- `get_thread_survivability_tuning(vital_target) -> ThreadSurvivabilityTuning | None` —
  fetches the tuning row for a given `VitalBonusTarget`; returns `None` if not yet seeded
  (baseline is 0 when absent).
- `survivability_baseline(character, vital_target) -> int` — `round(cap × S / (S + half))`
  where `S = coefficient × Σ depth(t) × coherence_factor(t)` over owned (non-retired)
  threads, `depth(t) = thread_level_multiplier(thread.level)` (#1718 — `Decimal(level // 10)`
  unchanged for level ≥ 10, `Decimal(1)` at level 0, a linear ramp from 0.1 to 1.0 for
  levels 1-9), and
  `coherence_factor(t) = min(coherence_max_multiplier, 1 + motif_coherence_bonus(sheet,
  thread.resonance) / coherence_scale)` (factor 1.0 when `coherence_scale` is 0). An
  uncoordinated wardrobe yields factor 1.0 — no penalty (dilution-only rule); a lone wolf
  (no threads) gets 0.
- `survivability_save_baselines(character) -> ThreadSurvivabilitySaves` — frozen dataclass
  (`wound`/`death`/`knockout`) bundling the three threshold-save baselines.

The baseline is injected at these call sites:

- `apply_damage_reduction_from_threads(character, damage_amount) -> int` — subtracts the
  DR baseline. Called from combat (`apply_damage_to_participant`) AND from the non-combat
  damage seams that previously bypassed it: `_deal_damage` (mechanics effect-handler;
  traps + consequence damage) and `_apply_round_tick_damage` (condition DoT) (#1251).
- `recompute_max_health_with_threads(character_sheet) -> int` — adds the MAX_HEALTH
  baseline to the base max-health figure. Called at weave and imbue time.
- `process_damage_consequences` (`world/vitals/services.py`) adds the matching save
  baseline to each tier's roll `extra_modifiers` (wound←PERMANENT_WOUND_RESIST,
  death←DEATH_SAVE, knockout←KNOCKOUT_RESIST) (#1250). Because all damage — combat, DoT,
  and traps — funnels its threshold rolls through this one function, hazard/DoT saves are
  covered for free.

**Damage-type RESISTANCE pull-effect (#1580):** distinct from the damage-type-agnostic DR
above. `EffectKind.RESISTANCE` (+ `resistance_amount`, `resistance_damage_type` FK; null =
all types) is the species-gift thread's mitigation that offsets the species drawback's
negative `ConditionResistanceModifier` (a vulnerability). `gift_thread_resistance(character,
damage_type) -> int` (services/threads.py) returns the POSITIVE total — passive tier-0
(flat `resistance_amount`, gated by `min_thread_level`, via
`CharacterThreadHandler.passive_damage_type_resistance`) plus active paid-pull snapshots
(`scaled_value = resistance_amount × level_multiplier`, via
`CharacterCombatPullHandler.active_pull_resistance`). It is summed with
`character.conditions.resistance_modifier(damage_type)` into the SAME clamped subtraction in
`apply_damage_to_participant` (combat) — the one seam where the drawback vulnerability is
read — so drawback and gift resistance net. GIFT threads are pullable (added to
`_ALWAYS_IN_ACTION_KINDS`: a species gift is intrinsic, always in-action). The DoT/trap seams
apply neither condition resistance nor this gift resistance, so they stay byte-identical.

**Pull perks by payer (#5123, ADR-5123-A).** `get_pull_effects_for_thread(thread, payer, ...)`
(`services/pull_effects.py`) filters `ThreadPullEffect` on the PAYER, not on `thread.resonance`;
`resolve_pull_effects(..., payers=)` and `thread_power_term` pass it. The thread level the payer's
perks read is `thread_rows.payer_level_read(thread, payer)`: the leading resonance reads
`thread.level`; another resonance with a nonzero row reads `max(0, level -
DriftConfig.second_resonance_level_step)`, falling back to the leader's level when the lower
level's `thread_level_multiplier` would beat the leader's (the curve is not monotonic below
10); another resonance with no row, or a row at 0, gets `None` and no perks (the leading resonance
always reads the thread's level, even at 0), but still pays an ordinary
pull (the cost and the pull's plain benefit). That level feeds both the `min_thread_level` gate
and the multiplier. Tier 0 (always-on) resolves only when the payer is the leading resonance,
and the tier-0 passives outside pulls (`handlers.py`, `mechanics/services.py`,
`companions/services.py`) key on the leading resonance. Pull applicability counts a thread
when ANY resonance with a row would have an effect, since it runs before the payer is chosen.
Aura alignment power (`power_terms._aura_alignment`) is one bonus, the largest over the cast's
working affinities and the payers' affinities: the full `affinity_alignment_bonus` for an
affinity with a settled share above zero, else the current percent, so a mixed character is
never weaker than a pure one and a pull never lowers it. A worn alternate self keeps the
acting-aura reading.

**Combat-side models (live in `world/combat`, not magic):**
- `CombatPull` - Per-(participant, round) commit envelope for a thread pull.
  Unique per (participant, round_number). The threads pulled are `CombatPullThread` rows
  (`pull_threads`; M2M `threads` through them, #5123), each carrying `paying_resonance`;
  `resonance_spent` / `anima_spent` for audit. Committed via
  `world/combat/pull_helpers.commit_combat_pull` (not called directly).
- `CombatPullResolvedEffect` - Frozen snapshot of one resolved effect from
  a pull. Captures `kind`, `authored_value`, `level_multiplier`, `scaled_value`,
  `vital_target`, `resistance_damage_type` (RESISTANCE only; null = all types, #1580),
  `source_thread`, `source_thread_level`, `source_tier`,
  `granted_capability`, `narrative_snippet` (copied only for the kinds whose payload
  constraint allows prose, NARRATIVE_ONLY and CORRUPTION_RESISTANCE; blank on a numeric
  kind). `level_multiplier` is the rounded int; the preview's wire field of that name is the
  exact one (`ResolvedPullEffect.level_multiplier_exact`, 0.9 at level 9). Cascades from CombatPull;
  edits to authoring or Thread.level mid-round cannot retroactively alter
  what a committed pull granted.

**Note:** Affinity and Resonance are proper domain models in this app, each with an
optional OneToOne FK back to ModifierTarget for modifier system integration.

### Specialization Engine (ADR-0055 — #1578)

A character's specialized techniques and capabilities are resolved by combining an
entity they hold — a **Gift**, **Path**, or **Covenant Role** — with their **resonance**
(and, where a thread is woven, that thread's level) through **one shared specialization
primitive**, not per-entity bespoke logic. The specialized form is **derived on read**
(ADR-0014): a resonance change instantly re-specializes every affected technique with no
regeneration step.

- `AbstractSpecializedVariant` — shared abstract base (SharedMemoryModel), the "one
  specialization engine." Carries the `matching_variant` selection predicate (highest
  `unlock_thread_level ≤ thread level` at the thread's resonance), the
  `newly_crossed_variants` discovery query, and the `discovery_narrative(is_first)`
  ceremony contract (`is_first=True` → gamewide recipients; `is_first=False` → `[]`,
  ceremony appends `[thread.owner]`).
- `TechniqueVariant` — concrete subclass. A resonance-specialized form of a parent
  `Technique` (`parent_technique` self-FK, `related_name="variants"`). Fields:
  `resonance`, `unlock_thread_level` (≥30 = variant, a thread level), `name_override`,
  `intensity_delta`, `control_delta`, `discovery_achievement`, `codex_entry`. Unique per
  `(parent_technique, resonance, unlock_thread_level)`.
- `CovenantRole` — refactored to inherit `AbstractSpecializedVariant` (schema no-op;
  `parent_role` with `related_name="sub_roles"` is the variant parent).
- `TechniqueVariant.cached_effect_summary` (#2901) — the per-form sibling of
  `Technique.cached_effect_summary`. A resolved form is fully determined by
  `(parent_technique, variant)` with no caster input, so it caches on the variant row;
  invalidate with `invalidate_variant_payload_caches`.

**Per-caster forms — `available_technique_forms` (#2901)**
(`services/technique_forms.py`): the display counterpart to the resolver. A variant does
NOT replace a technique — it makes an alternate version available — so the character sheet
and the in-scene cast list carry a **list** (base form + each unlocked variant + the next
locked one per resonance), never one collapsed answer. `technique_signature_payload`
returns the signature beside it, never inside it (ADR-0072).
**Invariant: every entry is produced by calling `resolve_specialized_variant`** once per
candidate resonance — never by re-implementing `matching_variant`'s predicate. The
`is_default` marker must come from the `preferred_resonance=None` call, since that is the
path carrying the alt-self resonance override.
**Trap this closed:** `_ResolvedTechnique` exposed `damage_profiles` etc. while every
payload reader reads `cached_damage_profiles`, so `__getattr__` forwarded those to the
parent and a variant summarised as the base form under the variant's name. All four
`cached_*` names are now declared on it; `cached_removed_conditions` is parent-only
because no `TechniqueVariantRemovedCondition` model exists.

**Resolver — `resolve_specialized_variant(*, entity, character)`**
(`world/magic/specialization/services.py`): the single specialization resolver.
`Technique` → `_ResolvedTechnique` value object (wraps parent + matching variant,
exposing `name`/`intensity`/`control` with deltas; raw parent `Technique` when no variant
matches). `CovenantRole` → the matching sub-role variant. Both paths read the active
thread through the cached `character.threads` handler (the same cached queryset the
passive bonuses read), never a fresh `Thread.objects.filter()`; a character with no
`CharacterSheet` degrades gracefully (returns the parent entity / the Gift's `resonances` list). The
GIFT-thread write-paths (`provision_latent_gift_thread`, `_weave_gift_thread`) call
`character.threads.invalidate()` after mutation, mirroring the covenant-role
invalidation contract. `_ResolvedTechnique`'s payload accessors
(`damage_profiles`/`capability_grants`/`condition_applications`) read their source's
single `cached_<payload>` list (on `Technique`/`TechniqueVariant`) rather than issuing a
`.exists()` + `.all()` pair. `resolve_effective_role` is now a one-line shim over this
resolver; no parallel specialization systems (ADR-0016).

**Crossing ceremony — `execute_crossing_ceremonies(*, thread, starting_level, new_level)`**
(`world/magic/crossing/ceremony.py`, ADR-0094): dispatches on `thread.target_kind` via a handler
registry so every `TargetKind` gets a ceremony at PathStage crossings (thread
levels 30, 60, 110, 160, 210, `is_thread_crossing_level`).
GIFT/COVENANT_ROLE handlers wrap the existing variant-discovery logic
(`AbstractSpecializedVariant.newly_crossed_variants` → achievement + codex + narrative). The
other kinds use the `_CrossingChoiceHandler` base (player-choice buffs from the
`CrossingOption` catalog) or the `TechniqueCrossingHandler` (narrative-only beat). A shared
`execute_ceremony_beat` helper lets non-variant kinds fire the same beat without an
`AbstractSpecializedVariant`. Called from `spend_resonance_for_imbuing` on every thread advance;
also standalone-callable. (`world/covenants/discovery.py` re-exports it as
`fire_variant_discoveries` for backwards compatibility.)

**GIFT thread substrate:**
- `TargetKind.GIFT` + `Thread.target_gift` FK (PROTECT) — a thread anchored to a Gift. One
  active GIFT thread per `(owner, gift)`, holding every resonance the character put into the
  Gift on its `ThreadResonance` rows (#5123); a second resonance is a row on that thread, never
  a second thread (`provision_additional_gift_thread` is gone).
- `grant_gift_to_character(sheet, gift, *, resonances=(), origin=...)`
  (`world/magic/specialization/services.py`; `resonances` are the preferred resonances, leading
  first, every one kept on the Gift thread, none named means resolve one) — the shared gift-acquisition primitive
  (path-crossing grant, species-gift provisioning, CG's gift-stage finalize, and
  `charge_and_learn`'s implicit gift acquisition all call this, not
  `provision_latent_gift_thread` directly). Mints (idempotently) the `CharacterGift` link
  and **always** provisions the gift's latent level-0 GIFT thread — resonance is resolved by
  `_resolve_grant_resonance` **before** the `CharacterGift` row is minted, so a raise leaves
  no partial state. In order (the single-resonance fallback, used when no preferred resonance
  is named): the caller's explicit pick, whatever the gift lists; an existing active GIFT thread already covering
  this gift, lineage-aware via `gift_threads_for` (makes a re-grant a true no-op; its leading
  resonance); a
  non-empty `Gift.resonances` list's claimed-or-first member (the list's one role: a default);
  the character's own earliest GIFT
  thread's resonance (their "main" one); their highest-`lifetime_earned` claimed resonance;
  the anima-ritual resonance. Raises `GiftResonanceUnresolvable` if nothing resolves — an
  empty `Gift.resonances` no longer means "skip provisioning the thread" (#2971); see ADR-0203.
- `provision_latent_gift_thread(sheet, gift, *, resonances)` — the idempotent level-0 GIFT
  thread writer `grant_gift_to_character` calls once resonances are resolved; it writes a
  `ThreadResonance` row at amount 0 per resonance in the order given (the first leads a tie),
  then `refresh_leading_resonance`. An existing thread on the gift is returned unchanged
  (the list is ignored). Not called directly by any grant call site anymore.
- `weave_thread(target_kind=GIFT)`: provisions the character's one thread on the gift at the
  named resonance (any resonance: the gift's `resonances` list limits nothing, and
  `UnsupportedGiftResonanceError` is gone, #5123); a gift that already has a
  thread raises `ThreadAnchorTakenError` ("imbue it instead"), as does every other anchor kind.
- `gift_resonances_for(character, gift) -> list[Resonance]` — the derive-on-read seam
  replacing `technique.gift.resonances.all()` at the four cast sites (`power_terms`,
  `techniques` ×2, `resonance_environment` ×2). Reads the active GIFT thread through the
  cached `character.threads` handler; returns the thread's resonances in row order (leading
  first, #5123), falling back to `gift.cached_resonances` (the authored `Gift.resonances` list) when
  no thread or no sheet. `_first_gift_thread_resonance`, `_effective_variant_resonance` and
  the technique forms read the leading resonance; `technique_forms` lists a form for every
  resonance the thread holds.
- `Gift.resonances` limits nothing (owner ruling 2026-11-14, #5123): a Gift is the substance
  and resonance is how the character feels using it, so any resonance she holds can feed any
  Gift's thread. The list is only the default `_resolve_grant_resonance` reaches for when a
  grant names no resonance (and what a sheetless character's gift manifests as). It is not the
  cast-time value (ADR-0052). Weaving, imbuing (`imbue_ready_threads`, the retune rite's
  options, `ImbuePanel`) and creation read no list; the thread payload has no
  `allowed_resonance_ids`.

**GIFT anchor cap (#1580, #4585):** `compute_anchor_cap` handles `TargetKind.GIFT` by
returning `compute_level_cap(thread.owner)` (character level × 10). GIFT threads are
always in-action (`_ALWAYS_IN_ACTION_KINDS`; a species gift is intrinsic). The frontend CG
resonance step is built (`GiftStage`'s `StrengthStep`, #1620/#2426 Task 10, rebuilt in #5231), which
writes `gift_resonance_weights` as one Primal pick and at most one Celestial or Abyssal pick.
Proven end-to-end by
`world/magic/tests/integration/test_gift_specialization_e2e.py` (#1578) and
`world/magic/tests/integration/test_species_gift_e2e.py` (#1580).
- **Species gift provisioning** — `SpeciesGiftGrant` (`world/species/models.py`; natural key
  `(species, gift)`) is the through-model linking a species to MINOR Gifts with an optional
  `drawback_condition` FK. `provision_species_gifts(sheet, *, resonances=())`
  (`world/species/services.py`) is called from `finalize_magic_data` after the Major-gift
  block; mints the MINOR `CharacterGift` via `grant_gift_to_character`, applies any
  drawback idempotently. Character creation passes its picks (one Primal and at most one Celestial or Abyssal, heaviest first), so a
  species gift's thread starts with the same rows; empty `resonances` lets the shared resolver
  anchor the Minor Gift's thread to the character's Major-gift thread's leading resonance,
  since that thread already exists by the time species gifts provision
  (`finalize_magic_data`'s ordering runs the Major-gift block first). See ADR-0071, ADR-0203.
- **Gift-specific pull-effect lookup** — `get_pull_effects_for_thread(thread, payer, **filters)`
  (`world/magic/services/pull_effects.py`): for `TargetKind.GIFT` threads, tries rows where
  `target_gift == thread.target_gift` first, falls back to `target_gift IS NULL`; all other
  kinds get only `target_gift IS NULL` rows.

**Path-crossing grant — the (Gift × Path) base-technique-set leg (#1579, ADR-0055):**
#1578 built the *resonance* leg (how a known technique manifests); #1579 builds the
*(Gift × Path)* leg as an **acquisition** (which techniques you get):

- `PathGiftGrant` (`models/grants.py`, the `PathRitualGrant` through-model shape) authors,
  per `(path, gift)`, a curated `starter_techniques` M2M subset of *that gift's* techniques:
  the techniques for that Path and Gift (#4555, ADR-4555-A). A technique is offered only on the
  Paths that list it; a `TraditionGiftGrant.special_techniques` listing restricts it to the
  listing Traditions (`cg_catalog.tradition_listings` / `offered_to_tradition`), and
  `grant_path_magic` skips a technique the character's active Tradition may not take.
  The same authored Gift grants a different set per path (a warrior-line and a spy-line path
  both grant Pyromancy, but different techniques from it). `clean()` rejects a starter
  technique not belonging to the grant's gift; unique per `(path, gift)`.
- **Tradition teaching fit (slice 2 of #4659, ADR-4659-B).** A `TraditionGiftGrant` row marks a
  Gift the Tradition favors; it does not gate the Gift pick (ADR-4659-A). `Tradition.favored_affinities`
  (M2M `Affinity`) marks the affinities it favors. `teaching_fit(tradition, gift, affinity)` in
  `services/teaching_fit.py` is the one resolver: affinity fit is that `Affinity` row being in
  `favored_affinities` (by pk, through foreign keys only); the numbers live in the
  `TraditionTeachingConfig` singleton (`get_teaching_config()`). Character creation
  (`CharacterDraft.magic_training_pool`) passes the picked Gift resonance's `affinity`; the Academy
  goes through `student_fit(tradition, student_traits(sheet))` (`npc_services.effects._course_terms`,
  `services._teaching_lines`), where `student_traits` reads the Major Gift (`major_gift_for`) and the
  affinity of the resonance on the student's active GIFT thread for it (`gift_affinity_for`, via
  `specialization.services.gift_threads_for`; None without one). Fit by the character's aura is
  deferred to #4672. Fit is a bonus or an ease, never a rule about who may teach.
- **Which Traditions teach which skills (#5326, ADR-5326).** No Magic-category skill is learned by
  self-study. `Tradition.taught_skills` (M2M `Skill`, `limit_choices_to` the Celestial and Abyssal affinities'
  skills) says which of Heroism and Villainy a Tradition's teachers teach; Reflection (the Primal affinity's
  skill, found by `AFFINITY_PRIMAL`) is taught by every Tradition with no tick; a fighting style's skill by the
  Traditions in `CombatStyle.taught_by`; every other Magic skill by every Tradition. It is not
  `favored_affinities`, which is a fit bonus and never decides who may teach. One rule module answers
  for creation, weekly training and courses: `services/tradition_teaching.py` (`tradition_teaches`,
  `is_tradition_governed`, `is_outsider`, `build_teaching_context` -> `TeachingContext`, `training_verdict` ->
  `TrainingVerdict.refusal`; value types in `types/tradition_teaching.py`). Build a `TeachingContext` once per
  call chain and pass it down, never store it; it must hold every student and mentor sheet asked about,
  their players and the student's lever when each is asked (`KeyError` otherwise, never "no Tradition" or
  "no lever"); `build_outsider_context` is the one for callers that never ask `training_verdict`. A skill that
  is both an affinity's and a style's follows the affinity's list. `tradition_teaches` and `is_tradition_governed`
  read the same context, so the one-question and batch answers cannot differ. Her own character is never her
  mentor, nor another character her player plays; a mentor who agreed and no longer qualifies gets one weekly line that names only the
  persona she typed (`MENTOR_CANNOT_TEACH`), whatever the reason. A mentor must agree (#5326, ruled 2026-11-28):
  naming a mentor only asks her (`training_asking_refusal` reads nothing about her), a mentor who has not agreed
  counts as no mentor in `training_verdict(..., mentor_agreed=)`, and she reads which of her own facts fails when she
  accepts (`mentor_acceptance_refusal`, `world/skills/mentoring.py`). The Tradition's state (self-taught, teachers gone, living) is
  never read. A student whose own Tradition does not teach a governed skill is an outsider: her Academy
  course sessions add `TraditionTeachingConfig.other_tradition_course_difficulty` (default 0), weekly mentoring
  carries no penalty. The exception is the `self_teaching` lever (`world.mechanics.levers.self_teaching_granted`),
  a staff-authored distinction effect. Do not read the rule anywhere else; call the module. See
  `docs/systems/magic.md`, "Which Traditions teach which skills"; Required content rows
  `affinity-skills-taught`, `governed-skills-taught` and `courses-taught-by-their-tradition`.
- `grant_path_magic(sheet, path)` (`services/path_magic.py`, returns `PathMagicGrantResult`)
  mints, idempotently, `CharacterGift` + the latent GIFT thread (reusing
  `provision_latent_gift_thread`) + `CharacterTechnique` rows for the path's `PathGiftGrant`
  sets, then announces via `announce_access_change` (`AccessChangeSource.PATH_ADVANCEMENT`).
  Resonance for the latent thread = a claimed resonance in the gift's `resonances` list (its default role), else the
  list's first (the player commits the real choice later via the Rite of
  Weaving). XP/advancement *gates* the crossing (ADR-0053); the grant is a consequence of path
  membership (ADR-0050), not an XP purchase.
- **Hook:** `cross_threshold` (`audere_majora.py`) calls `grant_path_magic(sheet, chosen_path)`
  right after writing `CharacterPathHistory` — so *which* levels grant is pure authored data
  (`AudereMajoraThreshold` rows). A POTENTIAL (level-3) "pre-crossing" reuses the identical
  machinery; its lesser-ceremony wording is authored on the threshold row.
- Proven end-to-end by `world/magic/tests/integration/test_path_crossing_grant_e2e.py`.

### A cast is worked in one resonance (#5231, ADR-5231)

Full reference: `docs/systems/magic.md` "A cast is worked in one resonance".

- **The resonance.** `cast_resonance_for(character, technique, preferred, *, refuse_off_thread=True, sheet=, alt_resonance=)`
  (`specialization/services.py`): the named resonance, else a worn alternate self's, else the leading
  resonance of the Gift's thread (`_effective_variant_resonance`'s order); a caster with no thread on
  the Gift works the resonance she named when a role thread holds it, else the Gift's first in the order
  Primal, Celestial, Abyssal; a technique with no Gift or a Gift with no resonance is worked in none.
  `resonance_on_gift_thread` is the one test of whether a named resonance has a row on a thread her forms
  come from (the Gift's thread and the threads `technique_forms._candidate_threads` lists, a covenant
  role's thread included): `cast_resonance_for` raises `ResonanceNotOnGiftThread` ("That resonance is not part
  of this Gift's thread.") when it fails, declaration (`declare_action`, the telnet cast, the web dispatch)
  and scene requests refuse the same way before anything is charged, and a stored choice for which it
  fails is dropped to the default at round resolution (`resolve_combat_technique`) and at scene consent
  (`_stored_cast_resonance_still_held`), never a refusal or an aborted round. `use_technique` reads it first.
  Choosing the base form does not change it.
- **Where the choice is stored.** Fights: `CombatRoundAction.cast_resonance`, the record of the resonance
  the declared cast is worked in (every other combat declaration writes it back to None; a passive-slot
  call keeps the focused cast's, dropped to None when the thread has lost it; an enchanted Strike names no
  resonance and has no picker, so it is always worked in the default resonance and its combat descriptor
  carries no `cast_resonance_options`). The combat doors refuse an off-thread pick with
  `refuse_resonance_off_thread` before the pull is committed. Scenes: the body key `preferred_resonance_id`,
  stored on `SceneActionRequest.cast_resonance` by the consent-gated and hostile-awaiting-consent routes and
  used when the request resolves. The field has one meaning, the resonance the player named while the
  request is pending (null: she named none); an immediate cast or an accepted hostile cast writes nothing to
  it. Telnet: `variant=<resonance>`.
- **Corruption follows it.** `_build_resonance_involvements` gives the whole `runtime_intensity` to the
  cast's resonance; a pull's spend still attaches to the resonance that paid for it. In
  `accrue_corruption_for_cast`, `cast_corruption_part` is 100 once the Abyssal share of the caster's true
  aura reaches `CorruptionConfig.full_corruption_from_share`, else `light_corruption_percent` (no aura, or a game with no Abyssal
  affinity row, counts as 100: a missing row never raises out of a cast); it reduces the ordinary tick (the cast's resonance and a pull paid in an Abyssal resonance), never
  the hasty-fall part, and is read only when some ordinary tick is above zero. The tick is
  `ceil((ordinary * part / 100 + hasty_fall) * leak_percent / 100)`, one rounding up (`_raw_tick` is exact).
- **Power follows it.** `PowerTermContext.cast_resonance`. Every resonance-tied power term reads the cast's one
  resonance through `cast_working_resonances(character, technique, cast_resonance)`
  (`specialization/services.py`; every Gift-thread resonance only where no cast resonance exists): the
  touchstone term, the aura term's standing and alignment (pulled threads' payers still join the alignment),
  the resonance scope of POWER and maneuver-effect targets (`technique_effect_context(cast_resonance=)`) and
  the place's reaction (`evaluate_resonance_environment(cast_resonance=)`, a worn alternate self's affinity still
  winning). A clash contribution reads the default (`cast_resonance_for`, nothing named). `kindled_cast_power_term`
  adds `kindled_cast_strength` (`cast_power` through `scale_by_kindled_boost` in `services/kindled_math.py`, the
  scaling the pull levels use too) of the cast's resonance, read with `kindled_strength_now`, whether or not the
  cast pulls a thread: kindling's levers stack (giving in, Dig deep, a pull's boost, the cast power) and staff tune
  `cast_power`; suppression by a pull was tried and removed.
- **The options.** `cast_resonance_options(character, technique, sheet=, kindling=, alt_resonance=)`
  (`services/cast_resonance_options.py`, separate from `available_technique_forms`, which still lists only
  variant forms): one `CastResonanceOption` per resonance on the Gift's thread, leading first, with a worn
  alternate self's off-thread default added as its own first entry marked `is_default` (a caster with no thread
  on the Gift gets only her default entry); each carries the
  kindled strength and reasons, `stronger` (the single entry with the highest cast strength, above the
  default's; a tie marks none, `stronger_marks` in `services/kindled_math.py`, the rule the pull dialog's payer options
  share) and `adds_corruption` (its affinity's coefficient above 0). A caller listing several techniques reads
  the kindling once with `kindling_by_resonance`, and her sheet and worn alternate self's resonance once. The scene cast
  payload (`resonance_options`) and the combat availability descriptor (`cast_resonance_options`) carry it,
  and the pickers send `preferred_resonance_id` only for a non-default option.
- **Earning.** `grant_resonance` scales by `resonance.affinity.earn_rate_percent`; the learn rate still
  follows the main affinity (`drift.learn_rate_percent`). The deed decides what is earned, whichever
  resonance powered the cast.

### Resonance Gain Surfaces (Resonance Pivot Spec C)

**Models (new):**
- `ResonanceGainConfig` - Singleton tuning config (pk=1). Fields: `weekly_pot_per_character`,
  `scene_entry_grant`, `residence_daily_trickle_per_resonance`, etc. Lazy-created via
  `get_resonance_gain_config()`.
- `PoseEndorsement` - Unsettled endorsement of a pose; settles at weekly tick. FK to
  `endorser_sheet`, single `resonance` FK (PROTECT). Unique per `(endorser_sheet, interaction)`.
  Captures `persona_snapshot` (FK to `scenes.Persona`, SET_NULL) for masquerade audit, and
  `endorser_persona` (the face the endorser wore, from `active_persona_for_sheet`, set by
  every endorsement writer; the scene feed's endorser badge shows it, #5290; a row with none
  falls back to the endorser's PRIMARY persona; the FK is RESTRICT so deleting a mask that endorsed is refused rather than nulled). Fields:
  `created_at`, `settled_at` (NULL until weekly settlement).
- `SceneEntryEndorsement` - Immediate flat grant for endorsing a character's scene entry
  pose. FK `endorser_sheet`, FK `endorsee_sheet`, FK `scene`, single `resonance` FK (PROTECT).
  Captures `persona_snapshot` (FK to `scenes.Persona`, SET_NULL) for masquerade audit and
  `endorser_persona` (the endorser's presented face, as on `PoseEndorsement`). Unique per
  `(endorser_sheet, endorsee_sheet, scene)`. Fires `grant_resonance` synchronously on creation.
- `ResonanceGrant` - Universal audit ledger. Discriminator `source` (TextChoice: POSE_ENDORSEMENT,
  SCENE_ENTRY, ROOM_RESIDENCE, OUTFIT_ITEM, STAFF_GRANT) + typed FKs: `source_room_profile`,
  `source_staff_account`, `source_pose_endorsement`, `source_scene_entry_endorsement`. FK
  `character_sheet`, FK `resonance`, `amount`. CheckConstraints enforce shape per source.
- **Room resonance data lives in the locations cascade.** What used to be tagged via
  the former `RoomAuraProfile` / `RoomResonance` models is now stored as
  `LocationValueModifier` rows with `key_type=RESONANCE`. See `world/locations/CLAUDE.md`
  and the `tag_room_resonance` / `get_residence_resonances` services in `services/gain.py`.

**Services (`services/gain.py` — new module):**
- `grant_resonance(sheet, resonance, amount, *, source, typed_fk_kwargs)` - Typed-FK signature.
  Writes CharacterResonance + ResonanceGrant atomically. `source` is a GainSource TextChoice.
  Matching typed FK kwarg required per source: ROOM_RESIDENCE → `room_profile=`,
  POSE_ENDORSEMENT → `pose_endorsement=`, SCENE_ENTRY → `scene_entry_endorsement=`,
  STAFF_GRANT → optional `staff_account=`, OUTFIT_ITEM reserved.
- `create_pose_endorsement(endorser_sheet, interaction, resonance=None)` - 8 preconditions
  (self, alt, whisper, private, participation, unclaimed resonance, duplicate). Raises
  `EndorsementValidationError` on failure. A pose whose author reached for a resonance (#5308,
  `Interaction.cached_resonance_reach`) is endorsed for that resonance: `resonance` is ignored and the
  unclaimed-resonance check is skipped, since the author named it. A pose that reached for nothing needs
  `resonance`, claimed by the endorsee, and otherwise answers "Which resonance? This pose did not reach for one."
  The endorse action, `endorse pose <char> [#N] [confirm]` and `PoseEndorsementSerializer` accept a missing
  resonance for a reached pose only.
- `create_scene_entry_endorsement(endorser_sheet, endorsee_sheet, scene, resonance)` -
  Immediate-grant sibling with participation + alt checks.
- `settle_weekly_pot(endorser_sheet)` - Settles all unsettled PoseEndorsement rows for one
  endorser. Distributes `ceil(weekly_pot_per_character / N)` resonance per endorsement.
  Idempotent.
- `residence_trickle_tick()` - Daily pass: for each sheet with residence, write one `TrickleAccrual`
  per matching (aura-tagged ∩ sheet-claimed) resonance. It grants nothing (#5308): an anima ritual
  harvests the rows. Per-character atomic.
- `resonance_daily_tick()` - Master daily tick (residence trickle + the worn-piece trickle, which also
  writes `TrickleAccrual` rows).
- `waiting_trickles(sheet) -> dict[int, int]` - What her days have piled up per resonance id and no
  anima ritual has harvested; the only reading of the accrual rows (#5308).
- `resonance_weekly_settlement_tick()` - Master weekly tick (settle all endorsers).
- `tag_room_resonance(room_profile, resonance, set_by=None)` / `untag_room_resonance(room_profile, resonance)` -
  Idempotent room aura management.
- `set_residence(sheet, room_profile | None)` / `get_residence_resonances(sheet) -> set[Resonance]` -
  Residence declaration + resonance intersection query.
- `account_for_sheet(sheet) -> AccountDB | None` - Walks CharacterSheet → RosterEntry →
  current RosterTenure → PlayerData → Account. Single source of truth for alt-guard.
- `get_resonance_gain_config() -> ResonanceGainConfig` - Lazy-create singleton (pk=1).

**Ticks registered in `game_clock/tasks.py`:**
- `magic.resonance_daily` - 24h
- `magic.resonance_weekly_settlement` - 7d

**API surfaces (`views.py`):**
- `PoseEndorsementViewSet` - POST /api/magic/pose-endorsements/ + DELETE-if-unsettled
- `SceneEntryEndorsementViewSet` - POST-only (delete deferred with ResonanceGrantReversal)
- `StylePresentationEndorsementViewSet` - POST /api/magic/style-presentation-endorsements/ +
  GET detail (create + retrieve only; immutable, no delete/settlement). Frontend caller
  (#2031): `EndorsementControl` (`kind='style'`, `frontend/src/scenes/components/`), mounted
  in `PoseUnit` alongside the pose/entry kinds. Endorsed-✓ has no persisted per-viewer flag on
  the `Interaction` payload (unlike entry's `entry_endorsed_by_me`), so the control derives it
  from the create-mutation's own `isSuccess` for the session.
- `ResonanceGrantViewSet` - Read-only, user-scoped. FilterSet on source/resonance/date range.

**Telnet surfaces (`commands/endorse.py`, `commands/fashion.py` — #1340):**
- `CmdPoses` (`poses <char>`) — lists endorseable poses in the current scene via
  `get_endorseable_poses_in_scene()`; respects WHISPER receiver and VERY_PRIVATE
  participation gates.
- `CmdEndorse` (`endorse pose/entry/style <char> resonance=<name>`) — two-phase pose
  endorsement (preview → confirm) + one-shot entry/style; converges on the same
  `PoseEndorseAction` / `SceneEntryEndorseAction` / `StylePresentationEndorseAction`
  the web serializers use. Active scene resolved from caller's room.
- `CmdJudgePresentation` (`judge <id>`) — fashion event judgement via
  `JudgePresentationAction` (now returns `endorsement` in `result.data`).

**Privacy rules (updated):**
- **WHISPER** poses: endorsable only by the direct recipient
  (`InteractionReceiver` row for endorser's account). Previously blanket-blocked.
- **VERY_PRIVATE** poses: endorsable by scene participants (SceneParticipation check).
  Previously blanket-blocked.

**New service:**
- `get_endorseable_poses_in_scene(endorser_sheet, endorsee_sheet, scene) → list[tuple[int, Interaction]]` —
  returns (stable-1-based-position, Interaction) pairs visible to the endorser.
  Batches whisper-receiver check to avoid per-row queries.

**Related changes:**
- `CharacterSheet.current_residence` FK to RoomProfile (narrative declaration; mechanical
  trickle fires only when the room has a positive cascade-row LocationValueModifier
  with key_type=RESONANCE matching a claimed resonance)
- `Interaction.pose_kind` CharField - STANDARD / ENTRY / DEPARTURE
- `GainSource` TextChoice - POSE_ENDORSEMENT / SCENE_ENTRY / ROOM_RESIDENCE / OUTFIT_ITEM / STAFF_GRANT (and more since; `ANIMA_RITUAL` is the anima ritual's two grants, #5280: the Primal part on the roll, the outward part on the partner's endorsement or, for an NPC partner, on the roll; `TRICKLE_HARVEST` is what the ritual turned the waiting trickles into, #5308; `ROOM_RESIDENCE` and `OUTFIT_TRICKLE` are legacy, no longer written)

**Residence declaration + room aura tagging, live end-to-end (#2036):** the daily
residence-trickle gate above was mechanically inert until #2036 wired every write path —
declaring a residence, tagging a room's aura, and reaching both without a manual step at CG.

- **Declare→tag→tick loop:** a player declares a residence via `SetPrimaryHomeAction`
  (`world.locations.services.set_primary_home` — telnet `room/home` / `home/set`, web "Set as
  Home"), which writes `CharacterSheet.current_residence` (via `set_residence` in this file)
  alongside Evennia `home`, and accepts org-derived owner/tenant standing (not only a direct
  `LocationTenancy` row) by minting a personal tenancy first — so a resident of a shared
  family/org/Academy-granted room can still declare their own home. A tenant or owner then tags
  the room's aura via `tag_room_resonance`/`untag_room_resonance` (telnet `room/aura <resonance>`
  / `room/aura clear <resonance>`, web `RoomAuraPicker`; gated by the owner-or-tenant
  `IsRoomTenantPrerequisite`, tagging additionally requires the caller has claimed that
  resonance). `residence_trickle_tick()` then writes a waiting trickle (`TrickleAccrual`, harvested by
  an anima ritual since #5308) daily for the intersection of
  (aura-tagged resonances on `current_residence`) ∩ (the sheet's claimed resonances) —
  `get_residence_resonances()` above. `end_tenancy()` clears `current_residence` when the ended
  tenancy was the declared residence — a character shouldn't keep trickling from a room they no
  longer have standing in.
- **Zero-manual-step CG on-ramp:** `StartingArea.grants_residence_tenancy` (BooleanField, default
  True) — an authored per-area toggle — drives `_grant_cg_residence_tenancy()`
  (`world/character_creation/services.py`, called from `finalize_character`): grants a
  `LocationTenancy` at the starting room for areas that author it, which auto-defaults both
  Evennia `home` and `current_residence` via `maybe_default_residence()`. A new character can
  reach the trickle gate with zero manual player action (the "Academy auto-residence" story).
- **Intentional emergent synergy — sanctum Homecoming satisfies the same gate:** the Ritual of
  Homecoming (`perform_homecoming_ritual` → `apply_homecoming_gain`, `services/sanctum_rituals.py`
  / `services/sanctum_lvm.py`) grows a Sanctum's consecrated resonance by writing/incrementing a
  `LocationValueModifier(key_type=RESONANCE, resonance=sanctum.resonance_type,
  room_profile=sanctum's room)` row — the exact same row shape `tag_room_resonance` writes, just
  under a different `source` tag. `get_residence_resonances()` doesn't filter on `source`, so a
  character whose `current_residence` is a Sanctum room, with a claimed resonance matching the
  Sanctum's consecrated type, accrues a trickle daily for free (harvested by an anima ritual, #5308) as a side effect of ordinary Homecoming
  ritual growth — no extra wiring needed, and no code should special-case it.

### Affinity skills and bonus checks (#5308, ADR-5308)

**Docs:** `docs/systems/magic.md` "Affinity skills and the bonus resonance check";
`docs/architecture/resonance-gain.md` §13.

- **One skill per affinity, named in no code.** `Affinity.skill` (one-to-one to a Magic skill) is the only way
  code reaches Villainy, Heroism or Reflection (ADR-4450). The Primal skill Reflection is not the Reflection
  pose or creation step. `Affinity.clean`, `MAGIC_PICKER_SKILL_CHOICES` and `RitualCheckConfig.clean` keep an
  affinity's skill off every other magical roll, so one roll never adds a skill twice.
- **Every earned gain rolls once per affinity.** `grant_resonance` rolls `roll_gain_bonus`
  (`services/resonance_checks.py`) for a source in `GAIN_BONUS_ROLLED_SOURCES`; a source in
  `GAIN_BONUS_CALLER_ROLLED_SOURCES` (`KINDLED_DEED`, `ANIMA_RITUAL`, `TRICKLE_HARVEST`) must be given a
  `gain_bonus=` its caller rolled once per affinity; a source in `GAIN_BONUS_EXEMPT_SOURCES` refuses one. A
  new `GainSource` goes in exactly one set (`test_deed_classification.py`). Pass `act_stat=act_stat(check_type)`
  when the act rolled; otherwise the stat comes from `ResonanceGainSourceStat`. Never roll a second time to
  grow something an earlier roll already grew: a kindled claim, a stored ritual amount and a harvest take the
  result already rolled.
- **Spending rolls `roll_spend_worth`.** A pull scales its resolved effects by the worth of each paying
  affinity (`spend_resonance_for_pull(worth_by_affinity=)` takes a worth already rolled, so one cast never
  rolls an affinity twice); `kindled_cast_power_term` scales by `PowerTermContext.resonance_worth_percent`.
  Previews never roll. Set `PullActionContext.check_type` where the action rolls a check. A combat cast with a
  pull rolls twice for one affinity (declaration and resolution), a recorded deviation.
- **Trickles wait.** The residence and worn-piece ticks write `TrickleAccrual`, never a grant; a ritual's
  `harvest_trickles` is the only writer of `TRICKLE_HARVEST` and of `harvested_at`. Do not add a counter:
  `waiting_trickles(sheet)` sums the rows. Any reader of "what a worn piece fed her" reads accrual rows plus
  legacy `OUTFIT_TRICKLE` grants.
- **A pose can reach.** `pending_reach_from` before the pose posts, `record_pending_reach` after
  (`services/reach.py`); an unheld resonance is a valid reach, and an unheld Celestial or Abyssal
  resonance is a valid kindled deed only when she chose the deed (`kindled_resonances(include_named_unheld=True)`,
  set only by `award_kindled_deeds`; the panel and casts never set it). "Chose" means a row on
  `CHOSEN_DEED_SITUATIONS`, today a mission option's theme. Every other row feeds holders only, including a
  state she caused in her target, and so does every row on a Primal resonance. The owner ruled on 2026-11-27
  that gaining a resonance needs intent, and the game cannot read intent from a state. Do not add a situation
  to `CHOSEN_DEED_SITUATIONS` unless the act is itself a declared choice of the deed.
- **Authoring left to staff:** the three skills and the affinity link, `ResonanceCheckAward` rows,
  `bonus_check_type` and its difficulty, per-source stats, the Abyssal floor and any skill accents. With no
  `bonus_check_type` nothing changes.

### Soul Tether (Resonance Pivot Spec B; Sineating and the Mire, #5177)

**Spec:** `docs/architecture/soul-tether.md`. **Decision:** ADR-5177.

Bond mechanic between two characters (Sinner + Sineater) that mediates Corruption. The Sinner's
`RELATIONSHIP_CAPSTONE` Thread carries **the Hollow** (a buffer that absorbs incoming corruption); what
it cannot absorb accrues to the Sinner, and nothing passes to the Sineater. Corruption a character
already carries comes down only through a Sineater (apart from daily decay): **Sineating** is a ritual
with a roll that moves it onto the Sineater, who carries it as **the Mire** and settles it later.

- **The Sineater's half.** Forming a tether (`accept_soul_tether`) also weaves a RELATIONSHIP_CAPSTONE
  thread for the Sineater, on a fresh ritual capstone of the Sineater's OWN side, never the Sinner's and
  never one reused from an earlier formation (`weave_tether_bond_thread`, no unlock gate), at `sineater_resonance` or `default_sineater_resonance` (their strongest main-affinity
  resonance); a sheet with no aura gets one (`ensure_aura`). A tether from before #5177 gets it on the
  first Sineating (`ensure_sineater_thread`). That thread's resonance is what the Sineater earns, and its
  presence turns on their resistance.
- **Presence is by character, play is by account.** `shared_active_scene(first, second)` (both characters in one room that has
  a live scene) replaces pairing player accounts, so a GM-puppeted NPC can be a Sineater. But no tether forms,
  and no plea or ritual runs, between two characters one account plays (`played_by_one_account`,
  `world/roster/services/npc_lending.py`, the loan-aware current player of each sheet; a sheet nobody plays
  shares none): `SoulTetherFormationError` / `SineatingValidationError`. A plea needs the asker to hold the
  tether's SINNER side, so reversing the pair is refused. Sineating, the
  rescue and the stage-advance offer use it. `sineater_has_fallen` (aura `dominant_affinity` Abyssal; an even split is Primal) makes
  Sineating and the rescue refuse with `SineaterFallenError`.
- **Sineating** (`services/sineating.py`). `request_sineating` is the Sinner's plea (a
  `SineatingPendingOffer`, one per pair, clamped to the per-plea cap); `perform_sineating` is the Sineater's
  ritual: refusals first (no plea, stale scene, fallen, already performed this scene, not set up, Mire at
  its stage cap), then in one transaction `ensure_sineater_thread`, roll `sineating_check_type` (with the
  activity terms of `MagicActivity.SINEATING`), `take_on_corruption` (`units x corruption_per_unit`, never
  more than the Sinner's own corruption (what they carry less what they hold as a Sineater for someone else, `mire.own_corruption`) or than fits under `CorruptionConfig.sineater_max_stage`, whatever the roll),
  refill the Hollow, `lifetime_helped += units`, and each party earns
  `floor(units x resonance_per_unit x earned_share)` (the rolled tier's `SineatingOutcomeAward`), as `GainSource.SINEATING`
  (#5231). The corruption moves in the resonance on the Sinner's thread in which she has the most of
  her own to shed (`_plea_resonance`; a tie goes to the row with more imbued, then the lower resonance
  id), the plea stores that resonance, and the Hollow refills on the thread that has a row for it. The
  Sineater earns it all in the resonance of their own thread; the Sinner's earning is split across the
  thread's rows by the amounts imbued, the leading row taking the remainder, a part of 0 granting
  nothing, and a thread with nothing imbued paying its leading resonance (`_earning_parts`; each part is
  its own grant, and the result carries `sinner_earned_parts`). A Sinner with nothing of her own to shed
  is not refused: the ritual performs and says "you carried no corruption to shed". No anima and no fatigue. `decline_sineating`,
  `sineating_lines` (both parties' result lines), `sineating_is_ready` (check type set and an award per
  outcome tier; the Required content probe reads the same), `sineating_options_for(sheet)`.
- **A pose carries it**, as it carries a reflection: pose fields `sineating_role` (`entreat` / `perform`,
  `SineatingPoseRole`), `sineating_partner_id` (the other sheet id), `sineating_units`;
  `pending_sineating_from` checks before the pose posts, `record_pending_sineating` acts after it; a pose
  carries a reflection or a Sineating, not both. Actions (`actions/definitions/sineating.py`):
  `entreat_sineating`, `perform_sineating`, `decline_sineating`; `run_pose_sineating` is what the pose
  action calls. Telnet: `pose/entreat <sineater>=<units> <text>`, `pose/sineat <sinner>=<units> <text>`,
  `sineater decline <sinner>`, `sineater pleas` (the pleas waiting and what the Sineater carries),
  `sineater brace <sinner> [sins=<n>]` (renamed from `sineater mire`; the stage-advance pledge),
  `sineater rescue`. Web: a Sineating row in the pose composer.
- **The Mire** (`services/mire.py`; `MireHolding`). The Mire is corruption on the Sineater's own
  `CharacterResonance.corruption_current`; `MireHolding.amount` records how much came from which Sinner,
  and **the holdings in a resonance never exceed that corruption**. `take_on_corruption` (the Sinner sheds
  through `reduce_corruption`, source `SINEATING`, no cleansing payout; the Sineater takes on through
  `accrue_corruption`, source `SINEATING_CARRIED`, after resistance) and `release_mire` (lowers the
  corruption and one holding through `reduce_corruption`, source `MIRE_SETTLED`) are the only writers of
  `amount`; every other reduction (`reduce_corruption` with `shrink_holdings=True`: decay, rescue, staff)
  takes unheld corruption first and then shrinks holdings in proportion. `corruption_that_can_move` and
  `corruption_ceiling` work out what fits under the stage cap, working backward through resistance.
  `add_to_largest_holding` carries what a Sineater adds by giving in to a Compulsion. `mire_carried_by`
  and `mire_for_sinner` read what is carried, with each resonance's stage and display name; the web shows
  it to the Sineater only (`SoulTetherDetailSerializer.mire`).
- **Resistance** (`_apply_sineater_corruption_resistance`, `services/corruption.py`): a Sineater with any
  live thread on a tether resists `1 - max(0.1, 1 - lifetime_helped / resistance_full_at)` of what they
  take on in a resonance, sized by their `lifetime_helped` in the accruing resonance, capped at 90%; the
  thread's own resonance need not match. It does not apply to `INDULGED` corruption.
- **Settling the Mire** (`services/mire_settling.py`, called by the settling rite): see "Drift correction
  and the rite of settling". Absolve and Condemn clear and reward, Succumb pays the Sinner from the
  jackpot, and `apply_fall` pays every Sinner when the Sineater's aura turns predominantly Abyssal.

**Fields:**
- `Thread.hollow_current` - the Hollow's available capacity. Drained by the redirect handler on Sinner
  casts (which skips `SINEATING_CARRIED` and `INDULGED` and lowers `payload.amount` to the unabsorbed
  remainder); refilled by `perform_sineating`.
- `CharacterResonance.lifetime_helped` - monotonic; increments by the units of every performed Sineating
  and by `severity_reduced` on every rescue; sizes the Sineater's resistance.

**Audit models (`models/soul_tether.py`):**
- `Sineating` - one row per performed or declined Sineating: `sinner_sheet`, `sineater_sheet`,
  `relationship`, `scene` (nullable), `resonance`, `units_offered`, `units_accepted` (0 = declined),
  `corruption_moved`, `corruption_taken`, `outcome` (nullable), `sinner_resonance_earned`,
  `sineater_resonance_earned`. The once-per-pair-per-scene rule reads these rows.
- `SineatingPendingOffer` - the Sinner's plea, unique per pair.
- `SoulTetherRescue` - one row per rescue: stages at start and end, `severity_reduced`,
  `sineater_strain_taken`, `check_outcome`.
- `PendingStageAdvanceOffer` - the stage-advance bonus offer.

**Constants and exceptions:**
- `ThreadPullEffect.EffectKind.CORRUPTION_RESISTANCE` names the benefit; its value is computed inline in
  `accrue_corruption`, not through `resolve_pull_effects`.
- `SoulTetherRole` (SINNER / SINEATER), `SineatingPoseRole`, `MagicActivity.SINEATING`, `GainSource`
  `SINEATING`, `MIRE_PURIFIED`, `SUCCUMBED`, `SUCCUMB_BONUS`, `SINEATER_FALL`, `CorruptionSource`
  `SINEATING_CARRIED` / `INDULGED`, `CorruptionRecoverySource` `SINEATING` / `MIRE_SETTLED`.
- `exceptions.py`: `SoulTetherError` (base), `AffinityGateError`, `NoSoulTetherUnlockError`,
  `SoulTetherFormationError`, `SineatingValidationError`, `RescueValidationError`, `SineaterFallenError`
  (both a Sineating and a rescue refusal), `StageAdvanceBonusError`.
- `SOUL_TETHER_FORMED` / `SOUL_TETHER_DISSOLVED` event names in `flows/constants.py`.
- Stats (`_increment_stat_safe`): `sineating.requests_made`, `sineating.units_accepted`,
  `sineating.units_declined`, `sineater.succumbed`, `sineater.succumbed_amount`, `sineater.broken`,
  `rescue.*`, `tether.formed`; they key on the sheet, so an NPC counts.

**CharacterSheet integration:**
- `CharacterSheet.get_tether_strain_stage() -> int` - the Sineater's Tether Strain stage (one shared
  condition per Sineater, not per resonance); used for `sineater_current_strain_stage` in the plea's
  `SineatingOffer`.

**The rescue is unchanged** except for three things (#5177): presence is by character (the scene is found
from where the two stand; a scene passed in must be that one), a fallen Sineater is refused, and the
Sineater's thread level reaches the rescue budget (`_get_sineater_thread_level` reads a live thread of the
Sineater's on this bond, whatever resonance it channels).

**Authored content (factories, not migrations):**
- `TetherStrainTemplate` — ConditionTemplate applied to the Sineater at dramatic moments
  (opt-in stage-advance bonus, rescue rituals). Only accrued via explicit opt-in; Sineating
  never adds Strain.
- `SoulTetherActiveTemplate` — ConditionTemplate installed on the Sinner at formation.
  Carries two reactive trigger M2Ms (soul_tether_redirect, soul_tether_stage_advance_prompt).
- `accept_soul_tether` Ritual — SERVICE-dispatched formation capstone.
- `soul_tether_rescue` Ritual — SERVICE-dispatched stage-3+ rescue ritual.
- `soul_tether_redirect` TriggerDefinition — subscribes to `CORRUPTION_ACCRUING`.
- `soul_tether_stage_advance_prompt` TriggerDefinition — subscribes to
  `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`.

All wired via `wire_soul_tether_content()` in `factories.py`, which `seed_magic_dev()` calls
(#2027) so this content exists in a real deploy, not only under test setup. `seed_magic_config()`
seeds one `SineatingOutcomeAward` per canonical `CheckOutcome` (a share of 1.50 for a critical
success down to 0.00 for a critical failure); the Sineating check type and the Compulsion condition
are staff-authored, and the Required content page lists them while unset (`sineating-config`,
`compulsion-condition*`).
`seed_relationship_track_thread_unlock()` (`world/seeds/game_content/magic.py`) resolves the
paired RELATIONSHIP_TRACK `ThreadWeavingUnlock` + its "Sworn" `RelationshipType` (#3957) that
`accept_soul_tether`'s `_validate_unlock` gates on — `ThreadWeavingUnlock.unlock_type` is a
required FK, so both rows are needed to make Soul Tether formation reachable. The gate itself
is coarse: any RELATIONSHIP_TRACK-kind unlock the Sinner holds satisfies it, since
`ThreadWeavingUnlock` has no CAPSTONE-kind row to match against (the Sinner's specific
`unlock_type` need not match anything on the tie). Both rows are
content-repo-owned (#2698/#2973): resolved via `authored_or_sample`, never lazy-created
against a real deploy; `accept_soul_tether` raises `NoSoulTetherUnlockError` cleanly when
either is absent.

**Relationship side changes (`world/relationships/models.py`):**
- `RelationshipCapstone.is_ritual_capstone` — BooleanField (default False); marks capstones
  that gate a Ritual.
- `RelationshipCapstone.ritual` — nullable FK to `magic.Ritual`.

**Services (`services/soul_tether.py`):**
- `accept_soul_tether(initiator_sheet, partner_sheet, sinner_role, resonance, ritual_components,
  sineater_resonance=None)` - Formation ritual: `ensure_aura` for both, affinity gate (Sineater must be
  non-Abyssal-primary; Sinner non-Celestial-primary), unlock gate (Sinner must have a RELATIONSHIP_TRACK
  ThreadWeavingUnlock), idempotency check, the Sinner's Thread (RELATIONSHIP_CAPSTONE), the Sineater's
  thread, and the `SoulTetherActive` ConditionInstance and trigger rows on the Sinner. Returns the
  Sinner's-side capstone.
- `dissolve_soul_tether(relationship, initiator_sheet)` - Tears the bond: retires tether Threads, removes
  the ConditionInstance and triggers when it was the Sinner's last tether, emits `SOUL_TETHER_DISSOLVED`.
- `ensure_sineater_thread`, `default_sineater_resonance`, `sineater_thread_resonance`,
  `sinner_thread_resonance`, `sineater_has_fallen`, `shared_active_scene`, `get_soul_tether_config()`.
- `perform_soul_tether_rescue(sineater_sheet, sinner_sheet, resonance, components, scene=None)` -
  Stage-3+ rescue: gates (including the fallen refusal and the shared active scene), a check roll, Strain
  cost, resonance cost, `reduce_corruption`, `SoulTetherRescue` audit row, stats. Returns `RescueOutcome`.
- `soul_tether_redirect_handler(*, payload)` - subscriber on `CORRUPTION_ACCRUING`: drains `hollow_current`
  (strongest thread first) and lowers `payload.amount`.
- `soul_tether_stage_advance_prompt(*, payload)` - subscriber on
  `CONDITION_STAGE_ADVANCE_CHECK_ABOUT_TO_FIRE`: fires `PROMPT_PLAYER` to a Sineater in the same room.
- `resolve_stage_advance_prompt(...)` / `resolve_stage_advance_prompt_from_db(...)` - the Sineater's
  response to it (telnet `sineater brace`, REST `stage-advance/respond/`).

**`CORRUPTION_RESISTANCE` resolution** (`_apply_sineater_corruption_resistance` in
`services/corruption.py`, inside `accrue_corruption`): see "Resistance" above. It is not a
`ThreadPullEffect` evaluation.

**API endpoints (`views.py`, `views_sineating.py`, `urls.py`; all under `/api/magic/`):**
- `POST soul-tether/accept/` - `SoulTetherAcceptView`
- `POST soul-tether/dissolve/` - `SoulTetherDissolveView`
- `POST soul-tether/rescue/` - `SoulTetherRescueView`
- `GET soul-tether/<relationship_id>/` - `SoulTetherDetailView`: Hollow, thread levels, stats, and the Mire
  for the Sineater only. Only the two parties of the bond (an NPC a GM runs counts as played) and staff
  read it; anyone else gets a 404.
- `GET sineating-options/?character_sheet=<id>` - `SineatingOptionViewSet`: the pleas the character can
  make or answer with a pose; only a character the requester plays.
- `POST soul-tether/sineating/decline/` - `SineatingDeclineView` (runs `DeclineSineatingAction`)
- `GET soul-tether/sineating/pending/` (and `<id>/`) - `SineatingPendingOfferViewSet`
- `GET soul-tether/stage-advance/pending/` (and `<id>/`), `POST soul-tether/stage-advance/respond/`
- The plea and the ritual are not endpoints: they ride the pose endpoint's `sineating_*` fields. The old
  `sineating/request/` and `sineating/respond/` routes were removed in #5177.

**Types (`types/soul_tether.py`):**
- `SineatingOffer`, `SineatingResult`, `SineatingLines`, `SineatingOption`, `PendingSineating` - the
  plea, the ritual's result (units, corruption moved and taken, outcome, both earnings), what each party
  reads, a picker row, and a checked pose attachment.
- `MireTransfer`, `MireCarried`, `MireForSinner` - what `take_on_corruption` moved and what a Sineater
  carries.
- `StageAdvanceBonusOffer` / `StageAdvanceBonusResult` - the stage-advance prompt and its outcome.
- `RescueOutcome` - severity_reduced, stage_before/after, strain_taken.

### Covenant Lifecycle Content (#2114)

The full covenant lifecycle — formation, induction, banner-call rise, mentor bonding,
the mid-battle oath rite, and generic-org induction — is built session machinery
(`world.covenants.services` / `world.societies.membership_services`), but every
`Ritual` row a player would `ritual draft "<name>"` to trigger it previously existed
only in test factories. `wire_covenant_lifecycle_rituals()` in `factories.py`, which
`seed_magic_dev()` calls (#2114) right after `wire_soul_tether_content()`, seeds:

- **"Covenant Formation"** — `create_covenant_via_session` (DURANCE + BATTLE only;
  COURT formation is intentionally out of scope, per ADR-0057)
- **"Covenant Induction"** — `induct_member_via_session`
- **"Call the Banners"** — `rise_battle_covenant_via_session`
- **"Mentor's Vow"** — `establish_mentor_bond_via_session`
- **"Renew the Oath"** — `perform_covenant_rite`, seeded via the existing
  `wire_covenant_rite_content()` (`world.covenants.factories`) rather than the bare
  `RenewTheOathRitualFactory()` — `perform_covenant_rite` reads
  `session.ritual.covenant_rite`, a required `CovenantRite` sidecar the bare Ritual
  factory does not create, so the bare factory alone would seed a Ritual that crashes
  on fire. `wire_covenant_rite_content()` creates the Ritual + `CovenantRite` sidecar +
  role/level-band stat packages together.
- **"Organization Induction"** — `induct_organization_member_via_session`
  (`world.societies.membership_services`)

Also resets the `MentorBondConfig` singleton (pk=1) to its authored defaults via
`seed_mentor_bond_defaults()` — unlike the Ritual rows above (which preserve staff
edits via `django_get_or_create`), this is a pre-launch tuning-knob reset by design
(`update_or_create`), same treatment as other authored-defaults singletons.

Like Soul Tether, this content previously existed only under test setup — without it,
no player could ever found/join/grow a covenant, revive a dormant war covenant, form a
mentor bond, fire the mid-battle oath rite, or join an ordinary organization through
play; `covenant`/`org` (telnet)/REST could only manage state staff planted by hand.

### Dramatic Moment Tagging (#545 / #1139)

`models/dramatic_moment.py` — Staff-initiated scene moments that grant both resonance
and a renown award:

- `DramaticMomentType` (inherits `RenownAwardConfig`) — staff-authored lookup. Carries
  `label`, `description`, `resonance` (FK — the resonance granted), `resonance_amount`
  (flat units, default 15), and `per_scene_cap` (max awards per character per scene,
  default 1). Inherits `magnitude` / `risk` / `reach` / `archetypes` from
  `RenownAwardConfig` for the simultaneous renown leg.
- `DramaticMomentTag` — per-event record. FKs: `moment_type`, `character_sheet`,
  `scene` (nullable, `SET_NULL` — resilient to scene cleanup), `tagged_by` (AccountDB,
  `PROTECT` for provenance), `interaction` (optional pose anchor; `db_constraint=False`
  because `scenes_interaction` is a partitioned table with a composite PK),
  `interaction_timestamp` (denormalized from `interaction.timestamp` so the composite
  FK is navigable). `tagged_at` is auto-timestamped.

**Service (`services/gain.py`):**

`create_dramatic_moment_tag(*, character_sheet, moment_type, tagged_by, scene, interaction=None) -> DramaticMomentTag`

Validates that the character has claimed `moment_type.resonance` and that the
`per_scene_cap` for this `(moment_type, scene, sheet)` combination has not been
reached. On success, atomically:
1. Creates a `DramaticMomentTag` row (with `interaction_timestamp` denormalized when a
   pose is provided).
2. Calls `grant_resonance(..., source=GainSource.DRAMATIC_MOMENT, dramatic_moment=tag)`.
3. Calls `fire_renown_award` for the character's primary persona (skipped silently if no
   primary persona).

Raises `EndorsementValidationError` (unclaimed resonance) or `DramaticMomentCapExceeded`
(per-scene cap hit) — both carry `user_message` for safe 400 responses.

**REST API (`views.py`, `urls.py`, `serializers.py`):**

- `GET /api/magic/dramatic-moment-types/` — `DramaticMomentTypeViewSet` (read-only, no
  pagination; authenticated). Supplies the tag-picker dropdown in the GM control panel.
- `POST /api/magic/dramatic-moment-tags/` — create a tag; gated by
  `IsSceneGMOrOwnerOrStaff` (scene GMs, scene owners, and staff may tag — not
  restricted to staff-only). Body fields: `character_sheet`, `moment_type`,
  optional `scene`, optional `interaction`. Service errors map to HTTP 400
  with `user_message`. No `DELETE` endpoint — tags are immutable provenance records.
- `GET /api/magic/dramatic-moment-tags/` — list tags; filterable by `character_sheet`
  and `scene`; paginated.

**Telnet (#2227):**

- `moment tag <character>=<type>` — direct GM tagging from telnet; thin command
  calling `create_dramatic_moment_tag` directly (the same service the web serializer
  calls). Target resolved by name (`caller.search(global_search=True)`), type by
  `label__iexact`. GM-gated via `_account_can_gm_scene` on the caller's active scene.
- `moment tag list` — lists available `DramaticMomentType` rows (label + resonance +
  amount), same GM gate.

**Django admin (`admin.py`):**

- `DramaticMomentTypeAdmin` — full CRUD for the authored catalog. Fields:
  `label`, `resonance`, `resonance_amount`, `per_scene_cap`, `magnitude`, `risk`.
  Staff author types here; no special approval workflow.
- `DramaticMomentTagAdmin` — read-only (no add/change permissions). All fields are
  readonly for provenance audit. Staff can inspect issued tags but cannot fabricate them.

**Scene/interaction context fields (scenes serializers):**

- `SceneDetailSerializer.viewer_can_gm` (SerializerMethodField, bool) — `True` when
  the requesting user is the scene's GM, owner, or a staff member. The frontend uses
  this flag to show or hide the GM tagging control per pose.
- `InteractionSerializer.dramatic_moment_tags` (SerializerMethodField, list) — tags
  anchored to this interaction (Prefetch `to_attr=cached_dramatic_moment_tags`).
  Drives the badge displayed on the pose in the scene log.
- `SceneParticipationSerializer.dramatic_moment_count` (SerializerMethodField, int) —
  count of tags for this participant in the scene, derived from a `dramatic_moment_counts`
  context dict built at scene-serialization time. Powers per-participant tallies.

**React frontend (`frontend/src/scenes/components/`):**

- Per-pose GM "Tag dramatic moment" control (visible only when `viewer_can_gm`).
- `DramaticMomentTagDialog.tsx` — modal dialog for type selection + confirmation.
- Badge displayed on tagged interactions in the scene log.

#### GM Prompt Queue: narration of mechanical events (#4101; was Dramatic Moment Suggestion, #2183)

Big mechanical moments used to fire with generic authored text and the GM running the
scene got no signal. `DramaticMomentSuggestion` (the #2183 technique-entrance confirm
inbox) is renamed `GMPrompt`, moved to `world/gm/models.py`, and generalized to seven
kinds (`GMPromptKind` in `world/gm/constants.py`): `dramatic_moment` (the original
confirm kind, see below) plus six narration kinds
`audere_surge`/`audere_ultimate`/`crossing`/`miracle`/`death`/`stake_outcome`, each
fired by `world.gm.prompt_services.route_narratable_event`. Full detail (model,
services, release-on-close rule, telnet/web surfaces): `docs/systems/scenes.md`'s "GM
narration of mechanical events" section and ADR-4101. The six event sources live
outside this app (`world/worship/services.py` MIRACLE, `world/stories/services/
stake_resolution.py` STAKE_OUTCOME, `world/vitals/services.py` DEATH) and inside it
(`audere.py` AUDERE_SURGE, `audere_majora.py` CROSSING, `services/ultimates.py`
AUDERE_ULTIMATE); each resolves its own authored/prepared text, then calls
`route_narratable_event`; with no GM opted in it delivers that same text unprompted,
byte-identical to pre-#4101 behavior.

**Prepared text (`models/prepared_text.py`, `services/prepared_text.py`):**
`CharacterCrossingText` / `CharacterSurgeText`: one character's own authored line for
their next Crossing or surge, written by staff or that character's table GM
(play-adjacent, never catalog content, never exported). `resolve_crossing_text`/
`resolve_surge_text` layer field by field: the character's own prepared text, then
(Crossing only) the patron variant, then the tier default. A Crossing's prepared text
is consumed on use (`consume_prepared_crossing_text`); a surge's is reusable.

**Dramatic Moment Suggestion: the technique-entrance recognition bridge (#2183)**

A qualifying **Technique Entrance** (see "Technique Entrance" below) does not auto-tag a
Dramatic Moment; it surfaces a PENDING `GMPrompt` of kind `dramatic_moment` a GM later
confirms or dismisses. Recognition stays a human-adjudicated nudge, never a mechanical
auto-grant (ADR-0113). This kind has no `addressed_to` (it keeps the original scene
GM/owner/staff gate), no narration and no `route_narratable_event` call; since #4101 a new
suggestion is pushed live (`notify_gm_prompt`, on commit) to each scene GM who has not muted
the group, with the same `gm_prompt` frame a narration prompt gets.

- `DramaticMomentType.suggest_on_technique_entrance` (bool) / `.suggestion_min_success_level`
  (`PositiveSmallIntegerField`) — opts a moment type into the bridge and sets the cast
  success-level floor (`>=`) that must be cleared.
- `GMPrompt` (`world/gm/models.py`): FKs `moment_type` (PROTECT),
  `character_sheet` (CASCADE), `scene` (nullable/SET_NULL), `interaction` (nullable/SET_NULL,
  `db_constraint=False`, the entrance pose), `interaction_timestamp` (denormalized).
  Fields: `success_level`, `status` (`GMPromptStatus`: PENDING/CONFIRMED/DISMISSED/NARRATED;
  the `dramatic_moment` kind never reaches NARRATED in practice), `resolved_by` (AccountDB,
  PROTECT), `confirmed_tag` (OneToOne → `DramaticMomentTag`, the tag minted on confirmation).
  Unique per `(moment_type, character_sheet, scene)` while PENDING.
- **Services (`services/gain.py`):** `maybe_suggest_dramatic_moments(*, character_sheet,
  scene, success_level, interaction=None) -> list[GMPrompt]`: scans
  flagged `DramaticMomentType` rows meeting the success-level floor, skips unclaimed
  resonance / an already-spent `per_scene_cap`, `get_or_create`s idempotently.
  `resolve_dramatic_moment_suggestion(suggestion, *, resolver, confirm)` — confirm mints a
  real `DramaticMomentTag` via `create_dramatic_moment_tag`; dismiss closes it out with no
  reward. Raises `DramaticMomentSuggestionAlreadyResolved` on a non-PENDING suggestion.
- **Actions (`actions/definitions/dramatic_moments.py`):**
  `ConfirmDramaticMomentSuggestionAction` (key `"confirm_dramatic_moment_suggestion"`) /
  `DismissDramaticMomentSuggestionAction` (key `"dismiss_dramatic_moment_suggestion"`) —
  **account-authorized** (mirrors `actions/definitions/events.py`'s host-lifecycle
  actions: `actor=None`, `account=<resolver>`), gated on `_account_can_gm_scene` (staff,
  or `scene.is_gm(account)`, or `scene.is_owner(account)`). The same module's
  `DismissGMPromptAction` (key `"dismiss_gm_prompt"`) closes a narration-kind prompt
  instead, addressed-GM-or-staff gated, see the scenes doc section above.
- **Web:** the dedicated `DramaticMomentSuggestionViewSet` is retired; confirm/dismiss
  now ride the one GM prompt queue, `GMPromptViewSet` (`world/gm/views.py`): `GET
  /api/gm/prompts/?scene=<id>` lists every open prompt the viewer may act on (dramatic
  moments plus narration kinds addressed to them); `POST .../{id}/confirm/` (dramatic moment
  only) / `POST .../{id}/dismiss/` / `POST .../{id}/narrate/` dispatch by `GMPrompt.kind`.
- **Telnet:** `CmdMoment` (`commands/dramatic_moments.py`, key `"moment"`) — `moment
  suggestions|confirm <id>|dismiss <id>`, account-authorized like the web surface. The
  narration kinds have their own telnet surface: `gm prompts` / `gm prompt
  send|dismiss|done <id>` plus `emit/prompt`/`pemit/prompt`, see `src/commands/CLAUDE.md`.
- **Frontend:** the per-pose `DramaticMomentSuggestionChip` embed (`frontend/src/scenes/
  components/`) is retired with the viewset; the GM prompt queue UI
  (`GMPromptQueue`/`NarrationComposer`, `frontend/src/scenes/components/`) covers both the
  `dramatic_moment` kind and the six narration kinds.
- **Seed content:** `ensure_dramatic_entrance_content()` (`factories.py`) seeds the "Grand
  Entrance" `DramaticMomentType` with `suggest_on_technique_entrance=True` /
  `suggestion_min_success_level=3` and **no resonance**. It used to mint its own "Fervor"
  Resonance and pin the type to it, which made the game's one authored moment type
  un-awardable to everybody: the tag service refused any character who had not claimed
  Fervor, and an invented resonance is unclaimable (#2967). The resonance is resolved at
  tag time instead — see `_resolve_moment_resonance` in `services/gain.py`.

### Entry-Flourish Declaration (#1140)

On a **successful Entrance social action**, a poll-able offer is created so the entrant
declares which of their claimed resonances they broadcast. The pick resolves through
`create_entry_flourish` (actor self-grant), scoped to the room's active scene and
idempotent per scene. Mirrors the Audere offer pattern but is a **self-grant** —
not a reaction window (`react_to_window` hard-blocks self-reaction, so the #904
framework was evaluated and rejected for this; peer scene-entry endorsement is
the complementary half of the entrance moment).

**Model (`entry_flourish.py`):**
- `PendingEntryFlourishOffer` — poll-able offer; one per character (UniqueConstraint on
  `character_sheet`); nullable `scene` FK. Re-exported in `world/magic/models/__init__.py`.

**Model (`models/endorsement.py`):**
- `EntryFlourishRecord` — immutable receipt written by `create_entry_flourish`. FK
  `character_sheet`, FK `resonance`, nullable FK `scene`, `granted_amount`. Partial
  UniqueConstraint `(character_sheet, scene) WHERE scene IS NOT NULL` — per-scene
  uniqueness; scene-null grid-RP flourishes are unconstrained.

**Config tuning knob:**
- `ResonanceGainConfig.entry_flourish_grant` (default 10) — amount granted per flourish.

**Services:**
- `maybe_create_entry_flourish_offer(character, scene)` (`entry_flourish.py`) — called on
  Entrance success; skips if already flourished this scene.
- `resolve_entry_flourish_offer(offer: PendingEntryFlourishOffer, *, resonance: Resonance) -> EntryFlourishResult`
  (`entry_flourish.py`) — locked grant then offer deletion; an unheld resonance is earned (#5308).
- `create_entry_flourish(sheet, resonance, *, scene, amount=None)` (`services/gain.py`) —
  creates `EntryFlourishRecord` (the resonance need not be held, #5308), writes
  `ResonanceGrant(source=ENTRY_FLOURISH, entry_flourish=record)`. Skips gracefully on
  duplicate `(sheet, scene)`.

**Action wiring (`actions/definitions/social.py`):**
- `EntranceAction` calls `maybe_create_entry_flourish_offer` on success; gated by
  `ActionTemplate.grants_entry_flourish`. When an offer is created, the actor receives
  a telnet prompt: `"Use |wflourish <resonance>|n to declare your entrance."`
- `ResolveFlourishOfferAction` (key `"resolve_entry_flourish"`) — telnet + web converge
  here; calls `resolve_entry_flourish_offer(offer, resonance=resonance)` and stores the
  result under `ActionResult.data["entry_flourish_result"]`.
- **Technique-driven entrance (#2183):** `EntranceAction.execute` branches on a
  `technique_id` kwarg to `_execute_technique_entrance` instead of the plain
  ActionTemplate check path — see "Technique Entrance" below. The bare-entrance
  ActionTemplate path (this section) is unchanged and byte-identical when no
  technique is attached.

**Telnet commands (`commands/social/entrance_flourish.py`):**
- `CmdEnter` — thin telnet wrapper that dispatches `EntranceAction`.
- `CmdFlourish` — thin telnet wrapper that resolves a pending offer via
  `ResolveFlourishOfferAction`.

**REST endpoints (`/api/magic/entry-flourish/`):**
- `GET /api/magic/entry-flourish/pending/` + `GET .../pending/<id>/` —
  `PendingEntryFlourishOfferViewSet` (account-scoped, read-only).
- `POST /api/magic/entry-flourish/respond/` — `EntryFlourishRespondView`; body
  `{offer_id, resonance_id}`; dispatches through `ResolveFlourishOfferAction` (same
  seam as the telnet `flourish` command); picker data reads the resonance catalog
  (`useResonanceCatalog`) and `CharacterResonanceViewSet` to list held resonances first (#5308).

**Exceptions (`exceptions.py`):**
- `EntryFlourishOfferError` (base), `EntryFlourishOfferNotFoundError` — both carry
  `user_message` for safe 400 responses.

**Frontend:**
- `EntryFlourishOfferGate` + `EntryFlourishOfferDialog`
  (`frontend/src/magic/components/`) — gate polls `usePendingEntryFlourishOffers`;
  dialog opens once per offer id, lets the player pick a resonance and calls
  `useRespondToEntryFlourish`.
- Mounted in `frontend/src/scenes/pages/SceneDetailPage.tsx` (`isActive` guard).
- Hooks in `frontend/src/magic/queries.ts`: `usePendingEntryFlourishOffers`,
  `useRespondToEntryFlourish`.

**GainSource:** `ENTRY_FLOURISH` in `world/magic/constants.py` (`GainSource` TextChoices).

### Technique Entrance (#2183, ADR-0113)

A "make an entrance" whose check IS a technique cast — one roll, not two (ADR-0113): the
technique's own success level substitutes for the entrance's social check entirely and
drives every downstream consequence (flourish, disposition, the Dramatic Moment Suggestion
above). See `docs/systems/magic.md`'s "Technique Entrance" section for the full deferral
matrix table; the summary:

- **Dispatch:** telnet `enter <technique>[=<target>]` (`CmdEnter`,
  `commands/social/entrance_flourish.py`) and the web `EntranceTechniqueAttachment`
  popover both reach `EntranceAction._execute_technique_entrance`
  (`actions/definitions/social.py`) via `action.run()`. The web REST caller
  (`SceneActionRequestViewSet._create_technique_entrance`,
  `world/scenes/action_views.py`, #2183 Task 8 fold-in) dispatches the identical seam —
  **not** the generic technique-as-`ActionEnhancement` consent path
  `SceneActionRequestViewSet.create()` otherwise uses (that path has no
  `ActionEnhancement` row for `"entrance"` and always 400ed before this fix).
- **Deferral matrix** (why a success level isn't always known immediately): resolved
  inline → full hooks now; hostile → seeds/feeds combat, flourish only, suggestion
  deferred to combat round resolution (`from_entrance` marker, see
  `docs/systems/INDEX.md`'s Combat section); PENDING consent/risk-gated →
  `SceneActionRequest.originated_as_entrance` defers all hooks to
  `resolve_accepted_cast`; soulfray gate unconfirmed → a `PendingCast` carrying an
  `"entrance"` marker re-dispatches through the `"entrance"` REGISTRY action (not
  `"cast_technique"`) on `accept soulfray` (`world/magic/offer_handlers.py`
  `SoulfrayPendingHandler`).
- **Shared hook helper:** `run_entrance_success_hooks(actor, scene, *, success_level,
  target_persona_id, technique, interaction=None)` (`actions/definitions/social.py`) —
  one signature, three call sites (declaration-time inline/hostile branches,
  accept-time deferred hooks, combat round-resolution hook), no drift.

### Offer handler registry (`commands/offer_registry.py`)

System-initiated prompts (intensity surges, path crossings) are dispatched through
a registry of `OfferHandler` objects keyed by keyword string. Handlers live in
`world/magic/offer_handlers.py` and register in `world/magic/apps.py`'s `ready()`. The telnet
`accept`/`decline` commands route non-numeric first-token args through the registry.
To add a new handler: implement the `OfferHandler` protocol and call
`register_offer_handler()` in `ready()`.

### Audere & Audere Majora (#873, #543)

`audere.py` — Audere, the in-the-moment intensity surge: `AudereThreshold` (global
config), `PendingAudereOffer` (poll-able offer, one per character),
`check_audere_eligibility` (intensity tier + Soulfray stage + engagement; high runtime
control steps the stage needed back along the Soulfray ladder, one stage per
`AudereThreshold.control_per_stage_earlier`, never below the first stage, via
`required_stage_order`; the offer keeps `fired_control` for the accept re-check, and the
offer surfaces tell the player via `stages_lowered_by_control` / `control_lowered_line`,
#4740),
`offer_audere`/`end_audere` lifecycle, `AbstractPendingOffer` (shared offer base).

**Found by designation (#4739):** Audere and Audere Majora are the templates
`AudereThreshold.audere_condition` / `audere_majora_condition` name, read through
`audere_condition_id()` / `audere_majora_condition_id()` (or the threshold's FK when a
template is applied or removed). Nothing finds them by name; unset means no offer is made,
nothing is applied, and the Required content dashboard lists it. The web client reads
`ParticipantSerializer.audere_state` (`audere` | `audere_majora` | null), never a condition
name. Test factories: `AudereThresholdFactory` picks up the `AUDERE_SEED_TEMPLATE_NAME` /
`AUDERE_MAJORA_SEED_TEMPLATE_NAME` templates when they exist, `wire_audere_power_multipliers`
designates them on an existing threshold, and `ensure_audere_designations()` makes a threshold
when a test has none. Berserk is `FuryConfig.berserk_condition` the same way
(`get_berserk_template()` / `berserk_condition_id()`).
**Surge broadcast (#3451):** `AudereThreshold.surge_manifestation_text` (blank
default) is EMITted to the active scene by `_broadcast_surge` when a surge is
accepted — the plain-Audere echo of the Majora manifestation, via the shared
`world.scenes.interaction_services.broadcast_scene_emit` seam (which
`_broadcast_manifestation` now also delegates to). `{name}` substitutes the
primary persona's name; blank text keeps the accept room-silent (staff authors
the line — a required-content row for the #3444 sentinel, never code prose).

**Audere alternate self + acting aura (#4731):** an alternate self with ultimates is a bond
source in the reveal (`UltimateSource.ALTERNATE_SELF`); choosing its card makes
`choose_ultimate` register `world.forms.services.assume_alternate_self_for_audere` with
`transaction.on_commit` (swaps out a different worn self, or refuses with a message when she
is not in control), which marks `ActiveAlternateSelf.assumed_at_audere`. `end_audere` calls
`revert_audere_alternate_self` and `cleanup_completed_encounter` calls
`revert_audere_alternate_selves` for every participant; only a marked AUTOMATIC self
reverts, a TALKED_DOWN one stays with its `emergence_condition`. `acting_aura(sheet)` (`services/acting_aura.py`) is the aura she
ACTS with (cast alignment, place of power on arrival and during a cast, defilement, covenant
attacker affinity); `working_affinities` puts a cast in the worn self's affinity. Fall, Soul
Tether and the sheet display keep the true `CharacterAura`. See `docs/systems/magic.md`.

**Unsettled and Resonance Conflict (#4732, #5123):** `services/drift.py` holds `drift_for(sheet)`
(whether the character is unsettled: on the TRUE aura, each affinity read (see below) holds its own share of
lifetime resonance against its `CharacterAuraShare.settled_percent` plus the range that applies to it; the
Mire is corruption now, not a share of the aura, so it has no part in this reading, #5177) and `check_resonance_focus(character,
technique)`, called once per cast from `_complete_technique_cast` inside
`use_technique` (after anima, before `resolve_fn` runs), so every cast path rolls it; a pull is
part of its cast and adds no steps, only being unsettled calls for the roll. Scene casts, combat casts, clash
contributions and standoffs gather modifiers inside `resolve_fn` (scene casts after the
PRE_CAST triggers too), so the conflict counts on the same roll. Technique-enhanced social
actions gather modifiers before `use_technique`, so the penalty counts from her next roll;
battles roll focus but their roll reads no condition modifiers (pre-existing,
`BattleTechniqueResolver`); the joust is not a cast. Every number and both designations
(focus check type, conflict condition) are on the `DriftConfig` singleton
(`get_drift_config()`): `unsettled_tolerance_percent` (5, the general range before Unsettled) and
`unsettled_step_percent` (5, one step of severity per band past it) (`mire_allowance_percent` was
removed in #5177),
`creation_points` (10) and `creation_seed_per_point` (10) for character creation,
`second_resonance_level_step` (10) for pull perks, plus the focus check's base difficulty and
per-step difficulty. **The range before Unsettled and the step are per main affinity (#4751):**
`Affinity.unsettled_tolerance_percent` (0 to 100) and `Affinity.unsettled_step_percent` (1 to 100) are
nullable, and `_unsettled_numbers(main, cfg)` in `services/drift.py` returns the main affinity's own
values when set, else the `DriftConfig` ones. Staff set them on the Affinity admin page: Celestial's range
is small (a Celestial-led character unsettles early by her own Abyssal acts), Primal and Abyssal keep the
general value. Never call the range "room" or "headroom" (the glossary's term is "range before Unsettled").
**Drift reads by side (#5231)**, `_range_for` in `services/drift.py`, and the step is always the main
affinity's: a Celestial main reads Primal and Abyssal at Celestial's range; an Abyssal main reads
Celestial only (Primal never) at Abyssal's range; a Primal main that leans to a side (`_lean_of`: the
larger settled share of Celestial and Abyssal, equal shares including both zero meaning no lean) reads
the opposite side at the range of the affinity she leans to and her own side at
`DriftConfig.own_side_tolerance_percent` (15, the own-side range); a Primal main with no lean reads
Celestial and Abyssal at Primal's range. So growth in Primal never unsettles a Primal character, and
unsettles a Celestial one.
The reading `drift_for` returns is a `DriftReading` (`types/drift.py`):
`steps_past`, `main_affinity`, `leading_excess_resonance` (the resonance named in "Your X has
grown strong enough to make you unsettled"), `shares` (each affinity's percent of lifetime
resonance), `settled_shares` and `excess_points` (the excess per affinity in lifetime points, what
atoning may convert). The earlier `own_shares`, `own_excess_points`, `mire_share_percent`,
`mire_excess_points` and `convertible_points` went in #5177. A Sineater who succumbs to the Mire
grows the Sinner's resonance in their own aura (`GainSource.SUCCUMBED`), which can put them past the
range before Unsettled like any resonance. A character with nothing settled
(no aura, or magic not yet provisioned) reads zero. Unset designations skip the check and show on the Required content
dashboard, which also flags a conflict condition with `break_free_mode` NONE or no
`ConditionCheckModifier`. The penalty is the conflict condition's authored
`ConditionCheckModifier`; never set `alters_behavior` for it (use `ConditionCategory.self_shakeable`).
The focus sentences are built once on `FocusOutcome.lines` (`types/drift.py`): telnet prints them, and the web cast result's `technique_result.focus_lines` carries them (#5123).
Stirring it up is an authored social action applying the condition at a severity (the higher wins), not code.

`models/renown_config.py` — `RenownAwardConfig`: **abstract base** (SharedMemoryModel)
shared by `DramaticMomentType` and `AudereMajoraThreshold`. Carries four authored
knobs consumed by `fire_renown_award`: `magnitude`, `risk`, `reach` (nullable
override), and `archetypes` (M2M to `PhilosophicalArchetype`). Provides
`as_renown_award_kwargs() -> dict`. When `risk == NONE`, `fire_renown_award` creates
no `LegendEntry` — the invariant that gates deed creation.

`audere_majora.py` — Audere Majora / Crossing the Threshold, the unified tier-crossing
event:
- `AudereMajoraThreshold` — one authored row per boundary level (5/10/15/20).
  Inherits `RenownAwardConfig` (magnitude/risk/reach/archetypes). Additional fields:
  gate thresholds (`minimum_intensity_tier`, `minimum_warp_stage`,
  `requires_active_audere`) + ceremony content + `deed_title` (public, non-spoiler
  CharField; blank → generic composed title). **`vision_text`/`manifestation_text`
  are spoiler-private: authored in the DB only; factories/tests use placeholders;
  never commit real ceremony wording.** `deed_title` is the only ceremony-adjacent
  field that may appear in code and tests.
- `PendingAudereMajoraOffer` — poll-able Crossing offer (AbstractPendingOffer +
  threshold FK; one per character).
- `AudereMajoraCrossing` — irreversible receipt (unique per sheet+threshold;
  `chosen_path`, scene + declaration-interaction links, level_before/after,
  `legend_entry` OneToOneField → `societies.LegendEntry` with
  related_name `audere_majora_crossing`). The receipt is the single source of truth
  and points to the deed it minted; `legend_entry` is null when the threshold has
  `risk == NONE` or when the crossing sheet has no primary persona. Survives
  character death.
- Services: `check_audere_majora_eligibility` (8 gates),
  `eligible_paths_for_threshold` (current path's child paths at the target stage),
  `maybe_create_audere_majora_offer` (cast hook in `services/techniques.py`;
  manifestation EMIT broadcast on creation only), `resolve_audere_majora_offer`
  (two-phase staleness + spend guards + path validation),
  `cross_threshold` (atomic: declaration pose → level write → path history → receipt
  → Majora condition → **`_mint_crossing_deed`**), `end_audere_majora` (encounter
  cleanup calls it alongside `end_audere`).
- `_mint_crossing_deed(crossing)` — called by `cross_threshold` after writing the
  receipt. Resolves the sheet's primary persona, calls `fire_renown_award`
  (full renown event — fame/prestige/legend/society-reputation), records every
  persona present in the scene as `WITNESSED` via `grant_deed_knowledge` +
  `scene_witness_personas` (#916), and links the minted `LegendEntry` back onto
  `crossing.legend_entry`. Deed title/description use `threshold.deed_title` (if
  authored) or a generic public-fact composition; ceremony text is never used.
  No-ops silently if the sheet has no primary persona.
- API: `/api/magic/audere-majora/pending/` + `/respond/`; frontend
  `AudereMajoraOfferGate`/`AudereMajoraOfferDialog` (amber ceremony dialog with path
  choice + declaration composer) mounted in the combat panel.
- `PathIntent` (`world/progression`) — pre-declared next path; the offer serializer
  pre-selects it when eligible.

**Ultimates (#4098):** `models/ultimates.py` - `KnownUltimate` (`character` CASCADE,
`technique` PROTECT, nullable `crossing` SET_NULL, `readied` bool; constraints: one
row per `(character, technique)`, at most one `readied=True` per character). An
ultimate is a `Technique` with `is_ultimate=True`, never a `CharacterTechnique` -
every ordinary cast surface reads `CharacterTechnique` and so excludes ultimates by
construction. Attaches via `PathGiftGrant.ultimate_techniques` (owned, major gifts
only), `WorshippedBeing.ultimate_techniques` / `CompanionArchetype.ultimate_techniques`
(bond, active-bond-only), `AlternateSelf.ultimate_techniques` (#4731, bond:
`UltimateSource.ALTERNATE_SELF` via `_alternate_self_pools`; choosing its card assumes the
self), and `Gift.ultimate_techniques` (#4118: MINOR gifts only,
`UltimateSource.GIFT` via `_gift_pools`; membership rules in `GiftAdminForm`, while
`Gift.clean()` only rejects flipping a gift with ultimates to MAJOR).

- **Reveal:** `services/ultimates.py`'s `ultimate_reveal_for(sheet)`
  derives the reveal fresh on every read, never an offer table - owned pools
  (current Path x major Gift for plain Audere, new Path x major Gift for Audere
  Majora), owned-known pools (any Path, still MAJOR), bond pools (active bond only),
  filtered through #4097's `exclude_unmet_technique_requirements`. Grouped by
  category (`Technique.archetype_alignment`, labels from
  `AudereThreshold.label_for_category`). A KNOWN card carries name + description; a
  CATEGORY (undiscovered) card carries the authored label only, never the
  technique's identity; an UPGRADE card carries `upgrade_of_name`.
- **Readied:** `choose_ultimate(sheet, choice_key)` (`@transaction.atomic`,
  `select_for_update`) re-resolves under the lock to close a double-submit race
  (stale read → `UltimateRevealClosed`), then `get_or_create`s the `KnownUltimate`
  row and sets `readied=True`. Choosing readies; it does NOT cast. `readied_ultimate`
  / `clear_readied_ultimate` / `castable_technique_named` / `has_reveal_cards` /
  `audere_ultimate_state` round out the surface. `offer_audere`/`end_audere`/
  `cross_threshold`/`end_audere_majora` each clear any readied pick at the right
  lifecycle point (accept, end, crossing).
- **Cast path:** `actions/types.py`'s `PlayerAction.is_ultimate` flags a readied
  ultimate in the combat action list (`actions/player_interface.py`'s
  `_combat_actions`). Telnet's `CmdDeclareTechnique._resolve_technique`/
  `_resolve_technique_id` (`commands/combat.py`) resolve it by name only while an
  active DECLARING round holds (`_combat_participant_or_none() is not None`) - never
  through `CmdClashCommit`'s shared `_find_technique_id`, so an ultimate cannot reach
  a clash contribution or a scene cast. Once declared, it resolves through the
  ordinary `use_technique` pipeline like any other technique.
- **Majora round block narrowing:** `any_character_mid_audere_majora_crossing`
  (`audere_majora.py`) checks only `PendingAudereMajoraOffer` existence now, not the
  whole Audere Majora condition lifetime - the original block froze every round for
  the rest of the encounter, which meant a crosser could never act on the new Path's
  ultimate. `is_mid_audere_majora_crossing` (single-character use) is unchanged.
- **Telnet:** `offer_handlers.py`'s `UltimateRevealHandler` (keyword `"ultimate"`)
  plus `format_ultimate_reveal`; the surge/crossing accept handlers append the
  listing. Every listing snapshots its shown `choice_key`s onto
  `caller.ndb.ultimate_reveal_choice_keys`; `accept ultimate <n>` refuses and
  reprints rather than resolving blind if the pool changed since the snapshot.
- **Deferred certain death:** see `world/vitals/CLAUDE.md`-adjacent coverage in
  `docs/systems/INDEX.md`'s Vitals section - Soulfray's `character_loss` consequence
  now calls `defer_or_apply_certain_death`/`apply_pending_certain_death`
  (`world/vitals/services.py`) instead of killing synchronously, and only ever runs
  that path inside a combat encounter.
- Full detail: `docs/systems/magic.md`'s "Ultimates" section;
  `docs/adr/adr-4098-ultimates-are-flagged-techniques-revealed-at-audere.md`.

**Manifestation (#4118):** `models/manifestation.py` - `TechniqueManifestOption`
(authored per technique: one of `being` / `archetype`, plus `tier`) and
`CharacterManifestation` (per character and technique: `option`, nullable `companion`;
`bond_is_active()`; `clean()` enforces option-belongs-to-technique and an active bond).
`services/effect_handlers.py`'s `manifest_bound_entity(participant, technique)` is called
from `CombatTechniqueResolver` after conditions apply, on a successful, unbounced cast: it
moves a being's avatar (or a companion's body) into the caster's room, then
`add_opponent(..., existing_objectdb=avatar)` as an ALLY, or materializes the character's
own companion. It manifests nothing for a failed roll, a caster with no location, a body
that is not in the caster's room after the move, a Savaged companion, or an avatar in
another running fight. A being option's tier needs an `OpponentTierTemplate` row or the
cast raises on purpose and the whole round rolls back (probe `manifest-tier-templates`).
The player chooses her own option with the technique picker (#4341):
`services/manifestation.py` (`manifest_choices_for`, `set_character_manifestation`), action
`manifest_set`, telnet `manifest <technique>=<option>`, `GET /api/magic/manifest-choices/`,
the Spellbook's `ManifestPickerPanel`. No CG picker, no out-of-combat manifestation. The flow-payload `summon_ally` is a separate
threat-pool summon and is untouched. Detail: `docs/systems/magic.md`'s "Manifesting a
bound entity"; ADR-4118.

### Sanctum (#1497 — TELNET+WEB)

The sanctum subsystem is a 7-op surface shared by telnet (`CmdSanctum`) and web
(`SanctumViewSet` in `views_sanctum.py`); both converge on `action.run()`.

**Actions** (`actions/definitions/sanctum.py`, all REGISTRY, `target_type=SELF`, `category="magic"`):
- `sanctum_install` — Ritual of Sanctification: validate presence/ownership/founder-cap, create
  `RoomFeatureInstance` + `SanctumDetails`. Leader authorization
  (`_validate_sanctification_leader` in `services/sanctum_install.py`) branches on
  `owner_mode`: Personal requires the leader persona to be the room's direct owner;
  Covenant requires the room to be owned by a Covenant-type organization, that the
  Sanctum kind's authored owner-type catalog currently permits covenant ownership
  (`_covenant_ownership_allowed_for_sanctum()`, reading `RoomFeatureKindOwnerType` —
  staff can revoke covenant eligibility there), and that the leader holds an active
  (`left_at IS NULL`) `CharacterCovenantRole` whose `CovenantRank.can_lead_rituals` is
  `True` — mere active membership is no longer sufficient (#708). Also validates/consumes the
  Sanctification Ritual's `RitualComponentRequirement` rows (#707) via
  `resolve_and_consume_ritual_components` (`kwargs["components_provided"]`,
  `resonance_context=kwargs["resonance"]` — a touchstone must match THIS Sanctum's own founding
  Resonance) BEFORE calling `perform_sanctification`. This is the one Ritual that does NOT
  dispatch through the generic `PerformRitualAction` seam (`client_hosted=True`), so this Action
  calls the shared helper directly rather than relying on `PerformRitualAction`'s own wiring.
- `sanctum_homecoming` — Ritual of Homecoming: sacrifice resonance to grow the Sanctum's
  Homecoming reservoir (wraps `perform_homecoming_ritual`).
- `sanctum_purging` — Ritual of Purging: change the Sanctum's consecrated resonance type,
  draining grown resonance as the cost (wraps `perform_purging_ritual`).
- `sanctum_weave` — weave a SANCTUM-anchored `Thread` (`slot=personal|covenant|helper`).
- `sanctum_dissolve` — soft-delete the sanctum (see dissolution below).
- `sanctum_absorb` — drain the weaver's pending weaving/owner-bonus pool into spendable
  resonance currency; physical presence in the Sanctum's room required (wraps
  `absorb_sanctum_pool`).
- `sanctum_sever` — soft-retire a SANCTUM-anchored thread by name or id.

**Outcome-tier award tables (#1207):** Homecoming/Purging/Dissolution no longer key on the
deleted `ritual_checks.OutcomeTier` enum or hardcoded multiplier dicts — each looks up an
authored per-`CheckOutcome`-tier row via the shared `world.checks.models.OutcomeTierAward`
base (the pattern generalizes `world.societies.models.GangTurfReputationAward`):
`perform_homecoming_ritual` reads `SanctumHomecomingGainAward.gain_multiplier`,
`perform_purging_ritual` reads `SanctumPurgingRetentionAward.retention_modifier` (signed —
can reduce retention below the base value), and `perform_dissolution`
(`_dissolution_recovery_fraction`) reads `SanctumDissolutionRecoveryAward.recovery_fraction`
(all in `world/magic/models/sanctum.py`, consumed from `services/sanctum_rituals.py` and
`services/sanctum_install.py`). Sanctification itself doesn't use an award table — it was
ported to plain `success_level` comparisons against literal thresholds
(`MINIMUM_SANCTIFICATION_SUCCESS_LEVEL` / `SANCTIFICATION_CRIT_SUCCESS_LEVEL` /
`CRITICAL_FAILURE_SUCCESS_LEVEL` in `services/sanctum_install.py`).

Module helpers: `sanctum_in_room(location)` returns the active `SanctumDetails` for the
room (excludes dissolved); `room_profile_for_location(location)` resolves a `RoomProfile`.

**Telnet surface** (`commands/sanctum.py` — `CmdSanctum`, key `sanctum`): namespaced `sanctum
<subverb>` `DispatchCommand` routing the 7 subverbs through `dispatch_player_action`. Bare
`sanctum`/`sanctum status` = hub. No business logic in the command. `install`'s kwargs include
`components_provided=self._gather_components()` — auto-gathers every `ItemInstance` the caller
is physically carrying (mirrors `CmdRitual._gather_components`), since Sanctification now carries
real seeded `RitualComponentRequirement` rows (see "Seeded touchstone/reagent content" below).

**Web surface** (`views_sanctum.py` — `SanctumViewSet.install`): `SanctifyActionSerializer.components`
is an explicit `ListField` of the caller's own `ItemInstance` pks (mirrors
`RitualPerformRequestSerializer.components` in `serializers.py`) — `validate_components` resolves
them and checks each belongs to the requesting sheet's inventory (`ItemInstance
.holder_character_sheet`, not the account — items are body-scoped per #684). The view forwards the
resolved list as `components_provided=` to `SanctumInstallAction().run()`.

**Seeded touchstone/reagent content** (`seeds_touchstone_content.py`, #707, #2973):
`ensure_resonance_tiers()` (Faint/Resonant/Profound, tier_level 1/2/3) is config and stays
seeder-owned. `ensure_touchstone_content()` (one example touchstone `ItemTemplate` — "Paw of a
Predatory Animal", tier 1, tied to whichever Resonance the row already carries or the first
authored one, skipped entirely if none is authored — plus 3 generic reagent templates:
candle/salt/incense) is a test-fixture builder only as of #2973; it no longer runs from the
production seeder. `ensure_sanctification_requirements(ritual)` (called unconditionally from
`seeds_sanctum.ensure_sanctum_rituals()`, a real deploy path) attaches the touchstone-mode
`RitualComponentRequirement` (tier-based, no `ItemTemplate` lookup needed) plus one
template-mode requirement per reagent it resolves via `authored_or_sample` by name — a reagent
absent from the content repo (and `SEED_SAMPLE_CONTENT` off) is skipped (`continue`), not
passed through as `item_template=None`, to protect the "at most one null-`item_template` row per
ritual" invariant against a future reordering of the touchstone/reagent blocks — today's fixed
ordering (touchstone-mode row created first) makes an unguarded call a harmless re-fetch of that
row, not an active collision.
So a real "sanctum install" requires a touchstone tied to the founding Resonance (tier ≥ Faint,
attuned to the founder) plus whichever of the three reagents are authored — content-repo work,
not seeder work. A full per-resonance/per-tier catalog is separate content-authoring work, not
framework work.

**Dissolution soft-delete** (#1497): `perform_dissolution` sets `RoomFeatureInstance.dissolved_at`
(nullable `DateTimeField`) rather than deleting the row. `RoomFeatureInstance.active()` queryset
excludes dissolved instances. SANCTUM-anchored threads are soft-retired (`Thread.retired_at`) on
dissolution — never hard-deleted. The `one_personal_per_character_sheet` DB `UniqueConstraint`
on `SanctumDetails` was removed (cross-table partial-unique limitation); one-personal-per-founder
is enforced in the service layer, excluding dissolved rows. Re-sanctifying the same room after
dissolution is a deferred follow-up.

### Portal Travel (#2222, ADR-0121)

A character who knows a travel-mode `Technique` (`travel_anchor_kind` FK set) and stands in a
room carrying a matching active `PortalAnchor` can travel instantly to any other room whose
matching anchor is open-or-standing — `TravelAction.execute()`
(`actions/definitions/movement.py`) tries this branch FIRST, falling through to #2163's
walking pathfinder unchanged when ineligible. `PortalAnchorKind` (staff-authored medium
catalog — arrival/departure verbs) and `PortalAnchor` (stackable per-room install,
soft-deleted via `dissolved_at`, one active per `(room_profile, kind)`) live in
`models/portals.py`; deliberately NOT a `RoomFeatureInstance` (one-feature-per-room
cardinality) or a `RoomDecoration` (wrong domain — see ADR-0121). Services
(`services/portal_travel.py`): `travel_anchor_kinds_for` / `portal_destinations` /
`portal_route` / `perform_portal_travel` / `install_portal_anchor` /
`install_portal_anchor_as_staff` (#2451 — the staff-authoring counterpart called from the
world-builder canvas: no owner/tenant standing check, no currency cost) /
`dissolve_portal_anchor` — never consults `RoomProfile.is_public`. Install costs a flat
`settings.PORTAL_ANCHOR_INSTALL_COST` (default 5000 copper); actions
`portal_anchor_install`/`portal_anchor_dissolve` (`actions/definitions/portals.py`), telnet
`CmdPortalAnchor` (`portal/install <kind>=<name>` / `portal/dissolve [<kind>]`). `PortalAnchor`
also carries an optional nullable-unique `fixture_key` (#2451) for grid-bundle export/import —
see the "Grid content export/import" area of `docs/systems/INDEX.md`. Discovery
API lives in `world.locations` (not this app) alongside `ComfortViewSet`: `GET
/api/locations/portal-destinations/?character_id=<id>`. Seed:
`ensure_portal_travel_content()` (`world/seeds/game_content/magic.py`) — the
content-authored "Mirror" anchor kind plus starter anchors in the seeded magic-story
cascade rooms, and nothing else. The "Mirrorwalking" Minor Gift + "Mirrorwalk" Technique
it used to invent were obliterated in #2967 (ruled a placeholder; the gift was also the
only one in the catalog with a non-empty resonance set, and its one resonance was the
invented "Reflection"). **Portal travel therefore has no content today** — the gate is
knowing a technique whose `travel_anchor_kind` is set, and that technique is lore-repo
content nobody has authored yet. Full eligibility chain + API/frontend detail:
`docs/systems/magic.md`'s "Portal travel" section.

## Fall / Redemption: Asymmetric Resonance Conversion (#1583)

The Fall/Redemption system lets characters convert their affinity through
dramatic ceremony. **Falling gains power; Redemption is lossy** (ADR-0054,
ADR-0134). Compromising acts (combat kills, cruelty, malice) grant
spendable non-native resonance via `grant_resonance` with
`source=GainSource.COMPROMISE` — the existing `CharacterResonance` rows hold it, and
whether it has made the character unsettled is `drift_for`, read on the aura those rows feed
(#5123). `recompute_aura` shifts affinity percentages; the Fall
becomes available when the target affinity crosses
`FallRedemptionConfig.fall_threshold_percent`.

**Models (`models/fall_redemption.py`):**
- `CompromiseActType` — authored act category → (target_resonance, amount,
  is_cruelty, feeding_taint_role). `is_cruelty` is staff-authored and
  separates acts that share an affinity (the affinity cannot). Staff author
  act types; mission/combat/social systems reference them.
- `ResonanceConversion` — authored mapping (source_resonance,
  target_affinity FK to `Affinity`) → target_resonance. One row per path.
- `FallRedemptionConfig` — singleton (pk=1, `ArxSharedMemoryManager`) with
  the fall threshold (the old penance exchange rate was removed, #4751). The per-path multipliers and
  Fall/Redemption type are `AffinityInteraction.conversion_multiplier` /
  `conversion_type` on the directed (source, environment) pair; a database
  check keeps the two both set or both unset. `from_affinity`/`to_affinity`
  on `FallRedemptionRecord` are `Affinity` FKs.
- `FallRedemptionRecord` — immutable audit of a full (irreversible) Fall
  or Redemption. `ConversionType` TextChoices: FALL / REDEMPTION.

**Services:**
- `services/conversion.py` — `convert_resonance()` is the full (Fall / Redemption)
  conversion engine; `convert_resonance_amount()` is the single-resonance primitive the
  settling rite uses. `convert_resonance` transfers `balance` and
  `lifetime_earned` (scaled by multiplier) from source to target resonance.
  `lifetime_earned` is transferred, not decremented — the total is preserved
  modulo the multiplier, so `recompute_aura` shifts correctly. Full
  conversion converts each live thread's `ThreadResonance` rows in the affinity (scaling
  amounts and points, merging rows that land on one resonance, then
  `refresh_leading_resonance`).
- `services/fall_redemption.py` — `grant_compromise_resonance()` (thin
  wrapper over `grant_resonance`), `perform_fall()` (the full ceremony,
  gated by aura threshold + irreversibility; after the conversion it calls
  `drift.settle_shares`, the settle step `accept_aura_change` also uses, so a Fall or
  Redemption also moves who she is: her `settled_percent` follows her new own shares and
  `steps_past` reads 0, #5123), `get_fall_redemption_config()`.

**The old Rite of Atonement is gone (#4751).** The settling rite (below) is the only rite for a
changing aura; "atonement" is the plain word for the reflections that turn away from something
(disowning). Corruption a character carries falls by daily decay, a Sineater's rescue and, since #5177,
Sineating (a Sineater takes it on, `services/mire.py`): the old rite's cut to corruption at stages 1 and 2
was not carried over. Only Abyssal casts corrupt (Primal's
canonical `corruption_coefficient` is 0). Removed with it: `services/atonement.py`,
`FallRedemptionConfig.penance_exchange_rate`, `GainSource.PENANCE` and its grant constraint,
`CorruptionRecoverySource.ATONEMENT_RITE`, `PenanceError`, the partial path of `convert_resonance`, and
the Ritual row (migrations 0448 and 0449). ADR-4751.

**New `GainSource` values** (all `NON_ACCELERATED_GAIN_SOURCES`):
`COMPROMISE`, `FALL_CONVERSION`. No typed source FK
(MISSION_REPORT shape). Two `ResonanceGrant` CheckConstraints.
`DRIFT_CORRECTION` (#4733) joins them with `res_grant_drift_correction_shape`. #5177 adds
`MIRE_PURIFIED`, `SUCCUMB_BONUS` and `SINEATER_FALL` (non-deeds, no typed source FK), and `SUCCUMBED`
(a **deed**, in `DEED_GAIN_SOURCES`; it carries the rite and the burden reflection like
`EMBRACED_DEED`, so the Sineater can reflect on the succumbing and atone); all four are
`NON_ACCELERATED_GAIN_SOURCES`. `SINEATING` is the payout for performing it.

**Drift correction and the rite of settling (#4733, slice 4 of #4672; #5124).** Atoning (#5123) reads
lifetime, not balance: `drift_holdings` is resonance of a non-main affinity that stands past who
the character is (`DriftReading.excess_points`); `AuraDrift` / `recompute_aura` is the
older sense (shift in aura percentages). Do not mix the two in names. Nothing settles without a
reflection behind it: the one **rite of settling** (`perform_settling_rite`,
`services/drift_correction.py`; action `PerformSettlingRiteAction`, key
`perform_settling_rite`) takes every waiting `Reflection` (`rite` null) and applies one roll's share to
each. `accept_aura_change(sheet, fraction=Decimal(1))` (`services/drift.py`) is its internal step for
Embrace of the unsettling resonance, no longer an action: refused with `NotUnsettledError` unless
`steps_past > 0`; at a full fraction it sets each `settled_percent` to the aura's share, at a part
fraction each settled share moves that part of the way (`settle_shares(sheet, fraction)`), at 0 nothing
moves; writes no corruption. (It no longer moves a Mire lifetime: `mire_lifetime` is gone, #5177.)
`AcceptAuraResult.grown_affinity` is the affinity of the resonance that made them unsettled, read
before accepting; it is what "You become more abyssal." names.
- Models (`models/drift.py`): `DriftCorrectionConfig` (singleton; `rite`, `check_type` null until
  staff author them; `check_difficulty_level`; `cap_percent`; `disown_deed_percent`, the share of a disowned
  deed the rite converts at a full roll), `DriftCorrectionOutcomeShare` (an `OutcomeTierAward`;
  `converted_share` is the fraction of each reflection the rite carries out; `clean` keeps it
  monotonic by success level), `DriftConversionOffer` (one per sheet; `scene` is where it first
  opened), `DriftConversionCap` (per offer and target resonance; `grants` names the deed grants it was
  measured from; `cap` is a snapshot). `RitualComponentRequirement` has a third mode,
  `matches_target_resonance` (optional `min_item_meaning`, minimum 1), exclusive with `item_template`
  and `min_touchstone_tier`.
- Deeds: every `GainSource` is in exactly one of `DEED_GAIN_SOURCES` / `NON_DEED_GAIN_SOURCES`
  (test-enforced); a new member must be placed. `grant_resonance` ends with
  `open_or_extend_conversion_offer(grant)` (`services/drift.py`): deed, own-affinity target,
  convertible drift, and the grantee standing in a live scene (room scene at grant time, so a
  deed settled away from a scene opens nothing). The chance no longer lapses with the scene: it
  stays open until the rite spends it, and later deeds in any scene extend its caps.
- The rite: refuses, writing nothing, with no waiting reflection (`NoWaitingReflectionError`), with
  the rite unready (`rite_is_ready`: a rite, a check type and a share for every `CheckOutcome`;
  `RITE_NOT_READY_MESSAGE`) and with an offering that satisfies the rite for none of the resonances it
  moves (`rite_resonances`: each reflection's resonance, a burden's holdings and then the
  Sineater's own thread's resonance, then the main-affinity resonances when anything is disowned or a
  burden is settled). Then it rolls `check_type` with `focus_bonus` toward the resonance the
  offering is tied to, writes a `SettlingRite` (outcome, share, scene), spends the offering whatever
  the roll, applies the share and sets `rite` on every reflection, even at a share of 0. Order:
  disowned deeds, the disowned unsettling resonance, burdens (below), embraced deeds, accepting, and
  `apply_fall` last. Embrace a deed
  grows `embraced_amount(sheet, grant, s)` as `EMBRACED_DEED` (`grant_resonance(settling_rite=, reflection=)`):
  `grant.amount x s`, and for a deed of an affinity other than her main one also x the direction rate
  `conversion_pair(main, deed affinity).conversion_multiplier` (a fall toward the Abyss pays more than the
  deed was worth, a climb pays less; no authored pair leaves the rate at 1). The preview reads the same
  helper (#4751);
  disown a deed converts `amount x disown_deed_percent x s` (no open chance needed, up to the
  deed's resonance lifetime); when no usable conversion is authored for the pair, `_convert` returns a
  `_Conversion` carrying `missing_pair` and the line says "no conversion from X to Y has been set"; embrace the unsettling resonance calls `accept_aura_change(fraction=s)`;
  disown it converts up to the open cap toward the conversion target x s, bounded by what stands past
  who she is, and the cap falls by what converted. Conversions turn toward
  the main-affinity resonance the offering is tied to, else (`fallback_conversion_target`, which the
  preview's effect line also reads) the one with the largest open cap when the rite disowns the unsettling
  resonance, else the largest main-affinity resonance held,
  through `convert_resonance_amount` as `DRIFT_CORRECTION`; nothing after the roll raises (an effect
  that cannot happen is a line saying so). The check type is NOT a `RitualCheckConfig` sidecar.
  Never match the rite, check or affinities by name. `rite_is_ready(config=None)` (one query,
  through `outcome_tiers_without_a_share()`, which the Required content probe reads too) is the one
  readiness test. `SettlingRiteResult.lines` are the performer's alone.
- Reads: `services/settling_preview.py` `settling_rite_reading(sheet, items)` (waiting reflections as
  a player reads them, the offerings among `items`, readiness) feeds `GET /api/magic/settling-rite/`
  and telnet `aura`; `open_cap_line(sheet)` is the open-chance sentence.
- **Burden reflections and settling the Mire (#5177; ADR-5177).** `Reflection` names exactly one of
  `grant`, `resonance` or `tether` (the Sineater's own `CharacterRelationship` side), enforced by
  `reflection_exactly_one_target`; `ReflectionTargetKind` is DEED / RESONANCE / BURDEN. A burden takes
  only `ReflectionChoice` ABSOLVE / CONDEMN / SUCCUMB and a deed or the unsettling resonance only
  EMBRACE / DISOWN (`reflection_choice_fits_target`; `BURDEN_REFLECTION_CHOICES` /
  `DEED_REFLECTION_CHOICES`); a newer waiting burden reflection on a tether replaces the older. Telnet
  names a burden `mire:<Sinner>` (`BURDEN_PREFIX`) in `reflect`, `pose/reflect` and `journal/reflect`.
  `reflectable_for` lists one burden per tether with anything held, and `SUCCUMBED` grants as deeds
  beside kindled ones (`deed_what` / `deed_label` describe them by the pose or journal entry of the
  succumbing). The rite applies each burden in `services/mire_settling.py` at its share `s`, per
  resonance held from that Sinner: **Absolve/Condemn** `cleared = floor(held x s)` leaves the Mire
  (`release_mire`, no cleansing payout), the tether's `mire_purified_since_payout` rises by it, the Sineater earns
  `purify_reward_percent` of it in their own thread's resonance (`MIRE_PURIFIED`), and their side of the
  tie moves by `absolve_affection` / `condemn_conflict` x `s` (`move_gauges`); **Succumb**
  `taken = floor(held x s)` leaves the Mire and is granted as the Sinner's resonance in the Sineater's own
  aura (`SUCCUMBED`, with the rite and reflection), the tether's `mire_succumbed_since_fall` rises, the Sinner earns
  `taken x succumb_bonus_percent + mire_purified_since_payout x jackpot_percent` of their thread's resonance
  (`SUCCUMB_BONUS`; the jackpot is the tether's, paid once and reset to 0), both gauges move, and the
  Sinner's `sineater.succumbed*` stats rise. **The fall** (`apply_fall`, once per rite, last): when the
  Sineater's aura is now predominantly Abyssal each Sinner whose tether has `mire_succumbed_since_fall` above 0 earns
  `fall_payout_percent` of it (`SINEATER_FALL`), the Sinner of the most recent Succumb
  `fall_breaker_bonus_percent` more, and every counter resets (what stops a second payout for one
  fall). The Sinners' lines are `RiteNotice` rows on the result, sent by the action after the rite
  commits as stored narrative messages (`send_stored_notice`), so an offline Sinner reads them at login;
  the Sineating result lines to a Sinner are stored the same way, and the plea notice to the Sineater is a
  live line. `SUCCUMB_BONUS` and `SINEATER_FALL` are in `PASSIVE_DEED_SOURCES` (no pledge favor). The preview (`settling_preview`) reads the same numbers. A Sineater who succumbs is usually
  Unsettled and atones by reflecting on the succumbing deed and choosing Disown, or Embrace to keep it.
- Components: `qualifying_components_by_target` (`ComponentMode` MATERIAL, FACET, KEEPSAKE, in that
  order). `focus_bonus` adds to the check, not the output. `max_yield_per_earned_point` is the
  anti-farm estimator (per point). A cap grows by `amount x cap_percent // 100` per deed; only the
  deed that creates the cap row is floored at 1; `cap_percent` 0 opens no offer.
- Closing: `close_spent_conversion_offers(sheet)` (`services/drift.py`, #5123) is the one writer that ends an offer early: it deletes the caps whose target has no convertible drift left, and the offer with its last cap. The rite and `accept_aura_change` call it after they write.
- Surfaces: `PerformSettlingRiteAction` (`actions/definitions/drift_correction.py`), telnet `aura` /
  `aura settle <offering>` (`commands/drift_correction.py`), REST `/api/magic/settling-rite/` (GET
  reading, POST perform) and `/api/magic/drift-correction/pending/` (the open chance), React
  `SettleAuraDialog` and the sheet's `AuraReflections` (`frontend/src/magic/CLAUDE.md`). #5124 removed
  the separate accept, atone and decline actions with their endpoints and verbs, the scene-page gate
  and the scene-end lapse of the chance. Required
  content rows `drift-correction-config` and `affinity-conversion-pairs` (every ordered pair of distinct
  affinities has a `conversion_multiplier` and `conversion_type`). Details: `docs/systems/magic.md` "Drift correction".

**Thread retune (#4735, slice 6 of #4672; reshaped by #5123).** `services/thread_resonance.py` moves
part of ONE `ThreadResonance` row of a thread to another resonance's row through the SERVICE
ritual at `THREAD_RESONANCE_SERVICE_PATH` (found by path, never by name): same affinity one to one,
across affinities at the `conversion_pair` rate floored at 1, "from" defaulting to the leading
resonance and the amount to all of that row. Level and `developed_points` are unchanged;
`refresh_leading_resonance` runs after. `PerformRitualAction._precheck` calls
`check_thread_resonance_change` before components and anima are spent;
`kwargs["target_resonance"]` is the components' `resonance_context`. A refusal after the
spend (any caught exception a SERVICE raises) rolls the perform back,
and `_spend_restored_on_raise` puts the cached items, their game objects, the holder's contents
and the anima row back to match, for every ritual; `perform_fall` does the same for the resonance,
thread and thread-row state a half-done Fall moved (`conversion_restored_on_raise`). Both sit OUTSIDE the
`transaction.atomic()` they guard, so they run after the rollback. Telnet
`from=<id> amount=<n> resonance=<id>`, REST `GET /api/magic/threads/{id}/resonance-options/`. A SANCTUM thread or a
TECHNIQUE thread whose signature bonus requires a resonance cannot move
(`thread_resonance_refusal`); a GIFT thread stays within a non-empty `gift.cached_resonances`.
Required content rows `thread-resonance-ritual`, `thread-resonance-ritual-single`,
`thread-resonance-ritual-web-payable`. Details: `docs/systems/magic.md` "Thread retune".

**Seed content:** `wire_fall_redemption_content()` in `factories.py`,
called by `seed_magic_dev()`. Seeds the "Ritual of Falling" Ritual row
(SERVICE dispatch), the `FallRedemptionConfig` singleton, example
`CompromiseActType` rows, and example `ResonanceConversion` mappings.

## Kindled resonances (#5124, ADR-5124)

Player word: **kindled** ("stirred" appears nowhere). A resonance is kindled when one of its
`KindlingSituation` rows holds; Fury's anchor person is gone (`fury_resonance`), the thread-anchor
bond is one situation among many. Full tour: `docs/systems/magic.md` "Kindled resonances".

- **Rows** (`models/kindling.py`): `KindlingSituation` (a `SituationRequirementMixin` subclass; set
  on a `resonance` or once on an `affinity`, a check constraint demands exactly one; `strength` is a
  rank, blank reads it from the bond tier or condition severity and `clean` refuses blank where there
  is no source), `KindledStrengthTier` (natural key `rank`; the staff-named strength and every number
  that follows from it: `min_bond_tier`, `min_severity`, `pull_levels`, `give_in_max_depth`,
  `give_in_bonus_percent`, `give_in_ease_tenths`, `dig_deep_scale_percent`, `earn_percent`,
  `cast_power`, #5231; `Affinity.kindled_boost_percent`, default 100, scales `pull_levels` and
  `cast_power` per affinity so Abyssal's can be larger),
  `KindlingConfig` (singleton, `harm_property`), `KindledDeedAward` and `RallyKindlingStrength`
  (`OutcomeTierAward` tables), `Kindling` (Rally or GM only, `encounter` XOR `scene`).
  `Resonance.feeling` (Property FK) is what the feeling situations match; `missions.MissionTheme`
  is what `MISSION_THEME` matches. Never match a feeling or theme by name.
- **Code compares `KindledStrengthTier.rank`, never a name.** Faint, Strong and Blazing are seed and
  test data that staff can rename; players read the name and never a number.
- **One read path.** `services/kindling.py`: `kindled_resonances` / `kindled_for` (pass the
  `resolution` and `mission` you hold, and an `act` to ask "does this act feed it"),
  `kindling_context_for(sheet)` and `kindled_resonances_now(sheet)` when you hold neither,
  `kindled_tiers` (the map a pull reads), `kindled_resonances_for_acts` (many acts, one pass). Do
  not call `kindled_resonances` per row: it costs several queries, and the evaluation already
  dedupes reads per distinct (situation, params). The six new `Situation` members live in
  `world/covenants/perks/constants.py` with evaluators that call the same finders
  (`KINDLING_EVIDENCE_FINDERS`), so a vow perk and a kindling read one logic.
- **Uses.** Drawing strength: `resolve_pull_effects(..., kindled=)` adds the payer's tier
  `pull_levels` times its affinity's `kindled_boost_percent // 100` to the level the multiplier reads
  (resolution only, never the thread; never lowers a read). Since #5231 a second kindled resonance on
  the thread adds too (`_second_resonance_boost`): one that has a row on the thread, is kindled and is
  Primal where the payer is not, or the reverse, adds its boost times its share of everything imbued
  (`boost * amount // total`), whether or not the payer is kindled; the largest such addition counts and
  none counts while nothing is imbued. A payer that brings no perks never competes for the stronger
  mark in the pull preview (`PayerOption.stronger`). A cast worked in a kindled resonance is stronger
  (`kindled_cast_power_term`, below). Giving in: `fury.give_in_strength`, `give_in_refusal` (an unkindled resonance is refused
  in words, a tier deeper than the strength reaches is refused; Fury reads kindling with no act).
  Dig deep and Rally name a resonance (`dig_deep(participant, resonance=)`,
  `declare_rally(participant, ally, resonance=)`; a rallier sees whether the ally's resonance is
  kindled, never a strength; a Rally writes one `Kindling` at `RallyKindlingStrength(outcome)`).
  GM: `kindle_by_gm`, action `stage_kindle`, telnet `stage kindle`. Earning:
  `award_kindled_deeds` writes one `GainSource.KINDLED_DEED` grant per resonance an authored
  situation fed, `KindledDeedAward(outcome).amount x earn_percent // 100`, with
  `grant_resonance(kindling_situation=)`; seams are named in `docs/systems/magic.md`. A rollless act
  earns at `lowest_success_outcome()`.
- **Surfaces.** `GET /api/magic/kindled-resonances/` (`views_kindling.py`; its response carries an
  `impulses` list beside `results`, see "Corruption impulses"), telnet `resonances`,
  `GET /api/magic/reflectables/` (`views_reflection.py`) and telnet `reflect`, `pose/reflect`,
  `journal/reflect`. Reflections and the rite are in "Drift correction and the rite of settling"
  above. The model map and `docs/systems/INDEX.md` list the signatures.
- **Admin.** Situations are authored inline on the Resonance and Affinity pages; the strength tiers,
  Rally strengths, deed amounts and harm property are one page, "Kindling config".

## Corruption impulses (#5177, ADR-5177)

`services/impulses.py`. A character carrying corruption in a resonance, their own or a Sineater's Mire
(one store), feels it pull. The same code serves a Sinner and a Sineater because it reads corruption, not
the tether.

- **Config.** `CorruptionConfig`: `light_corruption_percent` (10) and `full_corruption_from_share` (50, #5231; see "A cast
  is worked in one resonance"), `intrusive_thoughts_stage` (1), `compulsion_stage` (2), `sineater_max_stage`
  (2; `clean` keeps it and `compulsion_stage` at or above the first), `compulsion_condition` (nullable FK to a `ConditionTemplate`
  staff author with a scene duration and a check modifier that scales with severity),
  `compulsion_indulge_corruption` (5). `Resonance.impulse_text` is the words staff write for a resonance's
  impulse. Required content probes list an unset Compulsion condition, one without a scene duration and one
  with no check modifier.
- **Display only.** `corruption_display_name(instance_or_template, stage_order, resonance=None)` names a
  corruption condition "Intrusive Thoughts: <resonance>" from `intrusive_thoughts_stage` and "Compulsion:
  <resonance>" from `compulsion_stage`; the condition serializers (`condition_display_name`, owner and
  observer), `mire_carried_by`, telnet `resonances` and the Soul Tether panel use it. No template is renamed
  and it is never a lookup key. **This `Compulsion` is a name on a corruption condition; it is not the
  control-loss `Compulsion` model in `world/conditions/models.py`** (forbidden actions and resist bands on a
  condition template). The corruption Compulsion is a display name plus a penalty condition and never reads
  or writes that model; the way to tell them apart is the code path: `corruption_display_name` and
  `CorruptionConfig.compulsion_condition` here, `Compulsion` rows in the conditions app.
- **Reading and applying.** `impulses_now(sheet)` returns an `Impulse` per resonance the character carries
  corruption in at the Intrusive Thoughts stage or above (`present` = `kindled_for(...).fed_tier` is set,
  that is, an authored situation of the resonance holds; `text`, `reasons`, `is_compulsion`) and writes
  nothing. `refresh_impulses(sheet, scene)` applies: with the situation present it sends the impulse words
  once per resonance per scene (`ImpulseShown`), and at the Compulsion stage, unless the resonance was earned
  by a `COMPULSION_INDULGING_SOURCES` grant since the scene began (`earned_in_scene`), lays `compulsion_condition` at severity
  `stage - compulsion_stage + 1` (keeping a higher one) and lifts it when nothing compels any more. It is
  called explicitly: after a pose posts (web `_refresh_impulses_after_pose`, telnet pose), before a cast's
  modifiers are gathered, and when the kindled panel or telnet `resonances` is shown.
- **Giving in.** `grant_resonance` calls `give_in_to_compulsion(grant, row)`: for a grant whose source is in
  `COMPULSION_INDULGING_SOURCES` (`constants.py`; only `KINDLED_DEED`, the instant share of the character's own
  deed; a claim (`KINDLED_CLAIM`) and an Anima ritual (`ANIMA_RITUAL`) do not join it, since the Compulsion
  lifts when the deed is done; a grant from another player, a GM or a cron, and `SUCCUMBED`, never counts) of a resonance the character is compelled by, in a live scene
  and the first such deed there, it lifts the Compulsion for the scene, accrues
  `compulsion_indulge_corruption` (`CorruptionSource.INDULGED`: exact, no resistance, the Hollow absorbs none)
  and, for a Sineater, assigns it to their largest holding (`add_to_largest_holding`). The line goes out in
  `transaction.on_commit`, and a failure is logged and forfeits only the giving in (`_isolated`). Every refresh
  call site uses `safe_refresh_impulses` / `safe_refresh_impulses_for_character`, which log and swallow a
  failure, and the web pose refreshes after the reflection and the Sineating so it can skip neither. A line
  is not spent (no `ImpulseShown` row, nothing sent) while the character has no live session.
- **Where it shows.** `GET /api/magic/kindled-resonances/` returns `impulses` (resonance, `label`, `present`,
  `is_compulsion`, `text`, `reasons`); `KindledResonancesPanel` draws them.

## Removed Models (deprecated)

The following models have been removed and replaced:
- `Power` - Replaced by `Technique` (player-created abilities)
- `CharacterPower` - Replaced by `CharacterTechnique`
- `AnimaRitualType` - Replaced by freeform stat+skill+resonance system
- `ResonanceAssociation` - Replaced by the `Facet` model (flat vocabulary as of the
  2026-09-11 ruling, #3776 — originally hierarchical)
- `Thread` (legacy 5-axis model), `ThreadType`, `ThreadJournal` - Legacy 5-axis thread family
  (a legacy `ThreadResonance` went with it; the live `ThreadResonance` of #5123 is a new model,
  see "Thread System"). Replaced by the new
  `Thread` discriminator + typed-FK model and supporting catalogs
  (`ThreadPullCost` / `ThreadXPLockedLevel` / `ThreadPullEffect` /
  `ThreadWeavingUnlock` / `ThreadLevelUnlock` / `CharacterThreadWeavingUnlock` /
  `ThreadWeavingTeachingOffer`). See "Thread System (Resonance Pivot Spec A)"
  above.
- `CharacterResonanceTotal` - Superseded by `CharacterResonance.lifetime_earned`
  (monotonic, updated via `grant_resonance`); aura recompute reads that field via
  `recompute_aura`, not a `CharacterModifier`/resonance-category walk (#1836). Distinction
  effects targeting a resonance-category `ModifierTarget` no longer write a
  `CharacterModifier` row at all — they flow through
  `reconcile_distinction_resonance_grants` (the `DistinctionResonanceGrant` sidecar)
  instead (#1834). The `resonance` `ModifierCategory` itself is still live infrastructure
  for non-distinction sources — facet/mantle/motif-coherence passive bonuses
  (`equipment_walk_total` in `world/mechanics/services.py`) still read/write
  resonance-category `CharacterModifier` rows via `EQUIPMENT_RELEVANT_CATEGORIES`.

### Distinction Resonance Grants (standing/currency axis, #1834)

`DistinctionResonanceGrant` (`models/grants.py`) — sidecar authoring surface joining a
`distinctions.Distinction` to a `Resonance` with two rank-scaled currency knobs:
`flat_amount_per_rank` (seed) and `earn_rate_bonus_per_rank` (percent). Lives in
`world.magic` (not `world.distinctions`) per ADR-0010 — the general primitive
(`magic.Resonance`) must not import back into a dependent app.

- `reconcile_distinction_resonance_grants(character_distinction)`
  (`services/distinction_resonance.py`) — the grant-time consumer, called by both
  `create_distinction_modifiers` and `update_distinction_rank`
  (`world/mechanics/services.py`). For every `DistinctionResonanceGrant` on the
  distinction: establishes a `CharacterResonance` row (`get_or_create`), then tops off a
  rank-scaled flat seed via `grant_resonance(source=GainSource.DISTINCTION,
  source_character_distinction=...)`. Ledger-idempotent (sums this distinction's prior
  `DISTINCTION`-source grants for the resonance, grants only the shortfall); a rank-down
  never claws back.
- `distinction_earn_rate_for(character_sheet, resonance)` (`services/distinction_resonance.py`)
  — sums the earn-rate bonus across a character's distinctions for one resonance. Read by
  `grant_resonance` (`services/resonance.py`) to scale `amount` up before writing, but only
  when `source in ACCELERATED_GAIN_SOURCES` (ADR-0041 — perception/presence sources); the
  `DISTINCTION` seed itself is in `NON_ACCELERATED_GAIN_SOURCES` (accelerating it would be
  circular). A total-classification test asserts every `GainSource` lands in exactly one set.
- `GainSource.DISTINCTION` + `ResonanceGrant.source_character_distinction` — ledger
  discriminator + typed source FK for the seed grants above.
- Wired at both acquisition sites: gameplay grant/rank-up and character creation
  (`_create_distinction_modifiers_bulk` in `world/character_creation/services.py`, followed
  by `recompute_aura` once `CharacterAura` exists in `finalize_magic_data`).
- **Reverse direction (#2037):** `DistinctionResonanceRankThreshold` (`models/grants.py`,
  unique `(distinction, resonance, rank)` + `lifetime_earned_threshold`) authors "sustained
  investment in this Resonance ranks up that Distinction."
  `check_distinction_rank_thresholds(character_sheet, resonance)`
  (`services/distinction_resonance.py`) is the consumer, called by `grant_resonance` only
  when `source in ACCELERATED_GAIN_SOURCES` (never for `DISTINCTION` seeds — feedback-loop
  guard). Ranks up **held** distinctions only (threshold keyed to exactly
  `current_rank + 1`, which is also the re-fire guard), loops to a fully caught-up state per
  grant, routes through `grant_distinction(origin=ENDORSEMENT_THRESHOLD)`, catches/logs
  `DistinctionExclusionError`, and is failure-isolated in `grant_resonance` so the resonance
  grant always stands.

### Distinction Potency (POWER axis, #1834 Task 7)

A distinction expresses **potency** for a resonance — as opposed to the identity/currency
axis above — by authoring a normal `DistinctionEffect` whose `target` is a POWER-category
`ModifierTarget` gated by `target_resonance` (the same scope-gate seam
`motif_coherence_bonus` and tier-0 thread-pull FLAT_BONUS rows ride). `create_distinction_modifiers`
writes this as an ordinary `CharacterModifier` (POWER-category rows are unaffected by the
resonance-category skip above). Two consumers read it:

- **Casts** — already wired: `_partition_power_targets`/`_derive_power`'s FLAT stage
  (`world/magic/services/techniques.py`) scope-matches the target against the technique's
  gift-resonances and folds `get_modifier_breakdown(sheet, target)` into the power ledger.
- **Thread pulls** — `world.mechanics.services.power_flat_bonus_for_resonance(sheet,
  resonance_id)` mirrors cast scope semantics: sums POWER-category targets whose
  `target_resonance` is null (unscoped) or matches `resonance_id` (excluding the unscoped
  `power_multiplier` target) via `get_modifier_total`. `world.magic.services.resonance
  ._fold_distinction_pull_bonus` folds it once per pull (not per thread/tier): the unscoped
  targets once, plus each distinct pulled resonance's scoped targets (a pull may mix
  resonances, #5066), and appends a synthetic `FLAT_BONUS`
  `ResolvedPullEffect`; wired into both `spend_resonance_for_pull` (the charge/commit path —
  persists into `CombatPullResolvedEffect` for combat, returned ephemerally otherwise) and
  `preview_resonance_pull` (so the read-only preview matches the eventual commit).

**Not full parity with a cast.** A cast's FLAT stage (`_derive_power`) also sums
condition-sourced POWER contributions via `get_condition_modifier_breakdown` — the pull fold
only sums the `CharacterModifier` (distinction) side via `power_flat_bonus_for_resonance`. A
character with an active condition that boosts POWER for this resonance sees it in a cast but
not in a standalone pull.

## Design Docs

- `docs/plans/2026-01-20-magic-system-design.md` - original system design
- `docs/plans/2026-03-02-cantrip-technique-alignment.md` - cantrip/technique alignment + spell mechanics
- `docs/plans/2026-03-04-path-cantrip-filtering-design.md` - path-based cantrip filtering design
- `docs/architecture/resonance-threads.md` - Resonance Pivot Spec A (Threads + Currency + Rituals + Mage Scars rename)
- `docs/architecture/resonance-gain.md` - Resonance Pivot Spec C (Endorsements + Room Aura + Residence Trickle)
- `docs/architecture/soul-tether.md` - Resonance Pivot Spec B (Soul Tether bond mechanic)
- `docs/adr/0134-resonance-as-drift-compromising-acts-grant-spendable-non-native-resonance.md` - Resonance-as-drift decision (#1583)

## Key Rules

- Player-facing data is narrative, not numerical (aura shows prose, not percentages)
- Affinities and Resonances are proper models in this app, not ModifierTarget entries
- FKs to affinities/resonances point directly to Affinity/Resonance models (type-safe)
- Use SharedMemoryModel for lookup tables (via mechanics.ModifierTarget)
- Technique has intensity (power) and control (safety/precision) as base stats
- Technique tier is derived from level (1-5=T1, 6-10=T2, etc.)
- CG links a staff-authored catalog Gift + Techniques — it never mints new rows (#2426)
- Bounded mends are castable via `TechniqueTreatment` payload rows → `perform_treatment` (#2668); the attrition invariant (ADR-0156) holds — per-healer-once-per-wound, never-to-full fraction. Magical treatment works in combat (`skip_engagement_gate=True`); mundane treatment stays non-combat-only. **Power scaling (#3391):** `TreatmentTemplate.mend_intensity_multiplier` (`DecimalField`, default 0) scales the outcome-tier mend amount by the caster's `eff_intensity`/`power_intensity`, added strictly after `_map_outcome_to_mend`'s gate (a failed/unmended-tier outcome still mends 0 regardless of power) and strictly before `mend_wound()`, whose fraction cap and `max_health` clamp remain the final word — power composes with the double-bound (ADR-0156), it does not bypass it. Dispel's sibling power leg is `TechniqueRemovedCondition.cure_power_multiplier`, feeding the opposed cure check's `extra_modifiers` — see "Dispel / Cleanse" above.
- Mend fraction (#4600): each `TechniqueTreatment` row authors `mend_cap_fraction` (default 0.75, at most `NEVER_TO_FULL_FRACTION`), threaded through `perform_treatment(mend_cap_fraction=)` into `mend_wound(cap_fraction=)`; a wound never heals past the highest fraction any healer used on it, and the scene `treat` path passes `FIRST_AID_MEND_FRACTION` for a mundane treatment only (`conditions.services.is_magical_treatment` False).
