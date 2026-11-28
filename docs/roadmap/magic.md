# Magic System — Playable-Loop Status

**Status:** engine essentially complete; blocked on onboarding/content, not mechanics.
**North star:** a player can **cast → see it posed into the scene → it's logged → it
resolves an outcome**, in a live RP scene in the web client.

This is the **status map** — the one place to answer "where are we / what's left." The
full scope-by-scope build record lives in
[`magic-build-history.md`](magic-build-history.md) (archive; consult it before designing
anything new, to avoid reinventing existing surfaces). When this doc and the archive
disagree, this doc and the code win.

**Capability tiers + MVP sequencing:** [`player-capability-ledger.md`](player-capability-ledger.md)
(DO / GROW / COMBINE pillars). **Gift/resonance economy decisions:** ADR-0050–0057 — Major/Minor
gifts (species abilities as Minor Gifts), gift-thread strength + resonance, XP-unlocks-gate-never-grant,
the one specialization engine, fall/redemption, Covenant of the Court.

## The playable loop, stage by stage

| Stage | Status | Where |
|-------|--------|-------|
| Cast initiation — REST `POST /api/action-requests/cast/`, WebSocket, `ActionPanel` UI | ✅ wired | `world/scenes/cast_services.py:request_technique_cast`; `frontend/src/scenes/actionQueries.ts:castTechnique` |
| Check resolution — anima, soulfray, mishap, corruption, environment | ✅ wired | `world/magic/services/techniques.py:use_technique` |
| Effects / outcome — conditions, combat damage, thread pulls, mage scars | ✅ wired | `world/combat/services/`; `world/magic/services/` |
| Pose / narration into the scene | ✅ wired | `world/scenes/cast_services.py:create_cast_outcome_pose` → `world/magic/narration.py` |
| Logging — `SceneActionRequest` + `Interaction` + power ledger | ✅ wired | `world/scenes/action_models.py`; `cast_services.py:persist_power_ledger` |
| Resonance / progression feedback | ✅ by design | earned from RP perception (endorsements), **not** from casting — see "By design" below |
| Distinctions grant/shape resonance (standing + potency) | ✅ built | `#1834` — `DistinctionResonanceGrant` + `reconcile_distinction_resonance_grants`; see `magic-build-history.md` |
| **A real character actually being able to cast** | ✅ wired | `#1306` — shared template + per-character check; see below |
| **A player being able to find out what a technique does** | ✅ built | `#2898` — one derived `effect_summary` block (plain-words line + structured effects) on all four surfaces + telnet; see below. `#3682` folded in the fifth payload family (treatments — a treatment-only technique used to report no effect at all) and made capability grants read as standing possession ("Knowing it grants X", ADR-0248) rather than as something the cast does |
| **A player being able to find out which forms of it they can work** | ✅ built | `#2901` — `available_technique_forms`: base + each unlocked variant + one step ahead, on the sheet and the cast list; see below |

The backend cast→pose→log→outcome loop is fully wired and resolves end-to-end (verified
by tracing + a throwaway smoke test). The remaining frontier is **assembly, content, and
integration**, not engine mechanics.

## What's left (the real gaps)

Ordered by priority. These are the gaps between "the engine works" and "a player can do
magic." Each is a filed issue — work these, not micro-hardening tickets.

0. **✅ #3712 — DONE (2026-09-08): the path half of the CG menu became authorable.**
   `PathGiftGrant` had no admin registration at all, so `get_technique_options`' path pool
   (76 authored rows) was fixture-loaded and uneditable while its tradition-side sibling
   had both an inline and a standalone page. Both now exist. `AuraPowerConfig` and
   `CapabilityPowerConfig` were likewise unregistered while the required-content dashboard
   reported their missing rows, so staff were told to create a row through a page that did
   not exist; both are now singleton-guarded admin pages. The `path-gift-starter-pools`
   sentinel (ADR-0282) reports each `(path, gift)` pair a tradition makes pickable with no
   path pool behind it, 8 pairs at the time. Since #4545 a pool counts only techniques a new
   character can take (`cg_catalog.cg_takeable_techniques`), and a `cg-gift-pools-takeable`
   row lists each (tradition, path, gift) combination character creation hides for want of
   one; the 2026-10-21 production dump had no technique with a cast template, so it hid
   every gift while the old row read complete. Two stale-cache holes closed alongside: a dispel
   row edited on its own changelist, and a condition delivery-channel edit that changes
   what every technique applying it is worth.
   **#4555 (2026-10-21): a technique is offered only on its Paths.** Character creation's
   pool and gift list, Academy training eligibility and `grant_path_magic` now read
   `PathGiftGrant.starter_techniques` as the techniques for that Path and Gift and
   `TraditionGiftGrant.special_techniques` as a restriction to the listing Traditions; a cast
   adds the skill of a Path the technique belongs to; a `tradition-techniques-on-a-path`
   Required content row lists a Tradition technique no Path holds (ADR-4555-A).

1. **✅ #1306 — RESOLVED: every technique minted through the builder is castable**
   (`priority:now` → done).
   `create_technique` defaults `action_template` to the shared **Technique Cast**
   `ActionTemplate` seeded by `seeds_cast.ensure_technique_cast_content()`.
   **Corrected 2026-09-07 (#3682):** this covers techniques the builder mints, and the
   authored catalog does not come in that way — content fixtures write rows directly, so
   all 306 techniques in the live database carry a null `action_template` and are refused
   by `request_technique_cast` while `get_technique_options` still offers them as valid CG
   picks. `technique_is_not_castable_standalone` and the `TechniqueAdmin` "No cast
   template" filter now make that visible to staff; deciding which of them are meant to be
   active casts (as opposed to standing-capability techniques) and wiring those rows is
   content work, tracked on #3713. **Ruled 2026-09-08 (#3682 ruling 2):** there is no
   standing-only category — every technique must be activatable, because it must be
   amplifiable by pulling threads, must cost anima, and must be able to decide a
   life-or-death moment. A passive is the latent weaker tier of the *same* technique
   (`TechniqueCapabilityGrant` is the floor, an applied condition carrying a
   `ConditionCapabilityEffect` is the activated tier, scaled by `compute_severity` off the
   `effective_power` a pull raises). So all 306 need a template and no staff judgement
   picks which — that is #3713's bulk action, not a decision. Cast
   resolution rolls the **caster's own per-character magic check**
   (`ensure_character_magic_check_type` / `get_character_cast_check` in
   `seeds_checks.py` / `services/anima.py`); the same check is used by the anima ritual
   (wired via `provision_player_anima_ritual`). A graded **"Magic: Technique Cast"**
   `ConsequencePool` routes outcomes. No schema migration required.
   **Follow-ups from #1306:** the targeting model gaps (listed below) were closed by
   #1321; the technique-designer consequence-pool catalog was closed by #1320 (see
   below).

