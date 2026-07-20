# Situational-perk machinery, slice 1: registry pattern, beneficiary evaluation point, dual-dispatch announce

ADR-0149 named Layer 4 of the four-layer vow-power model — "the point of vows": when the
situation a vow exists for arises, the holder shines deterministically and legibly (#2536).
This slice (1 of 3) ships the machinery: the situation library + evaluator registry, the perk
authoring models, `POWER_BONUS`/`CHECK_BONUS` delivery, and the presentation contract. It
records the decisions worth keeping, not a restatement of the spec (`gh issue view 2536`).

## Situation-library registry pattern

`Situation` (`world.covenants.perks.constants`) is a code-defined `TextChoices` — ruling 5 from
the issue: situations are hardcoded labels with precise, testable semantics; attaching them to
perks and tuning magnitudes is a content edit forever after, but adding a NEW situation is a
one-line enum value + a registered evaluator, always a code change. `SITUATION_EVALUATORS`
(`world.covenants.perks.evaluators`) mirrors the existing `_PROVIDERS` registry pattern in
`magic.services.power_terms` — a `dict[str, Callable[[SituationContext], bool]]` populated by a
`@register(situation)` decorator, one function per enum value, each a pure read (one query or a
cached-handler read, never a write) that returns `False` on missing/absent context rather than
raising. The enum ships **no inert values** — slice 1's 9 situations (`AT_RANGE`/`IN_MELEE`/
`SURROUNDED`/`TARGET_DISTRACTED`/`TARGET_SWAYED_BY_ALLY`/`TARGET_FOCUSED_ELSEWHERE`/
`ALLY_LOW_HEALTH`/`DURING_NEGOTIATION`/`TARGET_FAVORABLY_DISPOSED`) all have a shipped
evaluator; `combat_opened_from_parley`/`ambush_underway`/`ally_intercepted_for_me`/
`attacker_abyssal` were deliberately deferred (see "Slice-1 deferrals" below) rather than added
as dead enum entries with no evaluator.

## Beneficiary evaluation point

Perks are evaluated at the ACTING character's (the "subject's") resolution moment, never on the
perk-holder's own timer — `applicable_perks(subject, *, effect_kind, resolution, target)`
(`world.covenants.perks.services`) is the single entry point every delivery seam calls. The
candidate set unions the subject's own engaged roles (`SELF`/`WHOLE_GROUP` perks — anchor AND
resolved sub-role both apply, ADD semantics) with engaged covenant-mates' engaged roles
(`COVENANT_ALLIES`/`WHOLE_GROUP` perks). This is computed with a query ceiling independent of
how many perks/situations/rungs exist or how many mates are present (see
`applicable_perks`'s module docstring for the exact ceilings, tested by
`PerkResolutionQueryBudgetTests`/`AllyMateCountQueryBudgetTests`) — the no-queries-in-loops rule
holds even as content grows.

**"Covenant-mate" is answered two different ways for two different questions, deliberately.**
Group membership for perk beneficiaries requires BOTH an active `engaged` role in a shared
covenant AND physical co-presence for this resolution (same combat encounter's active roster in
combat; same active `Scene` otherwise) — perks are a benefit of active, present vows, not of
merely sharing a covenant. Provenance situations (`target_swayed_by_ally`) read a different,
narrower question on purpose: who applied a condition is a past fact about the moment it
landed, not a claim about right-now engagement or presence, so that evaluator uses
`Character.shares_covenant_with` (active membership only) instead of the co-presence rule. See
`world.covenants.perks.services`'s module docstring ("What counts as a covenant-mate") for the
full reasoning — this split is intentional, not an inconsistency to fix.

## Announce dual-dispatch — why `broadcast_action_outcome` alone was insufficient

