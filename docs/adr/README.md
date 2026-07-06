# Architecture Decision Records

This log records the *why* behind the hard, surprising, traded-off decisions that shape Arx II —
and the alternatives we rejected. An ADR captures a moment of reasoning so a future agent or human
doesn't relitigate a settled question or "fix" something that was deliberate.

`docs/roadmap/design-tenets.md` and the invariants in `CLAUDE.md` are the **forward-looking directives** —
they tell you what to do. The ADRs are the **record of why** that directive exists and what was
weighed against it. The two must stay in tandem: when a decision changes, update both the directive
and add (or supersede) the ADR in the same PR.

## When to offer an ADR

Offer an ADR only when a decision clears all three bars:

1. **Hard to reverse** — undoing it later means a migration, a data rewrite, or churning many call
   sites, not flipping a flag.
2. **Surprising** — a competent newcomer would reasonably expect the opposite, so the choice needs a
   recorded rationale to survive.
3. **A real trade-off** — we gave up something concrete (portability, flexibility, idiomatic
   convention) to get something concrete; both sides are worth naming.

If a decision is none of these, it's just code — don't write an ADR for it.

## Format

Each ADR is one tight file: a decision-shaped H1 title, one short paragraph (1–3 sentences) giving
the context, what we decided, and why — including the rejected alternative — and a one-line footer.

```md
# {Short decision-shaped title}

{1–3 sentences: the context, what we decided, and why — including the rejected alternative.}

> Status: accepted · Source: {roadmap §X / issue #N / CLAUDE.md / memory}
```

No Status/Options/Consequences sections — keep it to the paragraph unless extra structure genuinely
earns its place. Use repo vocabulary (Persona, Scene, Round, seam, Action); don't redefine terms.
ADRs derived from the roadmap that name specific models/fields carry a "verify against code" note —
treat those names as hints to confirm, not gospel.

## Index

### Architecture & seams
- [0001 — Action-centric dispatch through the player-action seam](0001-action-centric-dispatch-through-the-player-action-seam.md)
- [0002 — One round framework, three modes, as the shared RoundContext seam](0002-one-round-framework-three-modes.md)
- [0003 — Combat action economy: one focused + up to two secondary actions](0003-combat-action-economy-one-focused-two-secondary.md)
- [0004 — Tempo is action-driven, never wall-clock (AFK-safe)](0004-tempo-is-action-driven-never-wall-clock.md)
- [0005 — Reactive behavior is a separate flows/triggers/events engine](0005-reactive-behavior-is-a-separate-flows-engine.md)
- [0006 — Scenes are provisional by default; never auto-persist RP](0006-scenes-are-provisional-never-auto-persist-rp.md)
- [0091 — GANG_TURF resolves TIERED_PERIOD via a per-kind resolver registry, not a shared accessor](0091-gang-turf-tiered-period.md)

### Database & modeling
- [0007 — No JSON fields; every setting is a typed, queryable column](0007-no-json-fields-typed-queryable-columns.md)
- [0008 — All concrete models use SharedMemoryModel](0008-all-concrete-models-use-sharedmemorymodel.md)
- [0009 — No Django signals; explicit service-function calls](0009-no-django-signals-explicit-service-functions.md)
- [0010 — FK direction is specific→general; avoid FKs to ObjectDB](0010-fk-direction-specific-to-general.md)
- [0011 — IC-meaningful state keys on CharacterSheet/Persona, never AccountDB](0011-ic-state-keys-on-charactersheet-not-account.md)
- [0012 — PostgreSQL-only in production; use PG features directly](0012-postgresql-only-in-production.md)
- [0013 — Schema-only migrations pre-production](0013-schema-only-migrations-pre-production.md)
- [0014 — No persisted derived data; derive-on-read](0014-no-persisted-derived-data-derive-on-read.md)
- [0015 — No polymorphic / GenericFK / ContentType models](0015-no-polymorphic-genericfk-models.md)
- [0016 — One shared base per concept; no parallel implementations](0016-one-shared-base-per-concept.md)
- [0093 — Service functions read through cached handlers, not bare ORM queries](0093-service-functions-use-cached-handlers-not-queries.md)
- [0017 — New subsystems are submodules of existing apps](0017-new-subsystems-are-submodules.md)
- [0018 — Range-partition the Interaction table](0018-range-partition-the-interaction-table.md)
- [0062 — The Secret↔act anchor puts the FK on the Secret, reversing the back-reference pattern](0062-secret-act-anchor-reverses-the-back-reference-fk.md)