2. **✅ #1321 — RESOLVED: targeting model + behavior-consent + AoE + standalone condition
   application** (`priority:now` → done). Closed the four gaps deferred from #1306:
   - **Targeting validity enforcement:** `Technique.target_type` (new field,
     `ActionTargetType` choices: SELF/SINGLE/AREA/FILTERED_GROUP, default SINGLE) stores
     per-technique cardinality. `validate_cast_target` (`world/magic/services/targeting.py`)
     enforces cardinality and relationship rules, raising `InvalidCastTarget` on violation.
   - **Behavior-consent routing:** `ConditionCategory.alters_behavior` (new boolean, default
     False) marks behavior-altering categories (compulsion, charm, fear). The consent gate
     is now **behavior-based**: hostile → combat; benign + behavior-altering → PENDING
     consent; benign + capability/stat → resolves immediately (including on other PCs).
     `cast_requires_consent` in `targeting.py` implements this predicate.
     **Corrected 2026-09-07 (#3682, ADR-0281):** the hostile/benign half of that routing
     was wrong for the whole authored Defense line. `is_technique_hostile` read
     `EffectType.base_power`, which Defense carries at 10, so all 54 Defense techniques
     routed as attacks and a self-shield could not name its own caster. Hostility now reads
     the payload rows only.
   - **AoE expansion:** standalone AREA auto-expands via `resolve_targets` to all eligible
     personas in the scene (relationship-derived: SELF→caster only, ALLY/ENEMY→all others).
     Combat AoE uses the new `CombatRoundActionTarget` join table (`world/combat/models.py`);
     AREA auto-expands to all active opponents, FILTERED_GROUP uses the stored/supplied subset.
   - **Frontend target picker:** the existing `TargetPicker.tsx` (multi-select capable) is now
     driven by a technique's `target_spec`. `_target_spec_for_technique_action` in
     `actions/player_interface.py` builds the spec from `Technique.target_type` and
     `derive_target_relationship`. The `TargetSpec`/`TargetType`/`TargetKind`/`TargetFilters`
     model in `actions/` was **reused** (already existed and wired) — not reinvented.
   - **Standalone condition application:** `apply_technique_conditions`
     (`world/magic/services/condition_application.py`) extracted from combat's
     `_apply_conditions`. Standalone casts now apply technique-authored conditions to
     resolved targets. `AppliedConditionResult` still lives in `world/combat/types.py` as a
     known follow-up to relocate.

   **Still deferred (follow-ups):**
   - Resonance → aspect mapping (all magic checks still use the Arcana aspect).
   - Relocate `AppliedConditionResult` out of `world/combat/types.py`.
   - Standalone hostile/behavior-altering FILTERED_GROUP multi-consent state machine.
3. **✅ #2898 — RESOLVED: techniques now show what they do** (`level:1` → done). Four
   technique payloads had grown independently and disagreed, and every one of them stopped
   at the `Technique` row — so the fields players could see (`level`, `intensity`, `control`,
   `anima_cost`, `reach`, `target_type`) were the ones identical across all 272 authored
   techniques, and the four sibling tables that actually differentiate them (793 capability
   grants, 168 applied conditions, 62 damage profiles, 27 removals) reached nobody.
   - **One derivation, composed not reinvented:** `summarize_technique_effects`
     (`world/magic/services/technique_effects.py`) reads the four payload tables and calls
     the two derivations that already existed — `is_technique_hostile` and
     `derive_target_relationship`. The issue proposed building the relationship half; it was
     already `[BUILT & WIRED]` as the gate `validate_cast_target` runs. No model field added.
   - **One serialized shape:** `TechniqueEffectSummarySerializer` embedded as
     `effect_summary` by all four surfaces. CG — thinnest of the four at the moment the pick
     is least reversible — gains cost, reach, targeting and hostility in one field; the
     in-scene cast list gains the `description` it never had.
   - **Plain words, both faces:** the `summary` line ("Cast on an ally, anywhere in the room,
     in the physical arena. Costs 5 anima. Applies Guarded.") is authored server-side, so the
     web client and telnet render the identical sentence and clients never re-derive it.
   - **Telnet parity for the play verbs:** bare `cast` is now the cast list (it raised a usage
     error before — telnet had no way to learn what a technique does at all), and
     `sheet/magic` prints the same line. Both share `castable_techniques_for_sheet` with the
     web endpoint.
   - **Everything caches onto the row:** `Technique.cached_effect_summary`, plus three
     derivations that were issuing a query per call (`is_technique_hostile` ×3, called up to
     six times per cast path; `derive_target_relationship` ×2; `is_lock_applying` ×1) rewritten
     to read the cached payload lists.
   - **Authoring gaps reported, not guessed at:** `technique_relationship_is_ambiguous` (the
     #2764 self-teleport-that-Flanks-an-enemy shape) and `technique_is_underspecified`, both
     on `TechniqueAdmin`. `derive_target_relationship`'s live answers are unchanged.

   **Still open (content, not engine):** the 86 techniques with no derivable relationship
   need conditions authored in the lore repo. Display now makes the gap visible — that was
   the point — but the authoring itself is out of scope per the issue.
4. **✅ #2901 — RESOLVED: surfaces now show which forms a caster can work** (spawned by
   #2898). #2898's block describes the *authored* technique, which is right for CG and the
   magic API but not for the two per-character surfaces: a `TechniqueVariant` does not
   replace a technique, it makes an alternate version available. Nothing anywhere enumerated
   a caster's forms — `Technique.cached_variants` had no display caller — so a player could
   pass `base` or `variant=<resonance>` to `cast` without any surface having told them those
   forms existed.
   - **A list, not one resolved answer:** `available_technique_forms`
     (`world/magic/services/technique_forms.py`) returns the base form, each unlocked
     variant (at most one per GIFT-thread resonance, since `matching_variant` shadows lower
     tiers), and the next locked form per resonance as a visible goal. The signature rides
     beside it as a delta, never as a sibling row (ADR-0072).
   - **One resolver, reused not reinvented:** every entry comes from calling
     `resolve_specialized_variant`; the `is_default` marker comes from the
     `preferred_resonance=None` call specifically, because that is the path carrying the
     alt-self resonance override.
   - **The caching concern in the issue dissolved:** a resolved form takes no caster input,
     so each form's summary caches on its `TechniqueVariant` row exactly as the base one
     caches on the `Technique` row. Sheet 37 → 39 queries, telnet cast listing 5 → 7, all
     fixed rather than per-technique.
   - **A silent correctness bug closed on the way:** `_ResolvedTechnique` exposed
     `damage_profiles` while every payload reader reads `cached_damage_profiles`, so
     `__getattr__` forwarded those to the parent and a variant with its own payload
     summarised as the base form under the variant's name.
   - **Web parity:** `preferred_resonance_id` on the cast request — telnet has had
     `variant=<resonance>` since #1619, and the web had no counterpart at all.
5. **🟠 #1307 — seed produces no playable character or scene** (`priority:next`). The
   "Big Button" (`world/seeds/database.py:seed_dev_database`, #651) seeds rules content
   only — 0 CharacterSheets / Personas / Scenes. Needs a playable-slice path (demo
   character via `create_character_with_sheet` + CG finalize, placed in a scene). Child
   of epic #1220.
6. **🟡 #1308 — the web cast loop is never tested live** (`priority:next`). Frontend cast
   tests mock `castTechnique`; backend tested only at service level. No test drives
   `POST /api/action-requests/cast/` against a seeded + CG'd character. Add one as the
   regression guard. Cross-refs #617.
7. **🟢 #1309 — frictionless scene start** (`priority:later`). Casting needs an active
   scene; a player should be able to start/auto-join one without staff setup (the
   "implicit scene start" intent).

## By design — do not re-file these as gaps

A code read flags these as "missing"; they are intentional. Verify against the design
before treating any as a bug:

- **Casting does not grant resonance.** Resonance is earned from *perception* — pose
  endorsements, scene entry, residence/outfit trickle (the four gain surfaces in Spec C,
  `docs/architecture/resonance-gain.md`; since #5308 the two trickles pile up as
  `TrickleAccrual` rows and an anima ritual turns them into resonance). You earn it when
  others endorse your dramatic cast pose, not mechanically from the cast.
- **Non-combat casts deal no damage.** A hostile cast at a PC routes into combat
  (`seed_or_feed_encounter_from_cast`), where damage applies. Non-combat = benign / self
  / room. Consistent with the non-lethal-PvP invariant.
- **Non-combat thread pulls are passive-only** (VITAL_BONUS inactive outside combat) —
  Resonance Spec §7.4.

## Design resolution — #1306 (castability, RESOLVED)

**Was:** Is castability (the `action_template`) auto-provisioned per technique, shared
per effect-type/style, or authored staff content?

**Resolved:** A single shared **Technique Cast** `ActionTemplate` is seeded by
`seeds_cast.ensure_technique_cast_content()`. `create_technique` defaults `action_template`
to it; the per-technique FK remains as a staff-only override. Cast resolution rolls the
**caster's own per-character magic check** (synthesized from their stat + skill via
`ensure_character_magic_check_type`), not a technique-level authored check. Outcomes route
through a graded **"Magic: Technique Cast"** `ConsequencePool`. The anima ritual and
technique casts always share the same personal check (`provision_player_anima_ritual`
in `services/anima.py`).

A player can perform the anima ritual itself (#4451, reshaped by #5280): it is never done alone, so
the web dispatch, telnet `ritual anima` and the ritual's own name all refuse and ask
her to name someone else; the ritual is asked of a partner through `start_partner_ritual`, once per
scene, in the scene the character stands in (see "The anima ritual becomes a scene with a partner"
below).

Deferred to follow-up issues: optional resonance→aspect mapping for the per-character
check (today all magic checks use the Arcana aspect).

The targeting model gaps (validity enforcement, AoE, frontend picker, standalone condition
application) were resolved in #1321 — see the #1321 entry above. The consequence-pool
catalog (player/CG selects a flavor from a curated catalog built on
`ConsequencePool.parent`, instead of the single shared pool) was resolved in #1320 — see
`docs/systems/magic.md` and `src/world/magic/CLAUDE.md` for detail.

## Telnet technique-authoring workbench (#1496 — BUILT, staff/GM-only)

Closes the `#1328` telnet-coverage gap for technique authoring. Surfaces built:

- **`TechniqueDraft`** + three payload child models (`TechniqueDraftCapabilityGrant`,
  `TechniqueDraftDamageProfile`, `TechniqueDraftAppliedCondition`) in
  `src/world/magic/models/technique_draft.py`. Payload children inherit abstract bases
  (`AbstractCapabilityGrant` / `AbstractDamageProfile` / `AbstractAppliedCondition` in
  `models/techniques.py`) shared with the committed `Technique*` rows.
- **Draft services** (`services/technique_draft.py`): `get_or_start_draft`, `discard_draft`,
  `set_draft_fields`, restriction + payload add/remove helpers, `draft_to_design`.
- **`validate_design_for_character`** (`services/technique_builder.py`) — gift-ownership
  gate extracted from the serializer; now the single gate for both telnet and web.
- **`AuthorTechniqueAction`** (key `"author_technique"`, category `"magic"`,
  `actions/definitions/technique_authoring.py`) — the single commit seam. Both the web
  `TechniqueViewSet.author` endpoint and `CmdTechnique` converge on `action.run()`.
- **Web convergence** — `TechniqueViewSet.author` now dispatches `AuthorTechniqueAction.run()`
  for the player path (HTTP contract preserved: 201/400/403). Staff-without-character retains
  a direct `author_staff_technique()` fallback.
- **`CmdTechnique`** (`commands/technique.py`, key `"technique"`, `cmd:perm(Builder)`) —
  staff/GM-only telnet workbench with subcommands:
  `draft show set restrict grant damage condition price author discard`.
  `author` dispatches `AuthorTechniqueAction` with `as_staff=True` (`StaffPolicy`, advisory
  budget, no `CharacterTechnique` binding).

**Deferred `needs-design` follow-up:** when and how ordinary players earn technique authoring
(CG design step, magical-research unlock, or other unlock mechanism — never on-demand).
The `PlayerPolicy` seam and web `author` endpoint are already wired; the player-tier gate
is a permissive `TODO` in `technique_builder.py`.

## Telnet resonance visibility (#2032 — BUILT)

Telnet players could earn and spend `CharacterResonance.balance` (thread pulls, imbuing,
sanctum weaving, entry flourishes, pose endorsements, ...) but had no telnet surface that
ever rendered it. Two read-only faces now expose it, both reading the same
handler/service the web uses — no parallel query pipeline:

- **`sheet/magic`** (`commands/account/sheet_sections.py`) gained a `Resonance:` block —
  every claimed resonance's balance + lifetime earned, from `_build_magic_resonances`
  (`world/character_sheets/serializers.py`), which reads `character.resonances`
  (`CharacterResonanceHandler`, the cached identity-mapped accessor). Folded into
  `MagicSection.resonances`, shared by telnet and the web Magic tab.
- **`resonance`** (`commands/resonance.py`, new command key) — bare `resonance` reuses the
  same builder for the balance listing; `resonance history [<name>]` shows the caller's
  last 10 `ResonanceGrant` rows (newest first, source label), optionally narrowed to one
  claimed resonance, via `resonance_grant_history_for_sheet`
  (`world/magic/services/gain.py`) — mirrors `ResonanceGrantViewSet`'s ordering.

## Ritual of the Durance (#1352 — BUILT)

The within-tier class-level advancement ceremony is complete. Magic's contribution:

- **`RitualLiturgy`** (`models/liturgy.py`) — OneToOne on `Ritual`; `opening_call` TextField
  holds the authored officiant invocation (public, non-spoiler).
- **`RitualOfTheDuranceFactory`** (`factories.py`) — seeds the `Ritual` row (SERVICE /
  INDUCTION, `service_function_path` → `world.progression.services.advancement.advance_class_level_via_session`,
  `min_participants=2`) and its companion `RitualLiturgy` via a `@post_generation` hook.
- `AudereMajoraCrossing` now inherits `AbstractClassLevelAdvancement` (from
  `world.progression.models.advancement`), sharing shape with `ClassLevelAdvancement`.
  `cross_threshold` calls `apply_class_level_advance` (the shared spine) instead of
  inlining a level write.

**Telnet Durance (#1700) — BUILT.** Telnet drivability of the Ritual of the Durance is now
complete. Both a live-officiant ceremony (`ritual draft` → inductee `ritual join` → `ritual fire`)
and a site-convened session (`durance convene` → inductee `ritual join`, auto-fires) are
supported. See `docs/roadmap/character-progression.md` and ADR-0065 for the full build record.

## CG magic acquisition — Path → Tradition → Gift → Technique (#2426 — BUILT)

CG no longer lets a player author a personal cantrip; it links a character to
staff-authored catalog content instead:

- **Tradition is a real mechanical layer.** Every character has exactly one
  Tradition, including the self-taught `Unbound` tradition (no NULL-tradition
  special-casing). `TraditionGiftGrant` (tradition × gift → signature technique
  extras) drives the CG gift list; there is no selection gate, every tradition a
  Beginning's slate offers is selectable outright, and `BeginningTradition.state`
  (#3675, was `required_distinction`) decides which drawback the pick carries into
  the draft for free (`TraditionStateLine`, see `docs/systems/character_creation.md`).
- **`PathGiftGrant.starter_techniques`** (unchanged schema) is reinterpreted as
  the CG *availability pool*, not an automatic grant — the same rows
  `grant_path_magic` mints from at the level-3 Durance semi-crossing (ADR-0063,
  unaffected). CG picks 1 + `Tradition Training` distinction rank from the
  pool, less the techniques other traditions keep for their own members (#4555).
- **The Anima Check replaces a silent default.** CG's Gift stage now closes
  with an explicit stat + skill pick (`provision_player_anima_ritual` gained
  parameters instead of hardcoding Willpower + highest skill) and a ritual
  name — see the glossary entry (not "Signature"; ADR-0072 owns that term).
- **Removed:** `Cantrip` model + full stack, CG facet selection, custom gift
  name/description, and the CG Outcome Flavor pick.
- Rationale + rejected alternative: ADR-0136. Stage/flow detail:
  `docs/roadmap/character-creation.md`, `docs/systems/character_creation.md`,
  `docs/systems/magic.md`.

## Personalizing magic from the start (#4099, ADR-4099, BUILT)

A character now personalizes a chosen technique while building it in CG, not only after
reaching thread level 3 in play. Built:

- **Hold fields.** `CharacterTechnique` (the hold) gained `custom_name`,
  `custom_description`, `price` (FK `Restriction`, `kind=PRICE`), and `early_form` (FK
  `TechniqueVariant`). All four live on the hold, never on the shared catalog `Technique`.
- **Three priced catalogs.** A signature flourish (`SignatureMotifBonus`), an early
  specialized form (`TechniqueVariant`), and a price (`Restriction`, `kind=PRICE`) are each
  offered in creation only when staff set that row's `creation_point_cost`; a blank cost
  means the option is not offered.
- **The creation panel.** The Gift stage's "make it yours" panel (`PersonalizationPanel`)
  lets a player name and describe a chosen technique for free, and spend CG points on a
  flourish, form and/or price, backed by `GET drafts/{id}/personalization-options/`.
- **Price at cast.** A chosen price's `power_bonus` is added straight to every cast's power
  (`price_power_term`), and its `cast_narration` joins the cast line.
- **Gradual flourishes.** The old hard level-3 floor on signing is gone;
  `SignatureMotifBonus.min_crossing_level` is the only gate, and creation can weave a
  TECHNIQUE thread up to `CREATION_PERSONALIZATION_MAX_LEVEL` (10, a new character's level cap in stored thread
  levels, #4585/#5091) so an early flourish is
  reachable without skipping a crossing.
- **Early forms.** An `early_form` bought in creation applies before the gift thread
  reaches it, for its buyer only, when the cast's resolved resonance matches the form's
  own authored resonance (checked after ordinary variant matching, not before falling
  back — a hold carries no resonance of its own), never for a role-granted hold.
- Rationale + rejected alternatives: ADR-4099 (supersedes in part ADR-0136's "mechanical
  personalization starts at level 3" clause). Full model/service/endpoint detail:
  `docs/systems/magic.md`'s "Technique personalization" section,
  `docs/systems/character_creation.md`'s Magic API section.

## Choosing the imagery your magic is tied to (#5021, BUILT 2026-11-08)

Every reader of a character's facets was built (facet-gated flourishes, the facet route
for ritual offerings, the cast narration fallback, the sheet's Motif) and nothing wrote
them, so no facet-gated flourish could ever qualify. Built:

- **In play, any time, free.** `motif bindfacet <facet>=<resonance>` /
  `motif unbindfacet`, the Spellbook's Facets panel, and `bind-facet/` / `unbind-facet/`
  on `/api/magic/motif-styles/`: up to five facets on each claimed resonance, one facet
  on as many resonances as the player likes.
- **Signed flourishes keep their facet.** Removing the last tie of a facet a signed
  flourish needs is refused until the flourish is cleared.
- **Staff fix them** in the facet inline on the Motif Resonance admin page.
- **In creation (optional).** The Gift stage's Motif takes up to five facets for the gift
  resonance; a creation-costed flourish gated on a picked facet is then offered in "make
  it yours", and finalize ties the facets before signing the flourish.
- Detail: `docs/systems/magic.md` "Player-facing facet binding (#5021)".

## Where you stand matters: a gift's substance (#5018, ADR-5018, BUILT 2026-11-09; reshaped by #5125)

What #5018 built, in one PR (seven parts). Parts 1 and 2 were reshaped by #5125 (ADR-5125,
next section): a substance is now one shared `Substance` row, not a per-gift mapping, and a
call-up is priced as one step for one shared anima cost with no resonance charge.

1. **Stronger and weaker.** Every cast of a gift by a caster with a GIFT thread on it gains or
   loses power from the substance in the place, scaled by her thread level ("Shadow around
   you", then one line per source and "Shadow adds").
2. **Her cast calls it up.** Where the substance is missing, the cast calls it up (now only
   to Trace): its anima rides the cast's own cost before control, so social-scene casts usually
   stay free. The room changes for everyone while she stays. Never refused for anima.
3. **No technique.** "Your gift" on the scene panel, Call up beside Dig deep in a fight
   (once a round, not her action), telnet `callup`.
4. **Other surroundings.** A DESIGN restriction may need a reading its gift does not make;
   unmet, a heavy named roll penalty, never a refusal.
5. **Walls keep weather's darkness out.** A walled room drops weather-sourced lighting.
6. **The GM says yes.** `stage present <substance>` / the Stage tab's "Present here" marks
   it for the scene; the scene ending clears it.
7. **A roof keeps out the rain, not the cellar's own water.** Enclosure drops only the
   weather's wet and wind; a room's own rows count.

Remains for staff: authoring substances on real gifts, dark weather types and styles, and
tuning the numbers on Resonance environment settings.

## Substances and Primum (#5125, ADR-5125, BUILT 2026-11-17)

Design record #5121. Built in one PR, in this order:

1. **One shared list.** `Substance`, `SubstanceRelation` (related or opposed, one row per pair,
   never chained) and `Gift.substance` (major gifts only, a database check) replace
   the old per-gift mapping. Migration 0461 carried every old row into the new list (merging
   gifts that described the same substance, printing every discarded per-gift value so staff
   can re-author the relations) and 0462 dropped the old table and four config columns
   (ADR-0237: restructure; the per-gift full-strength number, weakened-by reading and arrival
   line are a deliberate discard).
2. **Primum in places and creatures.** `PlacePrimum` (a lair: capacity, stock, slow refill,
   finite), `CreaturePrimum`, and staff-edited `PrimumStep`, `SubstancePowerStep` rows. A room
   whose ordinary condition leans a substance's way reads Trace; lairs and creatures hold the
   large amounts. A cast draws on the place and her equipped items, never on creatures: a
   creature's Primum matters only for sensing and harvesting. Matching gives full benefit, related `substance_related_share_pct`, opposed
   works against the caster; sources add with a taper up to `substance_power_cap`; the bonus
   still grows with her GIFT thread.
3. **Perceiving it.** `EffectType.REVEAL_PRIMUM` (a perception technique's check): a plain
   success names the strongest substance, a good success all of them, until she leaves. A
   substance she has not perceived reads "Something here works against your ice" or "Something
   here strengthens your ice". Her own gift's substance is always perceived. The room panel
   lists "You sense" and `look` ends with the sentence.
4. **Calling up.** One step, one shared anima cost, one generated room line.
5. **Harvesting.** Anyone with the new harvest skill rolls a check; a matching GIFT thread
   adds `harvest_thread_bonus x thread_level_multiplier`; every attempt, good roll or bad, costs
   `harvest_ap_cost` action points and `harvest_fatigue_cost` physical fatigue. Only perceived Primum in a lair or on
   a slain creature is offered, a slain creature once in total, a lair slowly or never. Web
   Harvest buttons and telnet `extract fire` / `extract fire from elemental`.
6. **Items and crafting.** Harvested Primum is an item; an optional recipe ingredient makes the
   crafted piece carry the substance ("Carries fire", public); only equipped gear counts toward
   a cast (see `docs/systems/items.md` "Crafting with Primum").
7. **Every technique of a major gift always carries its substance's property**, derived on read.

`[ABSENT]` by decision (not alpha): spending Primum to raise a Gift thread or to call up a
substance in a cast. Remains for staff: authoring the substances, relations, lairs, creature
Primum, the harvest check, skill and outcome rows, and tuning the starter steps and curve.
Detail: `docs/systems/magic.md` "Substances and Primum"; journeys in `docs/testing/journeys.md`.

## Tradition sponsorship, Academy training, and the in-play loop (#2428/#2440/#2441/#2442 — BUILT)

The in-play training loop #2426's roadmap entries deferred as a follow-up is now real —
a character no longer needs to complete their starter Gift pool at CG; they finish it at
Shroudwatch Academy, or via a trainer of their own Tradition, in play.

**Content-dependency caveat.** The mechanical substrate below (Hares, obligations,
`OfferKind.TRAIN`/`SETTLE_OBLIGATION`, the availability gate) is dev-complete and
fully wired, but the *NPCRole* content that fronts it is not: real Academy trainer
curricula (which techniques, which tradition, how many, room prose) are lore-repo
authored content, not this cluster's job. What ships in this repo is a
dev-minimum seed — the Academy Registrar (settles the entrance debt) and one
ungated generalist trainer (teaches the shared starter pool) — just enough that a
freshly seeded DB can complete the loop end to end without lore-repo content
present. Staff/content replace or extend these seeded rows freely; the seeds
never overwrite a staff-adjusted row.

- **Golden Hares** (`currency.FavorTokenDetails`, ADR-0137) — a physical, tradeable,
  org-issued deed token (one Hare = one deed done for the issuing org), NOT an abstract
  ledger. Minted via `mint_favor_token` (GM adjudication `award_type="favor_token"`,
  #2428 Task 4), surrendered via `redeem_favor_token` (issuer-match enforced — a Hare
  only ever redeems to the org that issued it).
- **Academy sponsorship is a real spend, not a waiver.** `societies.OrganizationObligation`
  gives every CG-finalized character a Shroudwatch Academy entrance record: `OWED` one
  Hare for the Unbound (no Tradition to cover it), `SETTLED_BY_SPONSOR` for everyone else
  (the sponsor literally spent a Hare on the Prospect's behalf, lore-recorded at CG time).
  `settle_obligation` clears an `OWED` row by redeeming a real Hare later in play,
  reached through the Academy Registrar's `OfferKind.SETTLE_OBLIGATION` offer
  (`run_settle_obligation_offer`) — an ungated, always-visible NPCRole offer, since
  a Prospect who owes the debt must always be able to find someone to pay it to.
- **Academy training (#2440)** — `npc_services.OfferKind.TRAIN` teaches a technique for
  AP + coin + 1 Golden Hare, gated on the obligation above being settled and on the
  learner's own Path's list for the gift, a Tradition-kept technique only for an active
  member of a listing Tradition (#4555; `magic.services.cg_catalog.get_technique_options`). Delegates acquisition to the same
  `charge_and_learn` core player-to-player `TechniqueTeachingOffer` accepts use — one
  seam, two front doors. A learner short of the offer's coin is refused with the price and
  her balance before anything is charged (`TrainingFundsInsufficient`, #4523). The trainer is never
  present at a session, so the offer's staff-set `TrainOfferDetails.instruction_bonus` is copied onto
  the `TechniqueProgress` meter it opens and added to every session's roll as an "Academy
  instruction" modifier, and the self-study penalty does not apply (#2741, ADR-2741). The learning
  roll also adds the technique's own casting skill, counted once (#2740). **Great Archive self-study** is the same TRAIN shape, gated on a
  quest-completion `Achievement`. It teaches the learner's own (Path × Gift) shared
  starter pool only — it does **not** restore an orphaned tradition's signature
  technique list; recovering a lost tradition's own curriculum is story content, not
  a mechanical unlock this seam provides. A second, ungated generalist trainer seeds
  the same shared-pool techniques without the achievement gate, so a fresh-DB
  Prospect always has ≥1 reachable TRAIN offer even before any quest content exists.
  **Level 2 requires knowing ≥3 techniques of the character's major Gift**
  (`progression.MajorGiftTechniqueRequirement`) — a count, not a completeness bar.
- **Tradition membership lifecycle (#2441)** — `CharacterTradition.left_at` makes
  membership history-preserving (mirrors `OrganizationMembership.left_at`).
  `join_tradition`/`leave_tradition` (`magic.services.tradition_membership`) switch
  membership; joining a tradition through its teaching org's membership-offer accept
  flow auto-sheds the Unbound/Orphaned-Tradition drawback. Learned techniques are never
  revoked on switch — only future signature-list access changes.
- **The Unbound penalty is TIME, not power (#2442).** The "unbound" drawback
  `Distinction` carries a +50% Action Point surcharge on magic-learning activities
  (`magic_learning_ap_cost` `ModifierTarget`) — self-taught mages develop just as
  strong, only slower. Resonance earning and spending are untouched (see ADR-0137 for
  the rejected resonance-halving alternative).
- Rationale + rejected alternatives: ADR-0137. Full model/service detail:
  `docs/systems/magic.md`, `docs/systems/societies.md`, `docs/systems/INDEX.md`
  ("NPC Services", "Currency", "Societies" entries).

## CG starter catalog rides the content pipeline, not a seed function (#2474 — BUILT, 2026-07-18)

The CG starter Gift/Technique catalog (`Resonance`/`Gift`/`Technique`/`PathGiftGrant`/
`TraditionGiftGrant`, including the "Unbound" `Tradition` itself) is now real
lore-repo content, not synthetic in-repo seed data — closing the gap left when
#2426 built the catalog *shape* but authored it via a temporary in-repo
`seed_starter_gift_catalog()` seed function.

- All five models gained `NaturalKeyMixin` and joined `CONTENT_MODELS`
  (`core_management/content_export.py`); `Technique`'s natural key is
  `(gift, name)` (`unique_technique_gift_name` — `name` alone collides across
  gifts, e.g. lore reuse or a player-crafted technique).
- `core_management.content_fixtures.load_entries` gained M2M natural-key
  resolution, stale-field tolerance (a fixture field naming a removed/renamed
  model field is skipped with a warning, not a crash), and fixed-point deferred
  retry (multiple passes until a pass makes no further progress — a multi-hop
  chain like a `Technique` naming a still-deferred `Gift` needs more than one
  retry).
- `world.seeds.database.seed_dev_database()` now sequences: resolve
  `CONTENT_REPO_PATH` (raise `ContentError` immediately if unset/missing) →
  seed config prerequisites the content fixtures FK by natural key
  (`ensure_technique_cast_content()`, since lore-repo `Technique` rows FK the
  shared "Technique Cast" `ActionTemplate`) → `load_world_content()` → the
  `CLUSTER_SEEDERS` loop. No cluster seeder authors catalog content anymore.
- The retired `seed_starter_gift_catalog()` + `StarterGiftCatalogResult` are
  replaced, for tests, by `MagicContent.create_starter_gift_catalog()`
  (`world/seeds/game_content/magic.py`, a synthetic factory-built stand-in) and
  an enriched `stub_content_root()` (`world/seeds/tests/content_stub.py`).
  NPC trainer seeds (`world/npc_services/seeds.py`) resolve their starter
  technique picks as gift-scoped `(gift_name, technique_name)` pairs and raise
  `ContentError` when none resolve — a missing/stale catalog fails loudly
  rather than silently seeding an empty trainer.
- Rationale + rejected alternative (a synthetic sample-content fallback baked
  into arxii seeds): ADR-0142. Full detail: `docs/systems/magic.md`'s "CG
  Starter Gift/Technique Catalog" + "Content-vs-config boundary" sections,
  `docs/systems/INDEX.md`'s "Content-repo load" entry.

---

## Dev-seed content stand-ins retired (#2967/#2972/#2973 — BUILT, 2026-08-07)

ADR-0142 said the `CLUSTER_SEEDERS` loop "now only seeds non-lore config/lookup
tables and never authors catalog content again," naming `ensure_portal_travel_content()`'s
Gift/Technique as the "one known remnant." It was not one remnant: #2972 found ten
seeders in `world/seeds/game_content/magic.py` still authoring content-repo-owned
rows, every one keyed to a `Resonance` the seeder itself invented — each one made a
contentless feature look shipped. #2967 obliterated the portal-travel "Mirrorwalking"
placeholder first (the fix that stopped seeders from inventing `Resonance` rows at
all). #2973 then closed out the remaining eight, six of which needed an actual code
change to strip (lore fixture, the #2451 grid bundle, or a test fixture — no
non-test consumer):

- 3 demo `ObjectDB` rooms + `LocationValueModifier` resonance tags + the "Hallowed
  Rejection" `ConditionTemplate` (`_seed_resonance_environment_rooms`) — rooms ride
  the #2451 grid bundle; the condition template rides an ordinary lore fixture.
- The "Hallowed Threshold" `Story`/Chapter/Episodes/Beats
  (`_seed_hallowed_threshold_story`) — test fixture only, no production destination.
- The "Social Arts" `Gift` + 6 `Technique`s + 6 `ActionEnhancement`s + variants
  (`MagicContent.create_all()`) — lore fixture; `MagicContent` survives as a
  test-fixture builder. `actions.ActionEnhancement` and `magic.TechniqueVariant`
  joined `CONTENT_MODELS` in #3034 — that lore-fixture destination was aspirational
  until then (neither model carried a natural key or a registry entry, so the six
  enhancements + their variants had no way to actually be authored); the lore repo
  can now ship them (ArxII-lore#69).
- 2 Corruption `ConditionTemplate`s + 12 `MagicalAlterationTemplate` twists
  (`author_reference_corruption_content()`) — lore fixture; the factory survives as
  a test-fixture builder for `test_reference_corruption_content.py`.
  `magic.MagicalAlterationTemplate` joined `CONTENT_MODELS` in #3034 (NK
  `["condition_template"]`; player-authored rows excluded via `EXPORT_FILTERS`).
- 5 hallowed reaction `ConditionTemplate`s + the achievement bridge
  (`_seed_hallowed_reaction_conditions`/`_seed_hallowed_achievement_bridge`) —
  lore fixture; KEEP-side consequence pools resolve them by name via
  `authored_or_sample()`.
- The touchstone `ItemTemplate` + 3 reagent templates (`ensure_touchstone_content()`)
  — lore fixture; KEEP-side `ensure_sanctification_requirements` degrades loudly
  (logged skip) when a reagent is absent instead of inventing one.

The remaining two were **already clean going into this branch**, not stripped by
it — #2973 verified them against code, found no lazy-create/invention path left,
and added the regression coverage that had never existed for either:

- (#4681 affinity refactor, slice 1: affinity identity is now the `Affinity` row everywhere.
  `CharacterAura` percentages are `CharacterAuraShare` rows, the Fall/Redemption multipliers live
  on `AffinityInteraction.conversion_multiplier`/`conversion_type`, the corruption coefficients on
  `Affinity.corruption_coefficient`, and the `AffinityType` enum is gone.)
- 4 `CompromiseActType` + 6 `ResonanceConversion` fall-redemption examples
  (`wire_fall_redemption_content()`) — `authored_or_sample()`-gated since #2972,
  before this SDD series started. No production code changed; #2973 added
  strip-absence tests (`test_no_fall_redemption_example_rows_authored`). Lore
  authoring for these rows is still owed — the gate just means an absent row
  degrades loudly instead of getting invented.
- The "Devotion" `RelationshipType` (`seed_relationship_track_thread_unlock()`; the catalogue model was renamed from `RelationshipTrack` in #3957)
  — `authored_or_sample()`-gated since #2698, predating this series; no lazy-create
  path remained by the time #2973 looked. #2973 added strip-absence tests
  (`test_no_devotion_track_authored`) and corrected stale docstring/CLAUDE.md
  wording that still described a "lazy-creates ... canonical track" behavior the
  code no longer had.

`world/magic/seeds_resonance.py` (the `authored_or_sample`-based seam every stripped
caller used to look content up instead of inventing it) survives — KEEP-side
dependents remain (`seed_thread_pull_catalog`, `ensure_relationship_pull_content`,
`world/seeds/game_content/combos.py`). The `integration_tests.game_content.magic`
compatibility facade (roadmap task 3.2, #1220) is deleted now that its last
strip-side re-export is gone; every caller imports `world.seeds.game_content.magic`
directly. `seed_magic_dev()` now authors only config; every KEEP-side lookup of
authored content goes through `authored_or_sample()` (ADR-0168). Rationale + full
per-item destination table: issue #2973. Doc detail: `docs/systems/magic.md`'s
"Per-caster technique forms" section (the stripped `MagicContent.create_all()`
Gift/Technique/variant catalog) and "Portal travel" section (the stripped cascade
rooms + the defensive `_MIRROR_ANCHOR_ROOM_SPECS` resolution), ADR-0142 (amended).

---

## One-oracle merge — agency oracle reads technique grants (#2504 — BUILT, 2026-07-18)

Before #2504, a technique-granted `CapabilityType` only fed the **availability** oracle
(`get_capability_sources_for_character`, `world.mechanics.services` — "what could grant this
capability"); the **agency** oracle (`get_effective_capability_value`,
`world.conditions.services` — "can this character do X right now," consumed by requirement/gate
checks) did not know techniques existed, so a character whose only path to a capability was a
known technique failed requirement checks a condition or innate baseline would have passed.

- `world.conditions.services._technique_capability_values` folds the best (max) `prerequisite__isnull=True`
  `TechniqueCapabilityGrant` across a character's known techniques
  (`technique__character_grants__character=character_sheet`) into `get_effective_capability_value`,
  reusing `TechniqueCapabilityGrant.calculate_value()`. (`get_all_capability_values` deliberately keeps
  source-enumeration semantics with NO technique folding — the availability oracle's `_get_condition_sources`
  reads it, and folding there duplicated technique grants as phantom condition sources; caught by CI on this PR.)
- Zero per-consumer changes needed: `technique_performable` (`world/magic/services/capability_requirements.py`),
  mission `challenge_options_for_character` (`world/missions/services/challenge_options.py`), positioning +
  battle movement gates, predicates, and vitals awareness all now honor technique grants automatically —
  they already read through the agency oracle.
- Deliberate asymmetry (ratified, unchanged): `TraitCapabilityDerivation` stays availability-oracle-only.
- Rationale for MAX-not-sum + prerequisite-free-only: ADR-0144 (extends ADR-0034 individuation).
- Journey tests: `world/magic/tests/test_technique_requirements.py::TechniqueGrantSatisfiesRequirementTests`,
  `world/missions/tests/test_services_challenge_options.py::ChallengeOptionsTechniqueGrantTests`.
- Docs: `src/world/conditions/AGENT_GLOSSARY.md`'s "Agency oracle" entry; the "Technique - FK to
  ActionTemplate" box in `docs/architecture/action-template-pipeline.md` (was wrongly claiming
  availability-only).
- **Follow-up landed (#2503, 2026-07-19):** the object-state→challenge bridge closing this last
  mile is built — `Application.default_template` + `get_available_actions`'s bare-object second
  source + the `WORLD_INTERACTION` action backend now let a technique-granted capability surface
  a world-interaction affordance on any object carrying the matching `mechanics.ObjectProperty`,
  with no authored `ChallengeInstance` needed. See `docs/roadmap/capabilities-and-challenges.md`'s
  "Phase 8: Bare-Object Affordances & GM Stage-Prop", ADR-0147, and
  `docs/architecture/action-template-pipeline.md`'s "Bare-Object Affordances" section.

---

## Capability magnitude curve — geometric scaling with contextual power (#2708 — BUILT, 2026-07-26)

Before #2708, every capability grant's magnitude was flat or linear with respect to
power: `TechniqueCapabilityGrant.calculate_value()` only ever added
`intensity_multiplier * technique.intensity`, and thread-passive tier-0
`CAPABILITY_GRANT` rows were worth a hardcoded `1` regardless of the granting thread's
level. Neither could cross an ADR-0164 ladder tier boundary at any realistic power
figure — the ladder's own tier anchors (5/~10/25/100) are roughly geometric, so a linear
bump never lands where the ladder's own tiers actually sit.

- **Geometric curve, uncapped, staff-gated by a config singleton**: both grant types now
  compute `round(base * 2 ** (sensitivity * power / power_per_doubling))` via
  `world.magic.services.capability_curve.apply_capability_curve`, driven by a new
  `CapabilityPowerConfig` singleton. No config row = every consumer's pre-#2708 number,
  bit-for-bit — the feature is turned on by staff tuning, not by this code deploying.
- **`intensity_multiplier` retired as additive, repurposed as sensitivity** — a grant
  authored at the default `0` (every pre-#2708 row) stays inert under the curve.
- **`ConditionCapabilityEffect.scales_with_severity` now honoured** by all three
  value-aggregating readers (`get_capability_status`, `get_all_capability_values`,
  `conditions.views._aggregate_capability_effects`) — the column existed since
  migration `conditions/0007` but every reader silently ignored it until this fix.
- **A new ambient-activation predicate** (`_anchor_ambiently_active`,
  `world/magic/services/resonance.py`) gates the contextual-power term feeding the
  technique-grant curve: a free passive contribution requires demonstrable real state
  (actual equipped items, actual current room, actual involved technique/trait), not
  player assertion — deliberately a separate function from the paid-pull predicate
  (`_anchor_in_action`), which does allow assertion because a pull is paid for.
- **`get_effective_capability_value` gained an optional `action_ctx` param** (Task 8;
  keyword-only, `None`-default, ~13 pre-existing call sites unaffected) so a real action
  context can light up more thread kinds' contextual power than the ambient default can.
- Full detail: `docs/systems/conditions.md`'s "Capability magnitude curve" section,
  `docs/systems/magic.md`'s "Capability Magnitude Curve — Technique & Thread Grants"
  section, and `docs/adr/0169-capability-magnitude-curves-geometrically-with-contextual-power.md`.
## Cast observation — style-driven concealment (#2710 — BUILT, 2026-07-26)

"How absolute is subtle casting" (#2700's follow-on, now that style hangs off the
caster's Path — ADR-0167) is resolved: concealment is a per-observer graded contest at
cast time, not a boolean on the Technique or the Interaction.

**Built:**
- `TechniqueStyle.cast_concealment` (`PositiveSmallIntegerField`, default 0) — the
  style's difficulty floor for being noticed while casting. 0 = overt; every existing
  style defaults to 0, so nothing changes until content authors a non-zero value.
- `resolve_cast_audience(*, caster, technique, cast_openly=False) -> CastAudience`
  (`world/magic/services/cast_observation.py`) — per co-located observer, rolls the
  detection `CheckType` against `cast_concealment + compute_obstacle_rating(caster, check_type)` (the caster's full check total as the obstacle, ADR-5093)
  and sorts into full attribution / vague unattributed / effect-only. Fails CLOSED
  (ADR-0033) on attribution when the detection `CheckType` is unauthored.
- `InteractionVisibility.PERCEIVED_ONLY` — the new privacy tier the resolved audience is
  materialised into (writer + `InteractionReceiver` rows + staff + scene GM), sitting
  between `DEFAULT` and the stricter, no-exception `VERY_PRIVATE`.
- `SceneActionRequest.cast_openly` — the caster's one-way waiver, persisted so it
  survives a consent-gated cast's accept-time pose.
- Three enforcement points closed against leaking a concealed cast's identity: the scene
  log (`InteractionQuerySet.visible_to`, needed no change), the request-row REST surface
  (`SceneActionRequestViewSet.get_queryset`, `Exists()`/`OuterRef` filter), and the
  reaction witness gate (`can_view_interaction`, taught the new tier — an earlier spec
  draft wrongly called this predicate unwired; it is wired, see
  `reaction_services.py:132`).
- Full record: ADR-0170. Mechanism detail: `docs/systems/magic.md`'s "Cast observation"
  section.

**Explicitly deferred — not a gap, a scope boundary:**
- **Ships inert until content authors it.** The detection `CheckType`
  (`DETECT_CAST_CHECK_NAME`, `"Perception"`), a `CheckTypeCapabilityModifier` row
  bridging a magic-detection capability into that check, and per-style
  `cast_concealment` values are all lore-repo content — arxii authors no seed data for
  any of them.

---

## Cast concealment hides attribution, not the event (#2734 — BUILT, 2026-08-01)

Extending #2710's seam into combat exposed the model as wrong, not merely incomplete.
Concealment was an *existence* dial: failing detection deleted the cast from your feed.
In combat that meant a concealed working could wound, knock out or drop a PC whose feed
showed an empty round and a health bar that silently moved — vitals are viewer-scoped and
no damage path emits its own message, so the OUTCOME pose is the only channel that tells
a player what happened to them.

It is now an attribution ladder. A concealed cast is a sniper shot: the room may not know
where it came from, but nobody's head explodes in secret.

**Built:**
- `CastAudience.effect_only` — the third tier, reading the effect with no sense that
  magic was involved. `vague` folds the effect line in too, so no tier is told strictly
  less than one that rolled worse, and no observer ever receives two poses.
- `Technique.has_perceptible_effect` (BooleanField, default `True`) — the only case that
  still hides outright: a working that leaves nothing to perceive. Default `True`
  because almost any applied condition produces something a bystander would see.
- `resolve_cast_audience` takes the technique and short-circuits to unconcealed, with no
  query and no roll, for a `SAME`-reach technique. Contact gives the actor away — this,
  not "is it magical", is what makes a sword swing unconcealable.
- `render_unattributed_action_narration` / `render_unattributed_cast_narration` — the
  effect without the actor, carrying none of the attributed line's signature, power or
  synergy suffix clauses (each leaks exactly what the lower tiers withhold).
- Combat wired at `_record_and_broadcast_pc_action`, **not** `broadcast_action_outcome`
  (~15 non-cast callers: flee, encounter-end, clash, challenge, covenant insight); that
  function takes optional `audience` + `unattributed_narration`, and the defaults keep
  every existing caller byte-identical.
- A fourth read surface closed: `ActionOutcomeDetailsView` gated on
  `can_view_encounter_effects` — *encounter*-level, which answers "may you see effects in
  this fight" but not "did you perceive THIS act" — so a concealed cast's effect rows
  were readable by anyone in the encounter who passed its interaction id. Now filtered
  through `Interaction.objects.visible_to`.
- Fail-closed now fails closed on **attribution only**: unauthored detection content can
  no longer silently erase combat events from every participant's feed.
- `Gift.is_magical` (added in the first cut of this issue) was dropped — every Gift is
  magical by definition. Full record: ADR-0187.

**Known wart, not addressed here:** `world/combat/defend_content.py` seeds a `Gift`
purely as a container for combat stances, because `Technique.gift` is non-null and
techniques need somewhere to hang. Making that FK nullable is its own change.

---

## Minor gifts set their own casting style (#2905 — BUILT, 2026-08-05)

A Minor Gift (species ability, in-play power) is magic the character never chose, so
letting #2710's Path-derived `cast_concealment` govern it gave the gift itself no say in
how it manifests — a Khati's species magic would be exactly as loud as whatever Path
they happened to walk.

**Built:**
- `Gift.style` — nullable FK to `TechniqueStyle` (`on_delete=PROTECT`, mirrors
  `Path.style`'s shape). Null = defer to the caster's Path, as before (today's behavior,
  and every Major Gift's expected behavior).
- `_concealment_for` (`world/magic/services/cast_observation.py`) now checks
  `technique.gift.style` first, falling back to the caster's Path style exactly as before
  when the gift sets none. Capability gating (`technique_performable` /
  `StyleCapabilityRequirement`) is unaffected — it still reads the caster's own Path style.
- Full record: ADR-0199.

---

## Technique prerequisites + thread carry (#4097, BUILT 2026-10-01)

GM rulings needed two things the engine didn't have: a way to say "you must already
know/hold X before you can learn Y," and a way for early investment in a foundational
technique to keep paying off once a character learns what it unlocks.

**Built:**
- `AbstractUnlockRequirement.technique`: a fourth polymorphic target (alongside
  `class_level_unlock` / `thread_crossing_threshold` / `path`), gating whether a
  character may *learn* a technique. `LegendRequirement`/`ItemRequirement` reject it
  (narrowed to their own `Meta.constraints`).
- `GiftHeldRequirement` (holds a gift, named and lineage-aware or blank for any) and
  `TechniqueKnownRequirement` (already knows a named technique) are the two new
  requirement types authored against a technique. `MajorGiftTechniqueRequirement.gift`
  became optional (named counts that gift's count; blank counts the best of any single
  held major gift, never summed).
- `concrete_requirement_types()` (`world.progression.services.spends`) discovers
  requirement types via `apps.get_models()` instead of a hand-maintained list that
  silently skipped an unregistered type.
- `charge_and_learn` calls `check_requirements_for_technique` and raises
  `TechniqueRequirementsNotMet` when unmet; both front doors (teaching offers, Academy
  TRAIN) route through it. CG pick lists exclude gated techniques outright
  (`get_technique_options(..., exclude_gated=True)`), since a draft has no character to
  evaluate the gate against.
- **Thread carry:** a thread woven into a prerequisite technique empowers, at full
  level, everything that technique transitively unlocks (including a hidden
  ultimate several `TechniqueKnownRequirement` hops downstream).
  `prerequisite_technique_ids` walks the requirement graph;
  `PullActionContext.involved_technique_closure` unions it with the pull's own
  involved techniques; `_anchor_in_action`'s TECHNIQUE branch reads the closure.
  Applies to both casts and paid pulls; the passive Ambient Activation sweep is
  deliberately left unwidened.
- Full record: `docs/systems/magic.md`'s "Technique Prerequisites" and "Thread Carry
  Through Technique Prerequisites" sections; `docs/systems/progression.md`'s "Path and
  Technique Requirements" section; ADR-4097.

---

## Audere unlocks ultimates (#4098, BUILT 2026-10-01)

Audere and Audere Majora used to raise a character's intensity and anima pool without
giving them anything they couldn't already do. The #4073 owner's GM rulings turned
Audere into the moment a character's magic reaches powers otherwise out of reach.

**Built:**
- `Technique.is_ultimate` flags a technique as an ultimate; `KnownUltimate` is a
  character's per-technique discovery record (never a `CharacterTechnique`), with the
  character's single `readied` pick enforced by a DB constraint. Attaches via
  `PathGiftGrant.ultimate_techniques` (owned: Path x major Gift),
  `WorshippedBeing.ultimate_techniques` (bond: patron), and
  `CompanionArchetype.ultimate_techniques` (bond: companion),
  `AlternateSelf.ultimate_techniques` (bond: alternate self, #4731), and (#4118)
  `Gift.ultimate_techniques` (minor gifts).
- Every ordinary acquisition surface (CG catalog, covenant role grants, the Sphinx's
  shopping list, the ORGANIZATION thread weave, alternate-self grants, item
  `TechniqueGrant`, GM award, ritual SERVICE dispatch) excludes `is_ultimate=True`
  through one shared guard, `enforce_not_ultimate`.
- **The reveal** (`world/magic/services/ultimates.py`) is derived on read, not an
  offer table: plain Audere reveals the current Path's ultimates for the character's
  major Gift; Audere Majora reveals the new Path's. An owned known ultimate persists
  across a Crossing (still listed as long as the granting Gift stays held as MAJOR); a
  bond ultimate is listed only while that bond is active. Undiscovered candidates
  surface only their category (Sword/Shield/Crown, under authored display labels) -
  never a name, a description, or the technique's identity.
- **Choosing readies; it does not cast.** The pick is castable only through the
  ordinary combat declaration while an active DECLARING round holds - never via clash,
  never via a scene cast.
- **Upgrades (#4097 integration):** a later Path's ultimate can list an earlier one as
  its prerequisite, carrying its threads forward.
- **Deferred certain death:** Soulfray's `character_loss` consequence, under Audere,
  defers rather than kills - `CharacterVitals.death_certain_pending`, resolved when the
  last deferring condition ends (backstopped at encounter cleanup), honoring story
  protection. **Soulfray can kill only inside a combat encounter** (owner ruling,
  2026-10-01): a scene cast, a technique-enhanced social action, a battle, and an
  out-of-combat reactive spend are all non-lethal, capped below the first death-risk
  Soulfray stage.
- **Audere Majora's round-resolution block narrowed** to the undecided-offer window
  only, so a round can resolve - and a crosser can act on the new Path - after a
  Crossing instead of every later round freezing.
- **Required-content sentinels:** a Path x major Gift grant with no ultimates is
  flagged as an unfinished Path; the runtime fallback is minimal (Audere's surge with
  no reveal). A second sentinel flags any unauthored `AudereThreshold` reveal-copy
  field (framing line, deferred-death line, the three category labels).
- **Web, telnet, and the magic sheet** all carry the reveal, the choice, and known
  ultimates - `UltimateRevealDialog`/`UltimateRevealGate`, the telnet `ultimate`
  reveal handler (snapshot-guarded against a stale listing), and `SpellbookTab`.
- Full record: `docs/systems/magic.md`'s "Ultimates" section;
  `docs/systems/INDEX.md`'s Magic and Vitals sections;
  `docs/architecture/runtime-modifiers-audere.md`'s "Ultimate Reveal During Audere"
  and "Certain Death Deferral" sections; ADR-4098.

**Deferred (spec scope, not a gap in this build):**
- ~~Past-life bond ultimates~~ BUILT in #4731: `AlternateSelf.ultimate_techniques`, an
  alternate-self bond source in the reveal.
- Authoring the ultimates themselves, and the category display labels, is staff work
  tracked under #4089 - production has 76 Path x Gift grants and 0 authored ultimates
  today, which is exactly what the Required-content sentinel above is for.

---

## Minor-gift ultimates and technique manifestation (#4118, BUILT 2026-10-04)

The Arx 1 GM rulings for ultimates from minor gifts, and for bringing a bound being or
companion into a fight, built as two additions to the #4098 ultimates work.

**Built:**
- `Gift.ultimate_techniques` (M2M to ultimate techniques): a MINOR gift's ultimates are
  revealed at Audere to any character holding the gift, as a Gift group
  (`UltimateSource.GIFT`, `_gift_pools`). A technique reachable through a patron pool and a
  gift pool shows only in the earlier (patron) group. Admin form: minor gifts only, and
  each ultimate must belong to the gift; `Gift.clean()` rejects flipping a gift with
  ultimates to MAJOR.
- `TechniqueManifestOption` (authored per technique: a `WorshippedBeing` or a
  `CompanionArchetype`, plus a tier) and `CharacterManifestation` (the character's chosen
  option, constrained to an active bond). `manifest_bound_entity` runs when a manifesting
  technique resolves in combat: a being's avatar is moved into the caster's room and added
  as an ALLY `CombatOpponent` at the option's tier; an archetype option materializes the
  character's own companion. Works on ordinary techniques (low tier, a limited form) and on
  ultimates (high tier, the full arrival).
- Four REQUIRED-tier probes: `manifest-being-avatars`, `manifest-archetype-abilities`,
  `manifest-tier-templates`, and (#4076) `manifest-being-threat-pools`.
- (#4076, 2026-10-05) The pilot replay: `BoundBeingTurnsBattleTests` in
  `integration_tests/pipeline/test_audere_ultimates_e2e.py` drives Audere, a patron's
  ultimate, the being's arrival and action, the deferred death and the GM prompts as one
  scenario. It found two gaps, both fixed: an ultimate's roll could fail (now floored at
  the lowest authored success, `_floor_ultimate_at_success`), and a manifested being had
  no way to act (`TechniqueManifestOption.threat_pool`).
- The flow-payload `summon_ally` threat-pool summon is unchanged.
- Full record: `docs/systems/magic.md`'s "Ultimates" and "Manifesting a bound entity"
  sections; ADR-4118.

**Not built:**
- A character-creation picker for the manifested entity (GM or staff set it in the admin).
- Manifestation outside combat.
- A persistent bonded Companion made by a cast.
- Authoring the options and the minor-gift ultimates is staff work.

---

## Soulfray Stage Builder (#4089, BUILT 2026-10-03)

Authoring a Soulfray stage's consequences meant hand-editing a `ConditionStage` change
form, its separate consequence pool, and each consequence's own change form - no single
page, and nothing told staff a stage had nothing to draw or that no stage could kill.

**Built:**
- `soulfray_ladder_summary()` (`world/magic/services/soulfray.py`) resolves every
  Soulfray stage's EFFECTIVE consequences (own pool entries merged with a shared
  parent's) in two queries; `soulfray_stages()`/`is_soulfray_stage()` are the shared
  lookups; `nonlethal_ceiling_for(summaries)` is the pure non-lethal cap formula. The
  admin page, the Required-content probes, and the game's own non-lethal cap all read
  this one call, so they can never disagree.
- **Fixed:** the non-lethal cap and the safety checkpoint's death warning used to read a
  stage's own pool entries only; a `character_loss` row inherited from a shared parent
  pool was drawn by a lethal cast but never capped for a non-lethal one, and the
  checkpoint never warned of it. Both now read the merged, effective consequences.
- **The Soulfray Stage Builder** (`src/web/admin/soulfray_builder/`) - one page per stage:
  its own fields, on-entry conditions, resilience-check penalty, consequence pool (own
  rows plus an optional one-level-deep shared parent), every row ("What the roll can
  draw"), and each own row's effects, saved in one transaction and credited. "Copy rows
  from &lt;stage&gt;" prefills a new stage from a neighbor's own rows. Two
  Required-content rows ("Soulfray stage consequence pools", "Some Soulfray stage can
  kill") link straight into the stage with the gap.
- **The outcome wheel reaches Soulfray.** A dramatic stage draw (any option ticked
  `theater` or Can-kill) now spins the same #924 roulette wheel every other dramatic
  check outcome does, built from the drawn tier's UNFILTERED options so a row a
  non-lethal cast's own filter removed still shows and is spun past; delivered to the
  caster only, after the triggering action's own wheel(s) on the scene path, never to
  telnet.
- **ADR-4089-A** records that the Crossing gate's climax comes from the encounter's
  intensity, never from a Required-content row demanding authored high-tier threat
  content; **ADR-4089-B** records the wheel rules above.
- The `AudereMajoraThreshold.minimum_warp_stage` picker (form, admin formfield, and
  autocomplete) now offers Soulfray stages only - a non-Soulfray pick there was always a
  content error, since the Crossing gate compares the caster's Soulfray stage order
  against it.

Full record: `docs/systems/magic.md`'s "Soulfray" section; `src/web/admin/CLAUDE.md`'s
"Soulfray Stage Builder" section; ADR-4089-A and ADR-4089-B.

---

## GM narration of mechanical events (#4101, BUILT)

Audere surges and Audere Majora Crossings used to resolve their authored text as a flat
broadcast with no chance for the GM running the scene to narrate it themselves.

**Built:**
- `DramaticMomentSuggestion` (the #2183 technique-entrance confirm inbox) is renamed
  `GMPrompt`, moved to `world/gm`, and gains a `kind` (`GMPromptKind`): the original
  `dramatic_moment` confirm kind plus six narration kinds, three of them this app's own
  (`audere_surge`, via `world.magic.audere._announce_surge`; `crossing`, via
  `world.magic.audere_majora._route_crossing`; `audere_ultimate`, via
  `world.magic.services.ultimates._route_ultimate_chosen`) and three from other apps
  (`miracle`, `death`, `stake_outcome`; see `docs/roadmap/gm-system.md`'s Phase 10).
- Each event source calls `world.gm.prompt_services.route_narratable_event`, which prompts
  every opted-in GM (`GMPromptFilter`/`GMPromptGroup.AUDERE` covers all three magic kinds)
  with a `GMPrompt` to narrate; with none opted in, the resolved text delivers unprompted,
  byte-identical to pre-#4101 behavior.
- **Prepared per-character text** (`models/prepared_text.py`): `CharacterCrossingText`/
  `CharacterSurgeText`, authored by staff or a character's table GM, resolved field by
  field (the character's own prepared text, then, Crossing only, the patron
  `AudereMajoraFaithVariant`, then the authored tier default). A Crossing's prepared text
  is consumed on use; a surge's is reusable.
- **A GM's narration never releases the authored defaults by itself.** Both legs (room,
  private) go out at most once each, independently, only when the prompt's event closes.
  A Crossing's private vision still logs (`narrate_privately`) even with no active scene.
- **The ultimate-pick reveal is GM-signal-only**: no authored default line exists for a
  readied pick, so with no GM opted in nothing extra is delivered; the pick itself still
  works exactly as before #4098.
- Full record: `docs/systems/magic.md`'s "GM Prompt Queue" section;
  `docs/systems/scenes.md`'s "GM narration of mechanical events" section;
  `docs/architecture/runtime-modifiers-audere.md`'s "GM narration of surges and Crossings"
  section; ADR-4101.

**Deferred (spec scope, not a gap in this build):** a new mechanical event wanting GM
narration needs a new `GMPromptKind` + `GMPromptGroup` mapping + event-source call site;
the queue, filter, and composer surfaces are already generic over `kind` and need no
further change.

## Magical skills, slice 1 (#4450, ADR-4450, BUILT 2026-10-18)

Every magical roll now includes skills that staff choose in admin; before this a Tradition gave
no mechanical content to train, and magic drew on three magic-category skills only through the
caster's personal Anima Check.

**Built:**
- Check engine: `ExtraTraitTerm` and a keyword-only `extra_traits` on the roll functions
  (`docs/systems/checks.md`). Terms score like extra check type rows, develop once per trait per
  roll, and join the roll's involved traits.
- Models: `MagicActivity` (23 kinds of roll), `MagicActivitySkill`, `Path.technique_skill`,
  `Gift.technique_skill` (Minor Gifts only, DB constraint), `Technique.skill`,
  `ConditionCategory.adds_loss_of_self_skills`. Schema-only migrations, no placeholder rows.
- `world/magic/services/magic_skills.py`: the technique skill order (technique override, then the
  caster's current Path for a Major Gift, then the Gift for a Minor Gift), `resolve_cast_check`
  and `CastCheck` (replacing `resolve_cast_check_type`), activity terms, `loss_of_self_terms`.
- Roll sites: all casts (scene, combat round, joust, clash, interception, battle, ward
  penetration, social action, standoff display cast with per-technique grades) and every activity
  roll in the `MagicActivity` list.
- Cast thread pulls include the cast's stat, personal skill and technique skill, so a TRAIT
  thread on any of them is offered and pulls.
- Character creation no longer offers MAGIC-category skills as the Anima Check skill.
- Admin changelists and fields for every mapping; three Required content probes (unmapped
  activities, Paths and Minor Gifts).

**Follow-ups, filed separately:** #4456 (fixed-value magic becomes checks that scale a cost or
benefit by result tier), #4457 (Traditions train the magical skills; Orphans lack them, built as
slice 3 below), #4458 (resonance-flavoured options on threads in magical skills). **Open tuning
question:** trained casters' results shift upward against today's difficulty bands; check after
play.

## Magical skills, slice 3: Traditions train them (#4457, ADR-4457-A, BUILT 2026-10-21)

Before this a Tradition gave no skill content and any player could spend CG points on Magic skills,
so a schooled character and a self-taught one started alike. Now the schooling stance a player pays
for under Tradition Training sets the level every Magic skill starts at, CG points never buy a Magic
skill, and a character who starts behind catches up in play, fastest through an Academy course.

**Built:**
- `SchoolingLine.magic_skill_floor` (rank 0 pinned at 0 by a check constraint). The set trained is
  every skill in the MAGIC trait category (`magic_category_skills()`), the same for every Tradition.
  Finalize writes the floor to each, one `CharacterTraitChange` apiece (source character creation).
- Which Tradition states open which stances (`SCHOOLING_MAX_RANK_BY_STATE`): a living Tradition
  ranks 0 to 2, an orphaned one (teachers gone) ranks 0 and 1, a self-taught one none. The Tradition
  list and `TraditionSerializer.get_schooling` cut to those ranks; a pick the state no longer opens
  is dropped by reconcile. A stance offer saved without its stance is never offered.
- CG refuses points in a Magic skill and in a specialization of one; the skills step shows Magic
  skills as a read-only "From your Tradition training" group (or a muted untrained line), drops Path
  suggestions naming one, and ignores Magic ids on an older draft.
- Tradition slate page: a "Magic skill floor" input per stance (refused above the creation skill cap)
  with a read-only line naming the Magic skills it trains. Three Required content TUNING rows:
  stances with no floor, Magic skills with no Academy course, Path suggestions naming a Magic skill.
- Academy skill courses: `OfferKind.SKILL_COURSE`, `SkillCourseOfferDetails`, `SkillCourseEnrollment`
  and `run_skill_course_offer` (enroll once for coin and a Golden Hare, then rolled AP sessions, one
  per course per game week, scaled by `TrainingOutcomeAward`; development past an XP boundary waits in
  the course; every refusal charges nothing; no Unbound surcharge). `train_skill` and
  `points_to_next_boundary` in `world.skills.services`, shared with weekly training.
- Trainer menu price line on the web and in telnet `hire` (`OfferPrice`, `format_offer_price`,
  `InteractionOfferSerializer.price`) for skill courses and TRAIN. `AcademyOfferApCostError` replaced
  `TrainOfferMisconfiguredError`; `_academy_for` is shared by TRAIN, the course and settle-obligation.
- Journeys: `integration_tests/test_tradition_training_journeys.py` and
  `integration_tests/test_academy_skill_course_journeys.py`.

**Deferred (not a gap in this build):** a per-Tradition skill list (needs a design call: does a
Tradition train different skills, and does that replace or add to the uniform floor; the affinity skills
and the fighting styles' skills got one in #5326, below); a floor
weighted toward the Path's technique skill (rejected here, it would make one Tradition train
differently by Path rather than by stance); separating training level from Academy sponsorship and
retiring the "Unbound" name (#4536). Authoring the floors, the courses and their check types is staff
work on the Required content rows above; there is no placeholder data.


## Magical skills, slice 4: training pool and Tradition teaching fit (#4659 slice 2, ADR-4659-B, BUILT 2026-10-25)

Slice 3's fixed floor gave a stance's student one level in every Magic skill and no say in what
the schooling was in. Now the stance gives points the player spends, and a Tradition teaches some
students better than others.

**Built:**
- The floor became training points: `magic_training_points` modifier target, read by
  `CharacterDraft.magic_training_pool`; `SchoolingLine.magic_skill_floor` and its constraint removed
  (column dropped by 0299 with no carry: the production dump arxii-20261025T033001Z held 0 schooling
  lines, so the disposition is "empty in production", ADR-0237).
- Teaching fit: `Tradition.favored_affinities`, the `TraditionTeachingConfig` singleton and
  `world/magic/services/teaching_fit.py`, comparing `Affinity` rows by foreign key only: character
  creation reads the picked Gift resonance's affinity, the Academy the affinity of the resonance on
  the student's active GIFT thread for their Major Gift.
  Flat Gift and affinity bonuses join the pool only when the draft has some training; the player must
  spend all of it at the ordinary 10 points per step, validated at the Gift stage and written at
  finalize.
- Academy: a course taught under a Tradition lowers the session check's difficulty for a fitting
  student (`_course_ease`, since #5326 `_course_terms`), and the offer shows `teaching_line` and `fit_line` on the web and in telnet.
- Frontend: a training step on the Gift stage (after the Resonance step, stepping by the payload's
  `step`), "Teaches well" tags on Tradition and Gift cards, the
  stance training-points line, the Skills stage Magic group, and the two offer lines.
- Admin: the tradition slate shows a stance's points read-only; the `schooling-magic-skill-floors`
  Required content row now lists stances whose distinction has no training effect.

**Not built:** a per-Tradition skill list (built for the affinity skills and styles' skills in #5326,
below) and fit by the character's aura (#4672). The starting
aura now follows the picked resonances (#5123).

## Magical skills, slice 5: Traditions decide who teaches (#5326, ADR-5326, BUILT 2026-11-28)

Weekly training in a Magic skill needed no mentor, so a character could raise Villainy, Heroism, a
fighting style's skill or Occult alone, and no Tradition said what it taught. The maintainer ruled that
no magical skill is self-study: the Traditions' teachers decide.

**Built:**
- `Tradition.taught_skills` (M2M `Skill`, limited to the Celestial and Abyssal affinities' skills), ticked on
  `TraditionAdmin`: Heroism for a clearly Good Tradition, Villainy for a clearly Evil one, both for a neutral
  one. Reflection is taught by every Tradition with no tick; a fighting style's skill by the Traditions in
  `CombatStyle.taught_by`; every other Magic skill by every Tradition. The state of a Tradition is never read.
- One rule module, `world/magic/services/tradition_teaching.py` (`tradition_teaches`, `is_tradition_governed`,
  `is_outsider`, `TeachingContext`, `build_teaching_context`, `training_verdict`), read by creation, weekly
  training and courses.
- Weekly training: a Magic skill needs a mentor whose active Tradition teaches it and who holds a rating above
  0, refused with a line naming the next step; the weekly run asks again for every standing allocation and
  skips a stale one with one narrative line, no development and no AP spent. A mentored week pays as before:
  no penalty for a mentor of another Tradition.
- The exception: a distinction effect staff author on the `self_teaching` lever (`self_teaching_granted`), yes or
  no, read through `get_modifier_total`.
- Creation: a draft is offered only the affinity skills its own Tradition teaches (`training_skills`,
  `reconcile_magic_training`), `required_spend` follows the shorter list, and the Tradition list names what each
  teaches (`taught_skill_names`).
- Academy: a course in a governed skill is refused when staff author it on a role whose Tradition does not teach
  it and again at enrollment; an outsider's session adds `TraditionTeachingConfig.other_tradition_course_difficulty`
  and the trainer menu says so in `outsider_line`; a course already paid for keeps running.
- Three Required content TUNING rows (`affinity-skills-taught`, counting only Traditions creation can reach;
  `governed-skills-taught`; `courses-taught-by-their-tradition`) and a corrected consequence on
  `magic-skill-courses`.
- Review fixes: one rule source (`tradition_teaches` reads the same `TeachingContext` the batch does), a character
  is never her own mentor nor another character her player plays (`current_player_ids`), and a refused mentor
  gets one line that reveals nothing about the persona.
- The mentor must agree (ruled 2026-11-28, "The mentor must agree"): naming a mentor only asks her,
  `TrainingAllocation.mentor_accepted_at` records her agreement, and a mentor who has not agreed counts as no
  mentor everywhere. She answers from her own account's list (the player of her character now, the creator of
  her roster entry when nobody plays her, or staff; never the student's player), so a game master who holds an
  NPC answers for it: telnet `training requests|accept|decline|stop` and the training viewset's `mentoring/`,
  `accept-mentoring/`, `decline-mentoring/` and `stop-mentoring/` routes. The web screens for it are the next
  task in this PR.
- Journeys: `integration_tests/test_traditions_teach_journeys.py`, plus rows in
  `test_earning_your_keep_journeys.py`, `test_tradition_training_journeys.py` and
  `test_academy_skill_course_journeys.py`; one property per rule in
  `integration_tests/fuzz/test_traditions_teach_properties.py`.

**Staff must author before this helps anyone:** tick Heroism and Villainy on each Tradition; author the
self-teaching lever's category and target, a prodigy distinction with one effect on it, and the same effect on the
`unbound` distinction; set the extra course difficulty; give trainer roles a Tradition (all three seeded Academy
trainer roles have none) and author a course in Heroism, Villainy and each fighting style's skill on a role whose
Tradition teaches it. Until then those skills rise only through a mentor who holds a rating, or by use.

**Not built, on purpose:** teaching ordinary Magic skills such as Occult by Tradition (no list governs them), a
good-or-evil rating on a Tradition, any use of `favored_affinities` for teaching, a penalty for mentoring, and any
change to learning by use or by an XP breakthrough.

## Magical skills: Magic skills only (#4547, BUILT 2026-10-21)

The skill pickers took any skill, and two seeders invented placeholder skills (ritualism, occult,
theology) and weighted them into magic check types, so a cast could count one skill twice: once
from the check type, once as the technique skill.

**Built:**
- The four pickers (`MagicActivitySkill.skill`, `Path.technique_skill`, `Gift.technique_skill`,
  `Technique.skill`) offer and accept Magic-category skills only, in admin and in `full_clean()`
  (`world/magic/skill_choices.py`). Schema-only migration `0277_magic_skill_pickers_magic_only`.
- `seeds_checks.py` and `seeds_cast.py` name, create and weight no skill; the magic check types and
  the "Technique Cast" fallback weight their stat only. Sanctum ritual configs take their skill from
  the `RITUAL_WORKING` mapping.
- Required content row `check-types-weight-no-magic-skill`, linking to the offending check types.
- Journey: `integration_tests/test_magic_skill_pickers_journeys.py`.

**Not done here, on purpose:** no data migration. Production keeps its placeholder skills and the
check-type rows that weight them; staff rename, repoint or remove them in admin as part of the skill
revamp, working from the new dashboard row.

## Magical skills: the casting style carries the skill (#5002, ADR-5002, BUILT 2026-11-07)

A Path's casting skill and its casting style were authored on different rows and could drift.
The owner ruled them one thing seen from two sides: the style is how a character works magic,
the skill how good they are at it.

**Built:**
- `TechniqueStyle.skill` (Magic skills only, same picker rules). `Path.technique_skill`,
  `Gift.technique_skill` and the Gift minor-only constraint are removed by schema-only migration
  `0373_casting_style_carries_skill`, with no data migration: the owner signed off the discard of
  the one production value (ADR-0237); staff set the skill on each style in admin.
- One rule for a cast's manner and skill: `world/magic/services/casting_style.py`
  (`casting_style`, the Gift's own style else the caster's Path style), read by cast
  concealment and by `magic_skills._skill_for_path`. A Minor Gift with no style now adds the
  caster's Path style skill. The #4555 own-Path skill machinery (`technique_paths`,
  `skill_path`, `Technique.cached_own_paths`, its admin invalidation) is retired; a technique
  cast after a Crossing adds the current style's skill.
- Required content: one `casting-style-skills` row (styles used by an active Path or a Gift with
  no active skill, each linked to its edit page) replaces the Path and Minor Gift rows.
- Admin: the skill picker is on the Technique style form; the Path and Gift forms carry only the
  style.

## Changing a thread's resonance (#4735, slice 6 of #4672, BUILT 2026-10-27; reshaped by #5123)

A player can move part of one of a thread's resonances to another through a rite (#5123, ruling
31: a thread at its cap cannot change its mix by imbuing). A retune within the source resonance's
affinity moves the points one for one, a Fall or Redemption across affinities converts them at the
authored pair rate (a Redemption never loses the amount entirely). The thread's level and
developed points do not change; its resonance rows move, and the leading resonance follows. With
one thread per anchor there is no merging of two threads: the Fall and Redemption merge rows on one
thread instead.

**Built (backend, telnet, web API, Spellbook dialog):** `services/thread_resonance.py` (options, a pre-spend check,
the change; #5123 reshaped it onto `ThreadResonance` rows), `PerformRitualAction._precheck` so a
refused move spends nothing, the
target-resonance offering paid toward the chosen resonance, telnet `from=<id> amount=<n>
resonance=<id>`, web `kwargs.{target_resonance, from_resonance, amount}`, `GET /api/magic/threads/{id}/resonance-options/`, a result line that
telnet and web both show, Required content rows `thread-resonance-ritual`,
`thread-resonance-ritual-single` (TUNING: a second rite on the path) and
`thread-resonance-ritual-web-payable` (TUNING: a rite with a template or touchstone component the
web cannot pay). The thread uniqueness constraints are one thread per anchor since #5123, and
they also ignore retired threads. Journey: `integration_tests/test_thread_resonance_journeys.py`.

Anchor rules (ruled on the final review): a GIFT thread moves between any resonances (a Gift's
`resonances` list limits nothing, owner ruling 2026-11-14, #5123); a SANCTUM thread has no options (the Ritual of Purging changes
its sanctum's resonance); a TECHNIQUE thread whose signature bonus requires a resonance is held
until the signature is cleared.

**Built (frontend):** `ThreadResonanceDialog` on `ThreadDetailPage` ("Change resonance" button,
not the thread card): a "Move from" pill per resonance row and a "Points to move" stepper
(#5123), "Change to" pills with a move-kind swatch, offering
pills only when the rite asks for them (`offering_count` picks), the server's
`unavailable_reason` in place of the pills, and the server's 400 detail on a refusal. Vitest:
`frontend/src/magic/components/threads/__tests__/ThreadResonanceDialog.test.tsx`.

**Not built here:** web pickers for item-template or touchstone components on the retune rite
(the dashboard row flags such a rite). Nothing is authored: until staff create the SERVICE
ritual, the dashboard row lists it.

---

## Drift correction: the conversion offer and rite (#4733, slice 4 of #4672, BUILT 2026-10-27; reread by #5123 and #5124)

A character who earns resonance from a deed in their main affinity while unsettled (#5123) can
atone: turn resonance of an affinity grown past who they are into the resonance the deed grew,
with a rite. Since #5124 the chance stays open until used (not once per scene) and the rite is
the rite of settling over what the character reflected on. It is read on lifetime, so it works after the excess was spent.

**Built:**
- Deed classification: `DEED_GAIN_SOURCES` / `NON_DEED_GAIN_SOURCES` beside the accelerated sets,
  with a total-classification test; `GainSource.DRIFT_CORRECTION` for the conversion itself.
- Offers: `DriftConversionOffer` (one per character since #5124) with a `DriftConversionCap` per
  target resonance, opened or extended from `grant_resonance` and open until the rite spends it (the
  scene-end lapse is gone). An offer needs the grantee standing in a live scene at grant time, so a deed
  settled away from a scene (the weekly pose-endorsement settlement) opens none. Telnet players get a
  line on open; the sheet's aura card shows the open chance.
- The rite: `DriftCorrectionConfig` (rite, check type, difficulty, cap percent) and
  `DriftCorrectionOutcomeShare` (share of the request converted per outcome tier, never lower at
  a better tier), run since #5124 by the rite of settling (`perform_settling_rite`) over every waiting
  reflection, at the authored Fall and Redemption pair rates through `convert_resonance_amount`. A
  failed roll spends the offering and keeps the cap. Worn focus adds to the check. `max_yield_per_earned_point` estimates farm risk for tuning.
- Offering: a third `RitualComponentRequirement` mode (`matches_target_resonance`,
  `min_item_meaning`) accepting an item tied to the target resonance, carrying a motif facet of it,
  or meaning enough to the performer.
- Surfaces (reshaped by #5124): `PerformSettlingRiteAction`, telnet `aura` / `aura settle <offering>`,
  REST `/api/magic/settling-rite/` and `/api/magic/drift-correction/pending/`, and the sheet's aura card
  with `SettleAuraDialog` (the scene-page and game-page gate, the atone, decline and accept actions and
  verbs are removed); admin pages for the tuning rows; Required content row
  `drift-correction-config`. Journey: `integration_tests/test_drift_correction_journeys.py`.

**One rite (#4751, BUILT 2026-11-17, ADR-4751).** The settling rite is the only rite for a changing
aura; the older Rite of Atonement (never performable, since ritual dispatch called its service with
arguments it did not accept) was removed with its Ritual row, `FallRedemptionConfig.penance_exchange_rate`,
the partial path of `convert_resonance`, `GainSource.PENANCE` and `CorruptionRecoverySource.ATONEMENT_RITE`
(migrations 0448 and 0449). Built with it: each main affinity sets its own range before Unsettled and step
width (`Affinity.unsettled_tolerance_percent`, `unsettled_step_percent`; `_unsettled_numbers`), so Celestial
can be strict; embracing a deed pays at the direction rate for the pair (`embraced_amount`, preview
included); a disown across an unset conversion pair names the pair, and the Required content row
`affinity-conversion-pairs` lists the unset pairs; the canonical Primal corruption coefficient is 0, so only
Abyssal casts corrupt. Corruption falls by daily decay and a Sineater's rescue, and, since #5177 (below),
by Sineating, which takes it on at any stage. Staff still author Celestial's range and set
Primal's coefficient to 0 on the production Affinity pages.

Drift thresholds (slice 3, #4732) were built after this slice and replaced by the unsettled reading
(#5123, below). Nothing is authored yet: until staff set the rite, check type and a share for every outcome tier,
the rite refuses and the dashboard row says so.

---

## Acting aura and the Audere alternate self (#4731, slice 2 of #4672, BUILT 2026-10-27)

An alternate self with a resonance now changes the aura a character acts with
(`acting_aura`), and an alternate self is a bond source in the Audere ultimate reveal (the
past-life source #4098 deferred): every self with ultimates offers its cards, and choosing
one readies the ultimate and puts her in that self, which ends automatically with Audere or
the fight, or holds until she is talked down. Revised 2026-10-27 (owner): the reveal's choice
replaced a one-per-character emerges-at-Audere flag. Built: `AlternateSelf.ultimate_techniques`,
`revert_kind` and `emergence_condition` with a check constraint,
`ActiveAlternateSelf.assumed_at_audere`, `UltimateSource.ALTERNATE_SELF` and
`_alternate_self_pools`, `assume_alternate_self_for_audere` run on the choice's commit
(swapping out a different worn self, refused with a message when she is not in control),
the revert in `end_audere` and in encounter cleanup for every participant (so a
duration-expired Audere still drops an automatic self), the telnet `bond: <name>` label
and the web reveal's alternate-self heading, `acting_aura` and its readers (cast alignment,
place of power on arrival and during a cast, defilement, covenant attacker affinity),
working affinities that follow the worn self's resonance (`working_affinities`), journeys
in `integration_tests/test_acting_aura_journeys.py` and
`integration_tests/test_audere_alternate_self_journeys.py`.

## Resonance burning as a Strain option (#4736, slice 7 of #4672, BUILT 2026-10-27)

A thread pull can burn resonance to push a cast harder: ceiling from runtime intensity
(`StrainConfig.burn_per_intensity`), a strain check whose outcome tier selects a
`StrainBurnReach` share, strain units at `Affinity.burn_value`, and a hasty fall for an
Abyssal acting aura burning other resonance (Fall pair rate, `CorruptionConfig.hasty_fall_multiplier`
on corruption). A share of the strain bonus feeds the caster's engagement intensity
(`StrainConfig.engagement_share_percent`; #4738 reuses it). One burn is paid once and strains only the
action it was declared with. Corruption now counts burned points and the non-combat pull's
resonance spend (that gap is closed). Built: `world/magic/services/burn.py`, burn columns on
`CombatPull` and `SceneActionPullDeclaration`, telnet `burn=<n>`, web `pull_burn` / `pull.burn`,
the pull preview's `burn` block and the frontend `PullBurnInput` in the Strain area (combat
card and scene cast). Also fixed: the web combat declaration used to drop its focused-cast pull;
the web now sends the pull on one job (the clash when chosen) and a resubmit never charges it
twice. Not built: the demo's intensity-after and anima-cost projection rows. Journeys in
`integration_tests/test_resonance_strain_journeys.py`. Unauthored until staff set a strain check
type, the `StrainBurnReach` rows and the `burn_value` of each affinity.

## Drift and Resonance Conflict (#4732, slice 3 of #4672, BUILT 2026-10-27; the reading replaced by #5123)

Originally resonance carried outside the affinity she acts with was drift, measured on spendable
balance and weighted per affinity pair; #5123 replaced that reading with being unsettled (below,
ADR-5123-B). Being unsettled strictly past the tolerance makes casting call for a focus check (once per cast inside `use_technique`, before modifiers, on every cast path); a failed check applies the authored Resonance Conflict condition for its authored duration (the scene), whose
check modifier is a labelled penalty on that same roll, severity rising with a worse roll.
Built: `DriftConfig` singleton (every number plus the focus check type and conflict condition
designations; `AffinityInteraction.conflict_weight`, `threshold_percent`, `threshold_floor`,
`severity_step` and `off_aura_pull_steps` of the first build were removed by #5123),
`MagicActivity.KEEPING_FOCUS`, `drift_for`,
`check_resonance_focus`, `ConditionCategory.self_shakeable` with `breakable_condition_filter()`
so `breakfree`, `rally` and the break-free tick reach it while `in_control` stays on
`alters_behavior`, Required content probes, and journeys in
`integration_tests/test_resonance_conflict_journeys.py` (including an unset condition rolling nothing and an enchanted flirt rolling focus) and
`integration_tests/test_conditions_journeys.py`. Stirring it up is authored content (a social
action's consequence pool applying the condition). Content (the condition, its modifier, the
check type) is for staff to author.

## A character with several resonances (#5123, ADR-5123-A and B, BUILT 2026-11-14)

A mixed character is the normal case. Built, as one PR:

- **A thread holds several resonances.** `ThreadResonance` rows (cumulative amount per resonance)
  under one thread per anchor; `Thread.resonance` is the leading resonance, written only by
  `refresh_leading_resonance`; imbuing names the held resonance that pays; the retune rite moves
  part of one row to another; the Fall and Redemption convert and merge rows. A GIFT thread made
  in character creation holds every pick at zero from the start.
- **Each pulled thread names its paying resonance.** `CombatPullThread` / `ScenePullThread`
  carry it; cost, perks and the corruption spend follow it; the leading resonance reads the
  thread's level, a second resonance `DriftConfig.second_resonance_level_step` lower (never beating
  the leader), a held resonance with no imbued row pays and gives no perks. The pull preview lists
  every held resonance's perks per thread, and the pull dialog's Pay with list and Inspect perks
  show them. Telnet `pull=<thread>:<resonance>`, `imbue ... resonance=`.
- **Unsettled replaces drift.** `CharacterAuraShare.settled_percent` is who the character is
  (set at creation from the picks, one Primal and at most one Celestial or Abyssal since #5231, nudged by the Glimpse, moved by accepting). (This
  work also gave a Sineater a Mire share with its own allowance, `CharacterResonance.mire_lifetime`;
  #5177 removed it, because the Mire is now carried corruption.) A
  non-main affinity grown past its settled share plus the range before Unsettled (per main affinity since #4751) makes the character
  unsettled; a pull outside the main affinity calls for no check of its own. Exit (since #5124): the
  rite of settling over what the character reflected on, which atones (lifetime-based) or
  accepts the aura's change by the roll's share. A mixed character
  casts at the full alignment bonus in every affinity they are settled in.
- **Creation.** The Gift stage's resonance step spreads `DriftConfig.creation_points` across
  several resonances with a live halo in words; `provision_magic` seeds lifetime (a
  `CHARACTER_CREATION` ledger row) so a new character reads exactly settled. The 80/20
  `starting_aura_shares` is gone.
- **Surfaces.** The sheet's `AuraHalo` (settled line and Unsettled status; its Mire band went in #5177) and its
  reflections card with `SettleAuraDialog` (#5124), telnet `aura` / `aura settle <offering>`.
- **Removed:** `DriftConfig.threshold_percent`, `threshold_floor`, `severity_step`,
  `off_aura_pull_steps`, `AffinityInteraction.conflict_weight`, `provision_additional_gift_thread`,
  the telnet `drift` command, the merge-two-threads paths (ADR-0237: deliberate discards of tuning
  numbers; no threads or real characters existed, so no data was carried).
- **Journeys and fuzz:** `integration_tests/test_several_resonances_journeys.py` and the unsettled
  fuzz invariants (`integration_tests/fuzz/test_unsettled_invariants.py`).

#5123 did not build what causes a resonance gain (#5124 built that later) or substances and
Primum (#5125 built those later; see "Substances and Primum" above). Staff still author the per-resonance pull perks and the `DriftConfig` numbers in admin.

## Kindled resonances, reflections and the rite of settling (#5124, ADR-5124, BUILT 2026-11-15)

Built as one PR (spec in the issue body; #5129's settling rite folded in):

- **Kindled.** A resonance is kindled when one of its staff-authored `KindlingSituation` rows holds
  (on the resonance, or once on an affinity for all of its resonances), or a Rally or a GM kindled
  it. Strength is a staff-named `KindledStrengthTier` (Faint, Strong, Blazing to start); players
  see the word and the reason, never a number. Six new `Situation` members (thread anchor present,
  own feeling, shared feeling, target in a state they caused, someone in trouble, mission theme)
  are shared with vow perks. `Resonance.feeling` and `MissionTheme` feed them.
- **Uses.** Drawing strength (a kindled payer reads the thread higher; no control given up), giving
  in (Fury for any kindled resonance, replacing the anchor person; Lose yourself only at a blazing
  strength), Dig deep and Rally naming a resonance (a Rally kindles an unkindled one until the
  fight ends), and a GM kindling by hand (`stage kindle`).
- **Earning.** Acting on a kindling situation earns the resonance as `KINDLED_DEED`, scaled by the
  roll (since #5181 only part of it arrives at once and the rest waits to be claimed, see below); an
  outcome with no act aimed at it earns nothing; a mission option shows which kindled
  resonance it feeds. Taking an action never asks how the character feels.
- **Reflecting and settling.** A pose or journal entry carries an optional "Reflecting on" row
  (a deed or the unsettling resonance, then Embrace or Disown; since #5177 also the Mire a Sineater
  carries, then Absolve, Condemn or Succumb). One rite of settling carries every
  waiting reflection out with one offering and one roll; the chance to atone no longer lapses with
  the scene; the click-to-accept, atone and decline paths are gone.
- **Surfaces.** Admin (situations on the Resonance and Affinity pages, one Kindling config page),
  the "Your resonances" panel, the Reflecting on row, the sheet's reflections card and the rite
  dialog, telnet `resonances`, `reflect`, `pose/reflect`, `journal/reflect`, `aura settle`.
- **Not built (by design).** No GM is needed for kindling; a Rally or GM kindling never earns by
  itself; nothing is earned for an outcome alone. Staff must author the situations: until they do,
  nothing is kindled.

## Sineating as a ritual, the Mire as carried corruption, and succumbing (#5177, ADR-5177, BUILT 2026-11-17)

The second of four pieces agreed in the design session for #4751 (the first is #5176; staff sizes are
listed in #5179; earning resonance through poses and the Anima ritual is #5181). Built as one PR:

- **Sineating is a ritual with a roll.** The Sinner's pose attaches a plea; the Sineater's pose performs the
  ritual, chooses how many offered units to take on, and rolls `SoulTetherConfig.sineating_check_type`. The
  chosen units move corruption from the Sinner onto the Sineater whatever the roll, and refill the Hollow;
  the roll's `SineatingOutcomeAward` scales the resonance each party earns, each in the resonance of their
  own half of the bond. It costs no anima and no fatigue. Telnet `pose/entreat` and `pose/sineat`, the web
  pose composer's Sineating row, actions `entreat_sineating` / `perform_sineating` / `decline_sineating`.
- **The Sineater's own thread** is woven when the tether forms, and presence is by character, so a GM can
  run an NPC Sineater. A Sineater whose aura is predominantly Abyssal has fallen and serves no one.
  The resistance a Sineater earns now applies to every Sineater with a tether (it had required a thread of their own in the accruing resonance that nothing prompted them to weave), and its divisor is
  `SoulTetherConfig.resistance_full_at`.
- **The Mire is corruption.** What a Sineater takes on is held on their own corruption, partitioned per
  Sinner by `MireHolding`, softened by resistance, and stopped at the Compulsion stage. It replaces
  #5123's Mire share of the aura (`mire_lifetime`, `mire_allowance_percent`, the drift reading's Mire
  fields, the halo's Mire band), which had no effect until it passed 30% of the aura.
- **Settling the Mire** is a third target of the reflection and the settling rite: Absolve and Condemn
  clear it and reward the Sineater and move the tie; Succumb turns it into the Sinner's resonance in the
  Sineater's aura, pays the Sinner from a per-tether jackpot, and the Sineater can atone by reflecting on
  the succumbing as a deed; the fall pays every Sinner when the Sineater's aura turns Abyssal.
- **Impulses.** Corruption a character carries shows as Intrusive Thoughts and then Compulsion (the
  Sinner's own corruption too); the Compulsion is a scene-scoped condition that penalizes rolls until the
  character earns the resonance there, which adds a little more corruption.
- **Also:** the Soul Tether detail is read only by the bond's two parties and staff; the Tether Strain
  command is `sineater brace`; Required content lists an unset Sineating check, a missing outcome award and
  an unset or unfinished Compulsion condition. Journeys: `integration_tests/test_sineating_journeys.py`,
  `test_mire_settling_journeys.py`, `test_impulse_journeys.py`.
- **Not built (by design).** Rules for one NPC shared by several GMs; magical scars (the conditions are
  built so scars can reuse them); removing `CorruptionSource.SPEC_B_REDIRECT` and `redirect_origin`, a
  decision for the maintainer. Staff must author the Sineating check, its outcome tiers' shares (seeded),
  the Compulsion condition, each resonance's impulse words, and tune the sizes (#5179).

## Earning resonance by claiming kindled deeds and through the Anima ritual, with per-affinity rates (#5181, ADR-5181, BUILT 2026-11-17)

The third of four pieces agreed in the design session for #4751 (after #5176 and #5177; staff
authoring it leaves is listed in #5179). Built as one PR:

- **A kindled deed pays part at once and sets a share aside.** Every kindled deed, in fights, missions
  and social scenes, pays `KindlingConfig.instant_percent` at once (at least 1, so a Compulsion still
  lifts when the deed is done) and adds `claim_percent` to `CharacterResonance.kindled_unclaimed`. The
  two may sum past 100. The deed line reads "You earned N Ruin. M more is waiting to be claimed."
- **Claiming.** What is set aside never expires. A claiming pose or a journal entry collects any or all
  of it across every affinity (`claim_kindled`); the writer alone reads "You gloat. Your Ruin grows by
  7.", with the verb staff wrote on the Affinity (`claim_verb`). The room sees only the pose. A claim
  can ride on the same pose as a reflection or a Sineating. Telnet `pose/claim`, `pose/claim
  <resonance>,...=<text>`; the web pose box and journal form have a claim row, the resonances panel
  shows what is waiting. The claimed share is a deed for worship favor and the settling offer, is not
  separately reflectable and does not lift a Compulsion.
- **The Anima ritual with a partner.** A player can finally start it (web persona menu, telnet `ritual
  anima <partner>`; the code that resolved it existed but nothing created the request). It earns the
  resonance the ritual names in full at once (`AnimaRitualResonanceAward` by roll, plus the kindled share
  when that resonance is kindled) and moves the partner's fatigue by the affinity of that resonance
  (`Affinity.ritual_partner_fatigue`: positive takes, negative eases, zero does nothing); the partner
  reads which before agreeing. (Since #5280 the ritual has two picks and is never solo; see the entry
  below.)
- **Earn rate and learn rate.** `Affinity.earn_rate_percent` scales what a character earns and
  `Affinity.learn_rate_percent` scales technique training. The learn rate is applied by the character's
  main affinity; since #5231 the earn rate is applied by the affinity of the resonance earned, whoever earns it;
  staff grants, character creation and resonance that is only moved or converted are exempt
  (`AFFINITY_RATE_EXEMPT_SOURCES`). This is how Abyssal magic can be faster than Celestial.
- **Journeys:** `integration_tests/test_claiming_kindled_journeys.py`,
  `test_anima_ritual_partner_journeys.py`.
- **Not built (by design).** A ritual that takes in a whole scene (`apply_ritual_bond` takes the partner
  as an argument so it can be called per member), perks that change what a ritual takes or gives, and
  whether an entrance flourish lifts a Compulsion. Staff must author each Affinity's claiming verb,
  earn rate, learn rate and ritual partner fatigue, the instant and claim percentages and the ritual's
  award table; none is seeded (#5179).

## Characters draw strength from a feeling and from what they do to others (#5231, ADR-5231, BUILT 2026-11-21)

Primal resonance is the feeling that drives a character; Celestial and Abyssal are whether helping or hurting
others gives her strength. Built as one PR (one migration, eight columns, no table):

- **A cast is worked in one resonance.** `cast_resonance_for` finds it (named, else a worn alternate self's, else the
  Gift thread's leading resonance, else the Gift's first); `resonance_on_gift_thread` is the one test of a named
  resonance, used at declaration, at round resolution and at scene consent, and a resonance the thread has lost falls
  back to the default and never refuses a round. The choice rides `preferred_resonance_id` and is stored on
  `CombatRoundAction.cast_resonance` and, while a request is pending, `SceneActionRequest.cast_resonance`, so every scene
  route and every focused fight cast honours it. An enchanted Strike names no resonance and shows no picker, so it is
  always worked in the default resonance. A named resonance is accepted on any thread her forms
  come from, a covenant role's thread included, and a caster with no thread on the Gift gets no choice and a default in
  the order Primal, Celestial, Abyssal.
- **Corruption follows the cast's resonance and how Abyssal the caster is.** The whole intensity goes to that resonance
  (a cast worked in a Primal or Celestial resonance adds none); a pull still corrupts by the resonance that paid.
  `CorruptionConfig.light_corruption_percent` (10) applies to the ordinary tick and to a pull paid in Abyssal while the
  caster's aura is below `full_corruption_from_share` (50) Abyssal; the hasty-fall part is never reduced; one rounding
  up, so any corruption added is at least 1 (a few results differ from the old two-step rounding even at 100).
- **Power follows it.** Every resonance-tied power term (touchstones, resonance standing, aura alignment, resonance-scoped
  power and effect targets, the place's reaction) reads the cast's one resonance (`cast_working_resonances`). A cast
  worked in a kindled resonance gains `KindledStrengthTier.cast_power` times the affinity's `kindled_boost_percent`,
  with or without a pull (suppression by a pull was tried and removed; kindling's levers stack and staff tune
  `cast_power`). On a pull a second kindled resonance of the other kind
  adds its boost scaled by its share of the thread, and a payer that brings no perks never takes the stronger mark.
- **The caster sees the choice.** `cast_resonance_options` lists each resonance with its colour, whether it is her usual,
  kindled, stronger and adds corruption; the scene cast panel and the combat declaration show `CastResonancePicker`; the
  pull dialog tags the stronger payer. The technique forms stay separate.
- **Earning and drift.** The earn rate is that of the resonance earned (the learn rate still follows the main affinity).
  Drift reads by side with a new own-side range (`own_side_tolerance_percent`, 15), and a tie in the main affinity goes to Primal.
- **Sineating** moves corruption in the resonance on the bond's thread with the most of the Sinner's own, pays her across
  the thread by the amounts imbued, and the Hollow guards any Abyssal resonance on the thread.
- **Creation** asks for one Primal feeling and at most one Celestial or Abyssal resonance, then the split, with the aura
  drawn as one swirling mass in each resonance's `color_hex` (`StrengthStep`, `AuraSwirl`); fifteen `gift_strength_*` text keys;
  a stored list that breaks the rule shows nothing chosen. `ResonanceWeights.tsx` is gone. Staff's Grant magic is unchanged.
- **Journeys:** `integration_tests/test_strength_in_creation_journeys.py`, `test_cast_resonance_journeys.py`,
  `test_abyssal_temptation_journeys.py`.
- **Not built (by decision):** the character sheet's aura keeps `AuraHalo` (only creation gets the swirl); two characters
  serving as each other's Sineater. Staff must author each resonance's colour, Abyssal's kindled boost and earn rate, and each
  kindled strength's `cast_power`; the starting values are grey, 100, 0.

## Audere earlier with control; Soulfray's anima-0 stage (#4740, slice 4 of #4727, BUILT 2026-10-27)

High control now lets a character reach the Audere offer at an earlier Soulfray stage, the
dangerous Soulfray stages need anima at 0, and no intensity tier reads as a control penalty.
Built: `AudereThreshold.control_per_stage_earlier` (default 0, off) and
`required_stage_order` (steps back along the actual ladder, so non-contiguous stage orders
work), the player told on the web dialog and the telnet `accept` listing when control
lowered the stage (`stages_lowered_by_control`), the control passed from the cast hook (`stats.control`, after Fury)
through `maybe_create_audere_offer` and stored as `PendingAudereOffer.fired_control` for the
accept re-check; `SoulfrayConfig.anima_zero_stage` and its cap in
`_handle_soulfray_accumulation` (lower of it and the non-lethal cap); `IntensityTier
.control_modifier` refusing negatives, the seed's Moderate and Major at 0, and the Required
content row "Intensity tiers never lower control". Audere Majora is unchanged. Staff still
set the step and the anima-0 stage; both default off. Journeys in
`integration_tests/test_audere_control_journeys.py`.

## Deeper design & history

- Scope-by-scope build record: [`magic-build-history.md`](magic-build-history.md)
- Architecture references: `docs/architecture/` (power-derivation, resonance-threads,
  resonance-gain, reactive-layer-foundation, magical-alteration, non-clash-casting, …)
- System reference: `docs/systems/magic.md`

## The anima ritual becomes a scene with a partner that grows two aura resonances (#5280, ADR-5280, BUILT 2026-11-22)

Built as one PR (the numbered parts were the build order):

- **Never alone.** The solo ritual and `perform_anima_ritual` are gone. Every door (persona menu, the
  Rituals page, the ritual's own name, the web dispatch, bare `ritual anima`) refuses a ritual with
  nobody else, with "Name someone else to take part in your ritual." An NPC partner needs a GM
  (a `GMProfile` on the player now playing it, or a scene GM); with none, "Nobody is playing that
  character." The ritual is still refused in combat.
- **Two picks.** `RitualCheckConfig.resonance` became `primal_resonance` and `outward_resonance`
  (three migrations: expand, copy by affinity, contract). Creation writes the heaviest Primal and the
  heaviest Celestial or Abyssal pick. The first setup of the picks is free (`/api/magic/anima-ritual/`);
  after that they are locked and a pick stays until changed. Held means a `CharacterResonance` row, which
  persists when her aura share falls, so a pick keeps paying while she holds the resonance.
- **The split.** The award at the roll's tier splits by the two affinities' settled aura shares. The
  part paid to the outward pick is the award times the outward share divided by the sum of the Primal
  and outward shares, rounded down; the part paid to the Primal pick is the rest; when both shares are
  0 the award splits in half. A share of exactly 0 beside a non-zero one is paid 0. A Partial Success counts as a success at
  its own tier's award; a lower tier recovers no anima and grows no Primal resonance. A part pays
  nothing when the performer no longer holds that resonance. The ritual is the character's own: it is
  the SCENE_ACTION ritual her roster entry knows (`CharacterRitualKnowledge`), never one her player's
  account authored for another character, and a character nobody is logged in as still has hers.
- **The partner's answer.** A player partner endorses or withholds the outward part (after a failed roll,
  `AnimaConfig.failed_endorsement_percent` of the Success tier's outward part is held for them to
  endorse). An NPC partner gives it on the roll alone. Unanswered questions lapse when the scene
  finishes, including a battle ending it, and a late answer is refused. Web card, telnet `ritual
  endorse` / `ritual withhold`.
- **Attunement.** After the free setup the picks change by attunement: staff-set anima, resonance and
  action point costs and an optional check on `AnimaConfig`. It checks only the picks it changes, is
  refused in combat and before any picks are set, spends action points as its check, never refuses for
  lack of anima, and a failed roll keeps the costs and the old picks. Web Attune dialog, telnet
  `ritual attune`.
- **Journeys and properties:** `test_performing_the_anima_ritual_journeys.py`,
  `test_anima_ritual_partner_journeys.py`, `test_attuning_the_anima_ritual_journeys.py` and
  `fuzz/test_anima_ritual_properties.py`.
- **Staff authoring left.** The `AnimaRitualBudgetAward` rows for Failure and Critical Failure are no
  longer read. Staff set the attunement costs and check and `failed_endorsement_percent` (default 50);
  none is seeded.

## Villainy, Heroism and Reflection: a bonus check on every gain and spend (#5308, ADR-5308, BUILT 2026-11-24)

Built as one PR (the numbered parts were the build order):

- **One skill per affinity.** `Affinity.skill` is a one-to-one to a Magic skill (Villainy for Abyssal,
  Heroism for Celestial, Reflection for Primal; the Primal skill is not the Reflection pose or the
  Reflection creation step). `Affinity.clean` refuses a skill another magical roll already adds,
  `MAGIC_PICKER_SKILL_CHOICES` and `RitualCheckConfig.clean` refuse an affinity's skill the other way
  round, and `Affinity.spend_worth_floor_percent` sets the least a pull or kindled cast is worth.
- **The bonus check on every earned gain.** `grant_resonance` rolls `ResonanceGainConfig.bonus_check_type`
  once per affinity paid, with the act's own stat (or the stat `ResonanceGainSourceStat` sets for a source
  that rolled nothing) plus the affinity's skill; `ResonanceCheckAward.gain_bonus_percent` grows the gain
  and the grant records `bonus_outcome` and `bonus_percent`. Exempt, rolled and caller-rolled sources are
  the three `GAIN_BONUS_*_SOURCES` sets. A kindled deed grows its set-aside share by the same percent, and
  a claim of that share rolls nothing.
- **A deed she chose earns a Celestial or Abyssal resonance the character does not hold.** Only a row on
  `CHOSEN_DEED_SITUATIONS` pays her, which today is a mission option's theme. Every other row, and every row
  on a Primal resonance, kindles only a character who holds the resonance. The entry flourish accepts any
  resonance.
- **A pose can reach.** `PoseResonanceReach` (web `reach_resonance_id`, telnet `pose/reach <resonance>=<text>`,
  composer row on the frontend); an endorsement of a reached pose pays that resonance and the endorser
  only confirms.
- **Trickles wait.** The residence and worn-piece ticks write `TrickleAccrual` rows. An anima ritual,
  successful or not, harvests them as one `TRICKLE_HARVEST` grant per resonance with one bonus check per
  affinity, and the ritual line and the "Your resonances" panel (and telnet `resonances`) say what waits.
  A harvest earns no pledge favor.
- **Spending has a worth.** A pull rolls one worth check per paying affinity and scales every effect it
  bought; a kindled cast rolls one for its resonance. The result sets `ResonanceCheckAward.spend_worth_percent`,
  held up by the affinity's floor. A line says "Your Villainy check made it worth 130 percent." only when the
  worth is not 100.
- **The settling rite** adds the skill of the affinity it converts toward to its roll.
- **Deviation from the spec.** A combat pull commits at declaration and the cast resolves later, so a
  combat cast with a pull rolls the pull's worth at declaration and its kindled cast term at resolution.
  Non-combat casts roll once. See ADR-5308.
- **Journeys and properties:** `integration_tests/test_affinity_skill_journeys.py` and
  `integration_tests/fuzz/test_affinity_skill_properties.py`.
- **Staff authoring left.** The three skills and the affinity link, the `ResonanceCheckAward` rows, the
  bonus check type and its difficulty, the per-source stats, the Abyssal floor and any skill accents are
  authored by staff and tracked in an `authoring` issue. Nothing is seeded, so until staff set
  `bonus_check_type` every gain pays its plain amount and every pull is worth 100 percent.
