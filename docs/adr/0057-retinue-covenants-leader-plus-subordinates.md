# Covenant of the Court: a leader and their retinue, as a third covenant type

A powerful character whose strength is partly tied to a covenant **role** but who has no peers can
still hold one by forming a **Court** — a third covenant type alongside the Covenant of the Durance
and the Covenant of War, modelling a single powerful leader and the servants/apprentices/acolytes
sworn to them across a wide power gulf — by design at least one power tier (ADR-0046) separates the
Court leader from their servants — explicitly **not** a co-adventuring party (e.g. "the Court of
Shadows" serving the Shadowlord; the "henchperson to a remote master" fantasy). We add it as a new
`CovenantType` value (`COURT`) on the existing `Covenant` model and **reuse** the existing pieces — the
`CovenantRank` authority ladder already models one leader (founder, tier 1) over Member-tier
underlings, and role power is already per-character and peer-independent (`CovenantRoleBonus` scales on
the holder's own level), so the leader's role still specializes by resonance/thread through the one
engine (`resolve_effective_role`, ADR-0055); Court-specific roles are authored `CovenantRole` rows
scoped by covenant_type. We rejected a new model, a new hierarchy field, and a plain `Organization` —
the first two already exist, and a Court needs covenant-only machinery (sworn oath, role power,
thread/resonance specialization, Legend), so a covenant type avoids a parallel implementation
(ADR-0016). It is **not** `MentorBond`, which is a combat-adjacency level-clamp for a co-present,
in-band pair — the opposite of a never-level-adjacent master. ADR-0042's min-2 floor **stands**: a
Court is a leader + ≥1 retained member (and auto-dissolves if all leave); we deliberately do not carve
a covenant-of-one exception. Role/rank orthogonality (ADR-0043) is what makes it work — the master
holds high role power *and* top rank authority while servants hold lesser roles — and no
`is_leadership` flag returns.

> Status: accepted · amended 2026-06-30 (#1589) — verified against code · Source: design discussion 2026-06-27 · Confidence: high — `CovenantType.COURT`, `Covenant.leader`, `CourtPact`, `swear_court_pact`, `power_tier_for_level`, `has_active_court_mission` all in `world/covenants/`

## Amendment (2026-06-30, #1589 implementation)

All claims below were verified against `src/world/covenants/` on this branch before writing.

**`leader` FK binding:** `Covenant` now carries a `leader` FK → `character_sheets.CharacterSheet`
(`null=True`, `on_delete=SET_NULL`, `related_name="led_courts"`), validated in `Covenant.clean()`
(required for COURT; forbidden for other types). This is the structural analogue of `campaign_story`
on Battle covenants — a per-instance binding that names the master. `create_covenant(leader=...)`
is the creation path. An NPC master is an account-less `CharacterSheet` seated as the `is_leader`
founder; the min-2 floor stands and the Court auto-dissolves when the last servant leaves.

**`CourtPact` model (new) — grant axis, SUPERSEDES "peer-independent" framing:** A new `CourtPact`
model (`world/covenants/models.py`) records the per-(Court, servant) sworn-fealty bond. Active =
`released_at IS NULL`; partial-unique on `(covenant, servant_sheet)` when active; released pacts
are retained as an audit trail. Key field: `granted_pull_cap` (PositiveSmallIntegerField) — a
master-set ceiling on the servant's Court-role thread pull level. **This supersedes the original
ADR framing that "role power is peer-independent / not a level-clamp"**: a Court servant's effective
combat pull is now bounded by what the master granted, so the servant's power is "own level PLUS
what the master grants via the cap." It is still NOT `MentorBond`'s level-clamp — it is a separate
grant axis on the thread-pull cap rather than a level adjustment, and the master remains
never-level-adjacent. The grant is the gate: a servant with no active pact has an effective cap of 0
(there is no `CourtPact` row to read) and cannot pull their Court-role thread. Services: `swear_court_pact(*, covenant, servant_sheet,
granted_pull_cap) -> CourtPact`, `release_court_pact(*, pact) -> None`, `active_court_pact_for(*,
covenant, servant_sheet) -> CourtPact | None`. The cap is enforced inside `compute_anchor_cap`
(`world/magic/services/threads.py`) via `_bound_covenant_role_cap_by_court_grant`.

**≥1-tier gulf now ENFORCED:** The ≥1 power-tier gulf is no longer purely narrative — it is
enforced at join by the COURT arm of `assert_membership_level_allowed`
(`world/covenants/mentorship.py`). The helper `power_tier_for_level(level) -> int`
(`world/covenants/power_tier.py`) maps levels 1–5 → tier 1, 6–10 → tier 2, 11–15 → tier 3, etc.
(band width = `TIER_ONE_MAX_LEVEL` = 5). `CourtGulfViolationError` is raised if
`power_tier_for_level(servant) >= power_tier_for_level(leader)`.

**Mission-driven engagement (new machinery):** The COURT arm of `can_engage_membership`
(`world/covenants/handlers.py`) gates engagement on `has_active_court_mission(character_sheet,
covenant)` (`world/covenants/court_missions.py`) — True iff the character participates in an ACTIVE
`MissionInstance` whose `source_offer.role.faction_affiliation_id` matches
`covenant.organization_id`. The mission (not co-presence) is the engagement gate. This is new
context-gate machinery, not a mirror of Battle covenants, whose engagement gate is simply
`not is_dormant`.

**Fealty ceremony extended:** `induct_member_via_session` (fire-handler) was extended to swear the
`CourtPact` for COURT covenants, reading `granted_pull_cap` from `participant_kwargs`, and emits
a servant-spotlight narration alongside the induction message.