### Resolution
- [0019 — Unified resolution: one roll path, data-sourced difficulty, graded outcomes](0019-unified-resolution-one-roll-path.md)

### Process & workflow
- [0020 — Feature specs live in the GitHub issue body, gated by labels](0020-feature-specs-live-in-the-issue-body.md)
- [0021 — main uses a GitHub merge queue + single-leaf migration guard](0021-main-uses-a-merge-queue.md)
- [0022 — Staff config & game-tuning tooling is admin-hosted, not React](0022-staff-tooling-is-admin-hosted.md)
- [0093 — Game Tuning/Ops dashboards stay on the stock ArxAdminSite with django-htmx, not django-unfold](0093-admin-hosted-tuning-dashboard-htmx-without-unfold.md) (narrows ADR-0022's implementation detail)
- [0083 — CI/test databases build schema from model state; migration replay runs nightly only](0083-ci-schema-from-models.md)
- [0084 — SQLite fast tier restores a cached schema template instead of rebuilding per run](0084-sqlite-test-schema-template-cache.md)

### Game-design tenets
- [0023 — PvP is structurally non-lethal](0023-pvp-is-structurally-non-lethal.md)
- [0024 — Consent gates behavior-altering effects, not benefit](0024-consent-gates-behavior-altering-effects.md)
- [0025 — Never parse pose text for mechanics](0025-never-parse-pose-text-for-mechanics.md)
- [0026 — The watched player is always OOC-aware](0026-the-watched-player-is-always-ooc-aware.md) (see also ADR-0083)
- [0027 — Visibility = eligibility: one predicate, no locked options](0027-visibility-equals-eligibility.md)
- [0028 — Web-first: not wired into React = not implemented](0028-web-first-not-wired-into-react-is-not-implemented.md)
- [0029 — Named/public faces are always shown by name](0029-named-public-faces-are-always-shown-by-name.md)
- [0030 — GMs author story trees; outcomes resolve by player roll, not fiat](0030-gms-author-story-trees-outcomes-resolve-by-roll.md)
- [0031 — Exact numbers in the ledger, descriptive labels in the fiction](0031-exact-numbers-in-the-ledger-labels-in-the-fiction.md)
- [0032 — Constrained bystander reactions](0032-constrained-bystander-reactions.md)
- [0033 — Privacy / RP-leak prevention is MVP-gating](0033-privacy-is-mvp-gating.md)
- [0034 — Mechanics individualize characters](0034-mechanics-individualize-characters.md)
- [0035 — Default to the high-drama / ceremony path](0035-default-to-the-high-drama-ceremony-path.md)
- [0036 — Combat merits Legend, never XP](0036-combat-merits-legend-never-xp.md)
- [0037 — Encounter difficulty scales on party size + average level only](0037-encounter-difficulty-scales-on-party-size-and-level.md)
- [0038 — Asymmetrical PvE; NPCs have no character sheets](0038-asymmetrical-pve-npcs-have-no-sheets.md)
- [0039 — Bulk resolution uses honest terminal states](0039-bulk-resolution-uses-honest-terminal-states.md)
- [0066 — Legend is earned only from difficult victories](0066-legend-earned-only-from-difficult-victories.md)

### Domain architecture
- [0040 — Incapacitation & dying decoupled from a single vitals enum](0040-incapacitation-and-dying-decoupled-from-vitals.md)
- [0041 — Resonance is earned from being perceived, not from casting](0041-resonance-is-earned-from-being-perceived.md)
- [0042 — Covenants are group-only (min 2 members)](0042-covenants-are-group-only.md)
- [0043 — CovenantRole and CovenantRank are orthogonal axes](0043-covenant-role-and-rank-are-orthogonal.md)
- [0044 — Covenant sworn objective is recorded as free text](0044-covenant-sworn-objective-is-free-text.md)
- [0045 — Multi-target casts validate a target list with per-target consent](0045-multi-target-casts-with-per-target-consent.md)
- [0046 — Power-tier breakthroughs gate at fixed path thresholds](0046-power-tier-breakthroughs-gate-at-fixed-thresholds.md)
- [0047 — STRICT rounds resolve on a quorum; an AFK participant's own peril is skipped on the END tick](0047-quorum-resolution-for-strict-rounds-afk-own-peril-skip.md)
- [0048 — Custom action resolvers for non-template consent actions](0048-custom-action-resolvers-for-non-template-consent-actions.md)
- [0049 — Acute peril resolves through a guarded consequence pool, never unconditional death](0049-acute-peril-resolves-through-guarded-consequence-pool.md)
- [0057 — Covenant of the Court: a leader and their retinue, as a third covenant type](0057-retinue-covenants-leader-plus-subordinates.md)
- [0058 — NPC disposition is two-tier: ephemeral for mooks, durable for named NPCs, with persona-promotion as the seam](0058-npc-disposition-is-two-tier-ephemeral-and-durable.md)
- [0059 — Allegiance is the unified substrate for summons and future charm/switch-sides](0059-allegiance-is-the-summon-charm-substrate.md)
- [0060 — Reactive defenses are mutation-only DAMAGE_PRE_APPLY flow handlers with a shared anima-cost pattern](0060-reactive-defenses-are-mutation-only-flow-handlers.md)
- [0061 — Access-change fires one shared surface; discoverability is a shared abstract base](0061-access-change-fires-one-surface-discoverable-is-shared-base.md)
- [0069 — Succor is a RoundContext capability; location shelter is a hard gate, not arithmetic resistance](0069-succor-roundcontext-capability.md)
- [0070 — NPC ontology: Functionary, Standing, and Story NPCs as class-1..4](0070-npc-ontology-functionary-standing-story.md)
- [0073 — Environmental vulnerabilities are ConditionDamageOverTime rows riding the peril pipeline](0073-environmental-vulnerabilities-are-dot-rows-riding-the-peril-pipeline.md)
- [0074 — Battle Surrounded peril may override AFK-safety, narrowly and explicitly](0074-battle-peril-may-override-afk-safety-narrowly.md)
- [0081 — Battle terrain lives on BattlePlace, not the room Position/PositionEdge graph](0081-battle-terrain-lives-on-battleplace.md)
- [0082 — Battle morale derives status; the front itself is the objective; VP stays award-only](0082-battle-morale-derives-status-objective-lives-on-place.md)
- [0083 — Siege structures are per-Fortification objectives; BREACH/FORTIFY are dedicated verbs](0083-siege-structures-are-per-fortification-objectives-with-dedicated-verbs.md)
- [0083 — Out-of-combat sudden harm defers via the scene-round declare/resolve shape, not a pre-armed check](0083-out-of-combat-sudden-harm-defers-via-scene-round.md)
- [0083 — Concealment carries an OOC-only, identity-free "someone is watching" guarantee, separate from IC detection](0083-concealment-ooc-observer-transparency.md) (see also ADR-0026)
- [0084 — Battle environment reads ambient weather via Battle.region, not the room graph](0084-battle-environment-reads-ambient-weather-via-battle-region.md)
- [0085 — BattlePlace gains internal battle-map coordinates, additive to ADR-0081](0085-battleplace-internal-battle-map-coordinates.md)
- [0085 — NPCStanding carries debt and petition-failure-streak, not CourtPact](0085-npcstanding-debt-and-petition-streak-are-generic.md)
- [0091 — instantiate_situation mints Challenges via an authored target-object name; GM triggers it with a plain staff Action](0091-instantiate-situation-mints-challenges-gm-trigger.md) (supersedes ADR-0090)
- [0095 — Battle live updates are a slim BATTLE_STATE ping plus REST refetch, not a full-state WS payload](0095-battle-live-updates-are-ping-plus-refetch.md)

### Gift & resonance economy
- [0050 — Gifts are Major or Minor; species abilities are a species-granted Minor Gift](0050-gifts-are-major-or-minor-species-abilities-are-minor-gifts.md)
- [0051 — Gift strength comes from the thread woven into it (the costliest thread kind)](0051-gift-strength-comes-from-the-woven-thread.md)
- [0052 — A gift's resonance is the resonance of its woven thread](0052-gift-resonance-is-the-woven-threads-resonance.md)
- [0053 — XP buys unlocks that gate acquisition, never grant it](0053-xp-buys-unlocks-that-gate-never-grant.md)
- [0054 — Falling gains power; redemption is lossy (asymmetric resonance conversion)](0054-falling-gains-power-redemption-is-lossy.md)
- [0055 — One specialization engine: resonance × entity → customized techniques (Gift, Path, Covenant Role)](0055-one-specialization-engine-resonance-times-entity.md)
- [0056 — Technique-threads are an optional "signature" axis, distinct from the gift-thread](0056-technique-threads-are-an-optional-signature-axis.md)
- [0071 — Species-gift drawbacks are conditions the gift's own thread mitigates](0071-species-gift-drawbacks-mitigated-by-gift-thread.md)
- [0072 — Signature motif bonus is an additive flourish, not a discovered TechniqueVariant](0072-signature-motif-bonus-is-additive-not-a-variant.md)
- [0086 — Thread pulls are target-aware via a per-target_kind modulation seam; regard attaches to the pull, not the Prerequisite system](0086-target-aware-pulls-court-regard-modulation-seam.md)
- [0087 — Touchstone dynamic resonance-match via in-place RitualComponentRequirement extension](0087-touchstone-dynamic-resonance-match.md)
- [0092 — Relationship Bond Pull Modulation is unsigned and saturating, deliberately diverging from Court Regard Modulation's signed-ratio shape](0092-relationship-bond-pull-modulation-is-unsigned-and-saturating.md)
- [0094 — Thread crossing ceremonies: every kind gets a resonance-matched personalization beat](0094-thread-crossing-ceremonies-every-kind-gets-a-beat.md)
- [0063 — The level-3 (Prospect→Potential) semi-crossing lives in the Ritual of the Durance, not Audere Majora](0063-level-3-semi-crossing-lives-in-the-durance.md)
- [0064 — Dispel is a technique payload row, not an EffectKind (thread-pull) entry](0064-dispel-is-a-technique-payload-not-an-effectkind.md)
- [0065 — A trainer-of-record bound to a room (DuranceTrainingSite) enables automated self-conduct of the Ritual of the Durance from telnet](0065-durance-trainer-of-record-enables-automated-self-conduct.md)

### Story & stakes
- [0067 — Beat.risk is the stakes-wager declaration](0067-beat-risk-is-the-stakes-wager-declaration.md)
- [0068 — Graded beat/encounter outcome reuses CheckOutcome, not a new enum](0068-graded-beat-outcome-reuses-checkoutcome.md)
- [0075 — Building size is a space budget rooms spend from, not a flat room cap](0075-building-target-size-is-a-space-budget.md)
- [0076 — Removal-from-play is reached through the fuse walk, never granted by fiat](0076-removal-from-play-is-reached-through-the-fuse-walk.md)
- [0077 — Effective risk is priced relative to declared target level, not the raw declared tier](0077-effective-risk-is-priced-relative-to-target-level.md)
- [0078 — Stakes are menu-first, calibrated by band, not freehand-authored per table](0078-menu-first-stakes-with-calibration-bands.md)
- [0079 — Style discovery rides the clue→codex→RESEARCH pipeline, not a parallel unlock model](0079-style-discovery-rides-the-clue-research-pipeline.md)
- [0080 — Heat jurisdiction is judged at the commit location, enforcement scoped to the dominant society](0080-heat-jurisdiction-judged-at-the-commit-location.md)
- [0081 — Org income requires active collection; idle approaches stasis, never decay](0081-income-requires-collection.md)
- [0082 — Scandal is a derived per-society judgment; reach forks at act birth](0082-scandal-reach-derived-at-act-birth.md)
- [0085 — The offer→staked-beat link lives on MissionOfferDetails, not NPCServiceOffer](0085-offer-to-beat-link-on-missionofferdetails.md)
- [0087 — Building renovation swaps the catalog BuildingKind row, not per-building flags](0087-building-renovation-catalog-kind-reassignment.md)
- [0095 — GM trust is `GMProfile.level`, capped by `GMLevelCap`, advanced only via `promote_gm`](0095-gm-trust-is-gmprofile-level.md)