Ruling 1 (HARD): a firing perk must be a loud, visible moment in BOTH the web client and bare
telnet. Combat already had a narration-broadcast path — `broadcast_action_outcome`
(`world.combat.interaction_services`) — but it is WS-only: it persists a Narrator-authored
`Interaction` and pushes the WS payload to the room, with no text companion, so a telnet
session sees nothing. Reusing it as-is for perk announces would have silently broken telnet
parity for this feature specifically, which is why the spec calls the gap out explicitly.
`announce_fired_perks` (`world.covenants.perks.services`, Task 6) keeps the same
persisted-Interaction + WS-broadcast machinery (so the announce still shows up in the scene log
and pushes over the same channel every other narrated moment uses) but ADDS a text companion
delivered by calling `location.msg_contents(text)` directly (a review-cycle fix — the pairing
precedent `world.scenes.interaction_views`' pose-create view follows, sending
`flows.service_functions.communication.message_location` alongside its WS-visible persisted row
"for telnet clients (WS parity)," does NOT transfer here as-is: `message_location` resolves its
broadcast room from its *caller's own* location, and this seam has no single acting character
reliably co-located with the room a perk fires in — a group-beneficiary firing may name a
`holder` elsewhere. The initial Task 6 implementation built a caller state from the singleton
Narrator persona's own character, whose location is unrelated to the fired-perk room and is
often unset; that shipped telnet delivery as a silent no-op, caught on the Task 6 review and
fixed by broadcasting to the caller-supplied `location` directly instead, mirroring
`world.combat.escalation`'s caller-less room-wide surge narration). Each rendered line is
prefixed with the firing perk's `name`
(the model's own "announced label," e.g. "Scout's Instinct") ahead of the templated
`{holder}`/`{subject}` line, mirroring the spec's presentation example, so two different perks
firing for one character stay distinguishable in the announce text itself — not only in the
(currently un-labeled, see below) power/check ledger.

**Call-site discipline, not loop-internal dedup, prevents double-announcing.** `announce_fired_perks`
is called from inside each delivery provider (`vow_situational_power_term` for `POWER_BONUS`,
`_situational_perk_check_bonus` for `CHECK_BONUS`) immediately after `applicable_perks` returns,
never from `applicable_perks` itself — `applicable_perks` may legitimately be called more than
once for a single player action (an offense check and a separate penetration check are two
distinct resolutions within one combat action, each entitled to its own announce). Both wired
providers are verified single-call-per-resolution: `_derive_power` is invoked exactly once
inside `use_technique`'s orchestration (the one production entry point for a cast), and a
production `perform_check` call computes its breakdown exactly once (the test-rig
forced-outcome branch and the normal-roll branch are mutually exclusive). A perk's `effect_kind`
is also a single value, so the same perk row can never fire from both seams for one resolution.

**Ledger attributability is a known, documented slice-2+ gap.** Spec §5 asks for the power/check
ledger's TERM-stage contribution to carry the firing perk's name (a `FLAT_MODIFIER`-style
dynamic per-source label), not the situational-perk provider's own static function-name label.
`_derive_power`'s TERM loop calls its per-provider label function once per provider, not once
per return value, so a provider that sums several perks internally has no channel to report
which one produced how much of the total — the SAME limitation every other multi-source
provider in that file already has (`covenant_role_blend_power_term`,
`covenant_role_specialty_power_term`). This slice does not refactor the ledger; the per-perk
name reaches the player through the announce line instead, which is the loud, attributable
moment ruling 1 actually asks for. A future ledger refactor to dynamic per-source TERM labels
is a legitimate slice-2+ item if staff want perk names in the breakdown UI too.

## Query-ceiling posture

Every layer introduced this slice keeps a documented, tested, FIXED query ceiling independent of
content volume: `applicable_perks` (ceiling 6 in the worst common shape — see its module
docstring), the evaluator registry (each evaluator is one query or a cached-handler read, never
a query per situation-per-perk), and the delivery seams (`vow_situational_power_term`/
`_situational_perk_check_bonus` each call `applicable_perks` once). This matters because perk
content is expected to grow substantially post-launch (every vow eventually gets several
situational perks) — a per-perk or per-situation query would turn combat resolution into an
N+1 as content scales; the ceiling holds that flat regardless of authored volume.

## Slice-1 deferrals

- **`TIER_FLOOR`/`BOTCH_IMMUNITY`** (`PerkEffectKind`) — schema ships now (all four values), but
  neither is read by any resolution seam yet. Ruling 3's outcome-guarantee principle (a
  character's specialization shouldn't be able to botch at it) ships as slice 2, wired into
  `perform_check`'s outcome resolution.
- **`combat_opened_from_parley`/`ambush_underway`/`ally_intercepted_for_me`/`attacker_abyssal`**
  (situations) — each needs machinery that doesn't exist yet (an encounter origin marker for the
  negotiation→combat transition; event-scoped ambush state; the ADR-0118 guardian-reaction seam;
  the defense-side evaluation point for incoming-attack context) and ships alongside that
  machinery in a later slice, per the issue's explicit slicing note. The enum does not carry
  these as inert values in the meantime.
- **Court/Battle scoping + dormant-vow messaging** — slice 3. `perform_check`'s `situation_ctx`
  threading already reaches mission and battle check contexts structurally (any call site that
  constructs a `SituationContext` and passes it), but no Court/Battle-specific situation or
  content exists yet.

> Status: accepted · Source: issue #2536 (slice 1 of 3) · Related: ADR-0149 (four-layer vow-power
> model — Layer 4), ADR-0055 (sub-role specialization — perk ADD-not-replace semantics mirror
> `CovenantRoleTechniqueSpecialty`'s Layer 2 precedent), ADR-0118 (guardian reaction seam — informs
> the deferred `ally_intercepted_for_me` situation), #2183 (technique-entrance `from_entrance`
> marker — the precedent the deferred `combat_opened_from_parley` transition will follow)
