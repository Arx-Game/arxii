# Outcome guarantees (TIER_FLOOR / BOTCH_IMMUNITY) are absolute floors, not scaled bonuses

ADR-0151 shipped Layer 4's machinery with `TIER_FLOOR`/`BOTCH_IMMUNITY` schema-only. This slice
(2 of 3, #2536) wires both into `perform_check`'s outcome resolution — Apostate's can't-botch
principle (ruling 3): a character's specialization shouldn't be able to botch at the thing their
vow is specifically for. `TIER_FLOOR`'s floor is a new first-class authored column,
`VowSituationalPerk.floor_success_level` (`SmallIntegerField`, canonical −10..+10 `success_level`
scale, `clean()`-required on `TIER_FLOOR` rows and rejected on every other `effect_kind`) — NOT a
reuse of the existing `magnitude_tenths` field that `POWER_BONUS`/`CHECK_BONUS` thread-scale.
Rejected: overloading `magnitude_tenths` for the floor would silently thread-scale a guarantee
that spec §6 requires to be absolute — a low-thread holder's "can't botch" would erode exactly
when they need it least. `BOTCH_IMMUNITY` uses the same floor mechanism (no field of its own): it
binds only when the raw outcome is already a botch (`success_level <=
world.checks.constants.BOTCH_SUCCESS_LEVEL_MAX`, a new module constant centralizing a boundary
`world.magic.services.sanctum_install` previously declared locally as
`CRITICAL_FAILURE_SUCCESS_LEVEL = -2`) and floors it at the least-bad non-botch level
(`BOTCH_SUCCESS_LEVEL_MAX + 1`). Both guarantees fire through `applicable_perks` in one call
(`effect_kind=(TIER_FLOOR, BOTCH_IMMUNITY)`, the new tuple-accepting form — same fixed query
ceiling as a single-kind call) and are ungated: no thread-level scaling, no thread-level
minimum, per the 2026-07-20 ruling.

Guarantees apply on both the real dice-roll path and the test-rig forced-outcome path
(`force_check_outcome`) — `_apply_outcome_guarantees` is called from both `perform_check` and
`_build_forced_check_result`, so a forced botch through a botch-immune character's check comes
out a plain failure deterministically, not just under real rolls. They announce
(`announce_fired_perks`) only when a guarantee actually altered the resolved outcome — rejected:
announce-on-fire (calling `applicable_perks` found a matching perk) regardless of whether it
bound, which would spam every check a `TIER_FLOOR`/`BOTCH_IMMUNITY` perk is merely *eligible*
for (the common case, since most rolls already land above the floor) rather than the rare case
where the guarantee actually mattered.

**Amends ADR-0151.** Slice 1 recorded "Covenant-mate" group-membership scoping as requiring the
candidate mate's OWN `CharacterCovenantRole.engaged=True` flag, alongside co-presence. This slice
reverses that rule (Tehom, 2026-07-20): a candidate mate now counts if they hold a non-departed
role (`left_at__isnull=True`) in a covenant the ACTING character is actively engaged in AND are
co-present in the resolution's roster — the mate's OWN `engaged` flag is irrelevant. Rationale:
a KO'd or disengaged covenant-mate still in the fight must keep contributing `COVENANT_ALLIES`/
`WHOLE_GROUP` perks, so losing allies mid-encounter never weakens the survivors (no
death-spiral) — "Last Bulwark"-style perks must fire hardest exactly when mates are going down,
not stop firing the moment they do. The ACTING character's own engagement is untouched by this
reversal (the stark-power rule: receiving group perks is a benefit of the actor's own active
vow, not the mate's) — `test_unengaged_role_grants_no_perks` still holds. Co-presence is
unaffected too: a mate who FLED/was REMOVED from the encounter still drops out of the group.
`evaluators.ally_low_health` and `services._ally_candidates`/`_group_sheet_ids` both apply the
reversed rule identically (they deliberately mirror each other); `evaluators
.target_swayed_by_ally`'s provenance question (`shares_covenant_with`, active membership only)
is untouched — it was never the engaged+co-present rule to begin with.

> Status: accepted · Source: issue #2536 (slice 2 of 3) · Amends: ADR-0151 (covenant-mate
> group-membership scoping) · Related: ADR-0149 (four-layer vow-power model — Layer 4)
