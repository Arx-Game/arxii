"""Perk resolution service for per-vow situational perks (#2536, Task 3).

``applicable_perks`` decides WHICH perks fire for one acting character's
resolution (a cast or a check) — the piece every seam (Tasks 4-6: the
``POWER_BONUS``/``CHECK_BONUS`` providers, the announce path) calls into.
Nothing in this module writes; it is a pure read that returns the fired set
for the caller to apply.

## What counts as a covenant-mate

Two different modules answer "who is a covenant-mate" for two different
questions, deliberately differently:

- **Group membership for perk beneficiaries** (this module's
  ``applicable_perks``, and ``evaluators.ally_low_health``, which this module
  matches on purpose): a covenant-mate is a character who BOTH (a) holds a
  non-departed role (``CharacterCovenantRole.left_at__isnull=True``) in a
  covenant the ACTING character is actively engaged in, AND (b) is co-present
  with the acting character for this resolution — the same combat encounter's
  active roster in combat, the same active Scene otherwise (see
  ``_group_sheet_ids``). The MATE's own ``engaged`` flag is irrelevant
  (Tehom's 2026-07-20 reversal of the slice-1 rule): a KO'd or disengaged
  covenant-mate who is still in the encounter keeps contributing their group
  perks, so losing allies mid-fight never weakens the survivors — no
  death-spiral. The SUBJECT's own engagement is still required (stark-power
  ruling, untouched): receiving group perks is a benefit of the ACTING
  character's own active vow, not of the mate's. Leaving the encounter
  (FLED/REMOVED, or absent from the scene) still drops a mate from the group
  — co-presence is unaffected by this reversal.
- **Provenance situations** (``evaluators.target_swayed_by_ally``)
  legitimately read HISTORY instead of live group membership: who applied a
  condition is a past fact about the moment it landed, not a claim about
  right-now presence or engagement. The applier's current engagement state
  does not retroactively un-charm the target — a covenant-mate who has since
  disengaged their vow (or wandered off to another scene) still "swayed for
  the team" for a condition they already applied. ``target_swayed_by_ally``
  therefore uses ``Character.shares_covenant_with`` (ACTIVE membership only,
  no engagement or co-presence requirement), not the rule above.

Both halves are deliberate — see the one-line cross-reference comment at
``evaluators.target_swayed_by_ally``.

## Beneficiary evaluation point (spec §2)

Perks are evaluated at the ACTING character's (the ``subject``'s) resolution
moment, never on the perk-holder's own timer. The candidate set is:

- ``SELF``/``WHOLE_GROUP`` perks on the subject's own engaged roles (anchor
  AND resolved sub-role both apply — sub-role perks ADD, never replace).
- ``COVENANT_ALLIES``/``WHOLE_GROUP`` perks on a co-present covenant-mate's
  (see above — the mate's own engagement is irrelevant) role — anchor AND
  the mate's own resolved sub-role both apply, same ADD semantics as the
  subject's own roles (a mate's level-3+ sub-role vow perk must be able to
  fire for the group, not just their base vow — see
  ``_ally_sub_role_candidates``).

``COVENANT_ALLIES`` never fires for the holder's own action because the
subject is structurally excluded from being counted as their own covenant-
mate; ``WHOLE_GROUP`` fires for both cases (the holder's own action via the
first bullet, a mate's action via the second) — "includes the holder."

## Query discipline

Every step below is a small, FIXED number of queries independent of how many
perks/situations/rungs/mates are authored: one query for the subject's own
active memberships (cached per-character by the covenant-roles handler), a
bounded number of resolve calls for the subject's own engaged roles (scales
with the subject's OWN role count, not perk count), one query for the
co-presence roster, one query for the batched ally ``CharacterCovenantRole``
fetch (with ``select_related("covenant_role")`` so the anchor role rides the
same query — no per-mate follow-up), one query for the batched ally
COVENANT_ROLE ``Thread`` fetch across every mate at once (see
``_ally_sub_role_candidates``), a bounded number of ``CovenantRole
.matching_variant`` resolve calls — one per DISTINCT anchor role held among
the group's mates (SharedMemoryModel's identity map de-dupes mates sharing
the same role to one Python instance, so this scales with role DIVERSITY in
the group, never with mate COUNT), and ONE query (plus 2 prefetch queries —
``situations``, ``rungs``, only issued when at least one candidate perk
matches) for the candidate-perk fetch regardless of how many perks match.
The candidate-perk fetch group is fixed at UP TO 3 queries (base + 2
prefetches) in every shape; the documented CEILING for the full
``applicable_perks`` pipeline in the worst common shape (allies present, a
matching perk, one shared anchor role among the mates) is **6** — see
``test_perk_resolution.PerkResolutionQueryBudgetTests`` (perk-count
invariance, self-only shape, ceiling 3) and
``test_perk_resolution.AllyMateCountQueryBudgetTests`` (mate-count
invariance, 2 vs 5 mates on one shared role, ceiling 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.core.exceptions import ObjectDoesNotExist

from world.covenants.perks.constants import PerkBeneficiary
from world.covenants.perks.context import SituationContext
from world.covenants.perks.evaluators import SITUATION_EVALUATORS

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import CharacterCovenantRole, VowSituationalPerk
    from world.missions.models import MissionInstance

#: Beneficiaries that fire on the perk-owning holder's OWN action.
_SELF_BENEFICIARIES = frozenset({PerkBeneficiary.SELF, PerkBeneficiary.WHOLE_GROUP})

#: Beneficiaries that fire on a co-present covenant-mate's action (never the
#: holder's own — the mate query structurally excludes the subject).
_ALLY_BENEFICIARIES = frozenset({PerkBeneficiary.COVENANT_ALLIES, PerkBeneficiary.WHOLE_GROUP})

# (covenant_role_id, holder, beneficiaries-that-count-for-this-candidate)
_Candidate = tuple[int, "CharacterSheet", frozenset[str]]


@dataclass(frozen=True)
class FiredPerk:
    """One ``VowSituationalPerk`` that fired for a single resolution (#2536).

    ``magnitude_tenths`` is the WINNING magnitude — the base if no rung
    qualified, or the highest qualifying rung's magnitude (rungs REPLACE the
    base, never sum with it). ``rung_number`` is ``None`` at base level, else
    the highest qualifying rung's number. Callers (Tasks 4-6) scale
    ``magnitude_tenths`` by the acting character's thread level and attribute
    the contribution to ``perk.name`` under ``holder``.
    """

    perk: VowSituationalPerk
    holder: CharacterSheet
    magnitude_tenths: int
    rung_number: int | None


def applicable_perks(
    subject: CharacterSheet,
    *,
    effect_kind: str | tuple[str, ...],
    resolution: object | None,
    target: CharacterSheet | None,
    attacker: object | None = None,
) -> list[FiredPerk]:
    """Return every ``VowSituationalPerk`` of ``effect_kind`` that fires for
    ``subject``'s resolution right now (#2536 spec §2, Task 3).

    ``effect_kind`` accepts a single kind (unchanged behavior) or a tuple of
    kinds — a tuple fetches every listed kind in ONE call (added for the
    outcome-guarantee seam, #2536 slice 2, which needs ``TIER_FLOOR`` +
    ``BOTCH_IMMUNITY`` together without doubling queries; same 3-query
    candidate-perk ceiling either way).

    ``resolution`` is the SUBJECT's live resolution context (a
    ``CombatRoundContext`` in combat, a check-pipeline context otherwise, or
    ``None``) — see ``SituationContext``'s docstring; it is reused unchanged
    across every candidate holder evaluated here. ``target`` is the subject's
    action target, or ``None``. ``attacker`` (#2536 slice 3, Task 6) is the
    SUBJECT's defense-side attacking entity, or ``None`` (the default, and
    every offense-side caller) — threaded through to every candidate
    holder's ``SituationContext`` so the ``ATTACKER_ABYSSAL`` evaluator can
    read it.
    """
    candidates = _self_candidates(subject) + _ally_candidates(subject, resolution)
    if not candidates:
        return []

    kinds = (effect_kind,) if isinstance(effect_kind, str) else tuple(effect_kind)
    role_ids = {role_id for role_id, _holder, _beneficiaries in candidates}
    perks_by_role = _fetch_candidate_perks(role_ids, kinds)
    if not perks_by_role:
        return []

    resolver = _PerkResolver(
        subject=subject, target=target, resolution=resolution, attacker=attacker
    )
    fired: list[FiredPerk] = []
    for role_id, holder, allowed_beneficiaries in candidates:
        for perk in perks_by_role.get(role_id, ()):
            if perk.beneficiary not in allowed_beneficiaries:
                continue
            result = resolver.resolve(perk, holder=holder)
            if result is not None:
                fired.append(result)
    return fired


def mission_category_ids_for(ctx: SituationContext) -> frozenset[int]:
    """``ctx.mission.template``'s authored category ids, as a hoistable set (#2536
    slice 3 review fix).

    Callers checking more than one mission-category-scoped perk against the SAME
    ``ctx`` in one resolution (``checks.services._situational_perk_check_bonus``,
    ``magic.services.power_terms.vow_situational_power_term``) MUST call this ONCE
    before their per-perk filter loop and pass the result through
    ``perk_scope_matches``'s ``mission_category_ids`` kwarg — that keeps the
    categories query at exactly one per resolution regardless of how many perks
    fire. Empty (no query) when ``ctx.mission`` is ``None``.
    """
    if ctx.mission is None:
        return frozenset()
    return frozenset(ctx.mission.template.categories.values_list("pk", flat=True))


def perk_scope_matches(
    perk: VowSituationalPerk,
    ctx: SituationContext,
    *,
    mission_category_ids: frozenset[int] | None = None,
) -> bool:
    """Every authored scope column on ``perk`` must match ``ctx`` (AND); empty scopes
    always match.

    ``mission_category_ids`` is the caller-hoisted result of
    ``mission_category_ids_for(ctx)``. Pass it through when checking more than one
    perk against the same ``ctx`` in a single resolution — see that function's
    docstring for the hoist contract. ``None`` (the default) means the caller didn't
    hoist: this function falls back to computing it itself via
    ``mission_category_ids_for``, one query, which keeps single-perk call sites
    simple at the cost of a fresh query per call.

    Shared by both fired-perk seams (#2536 slice 3): ``checks.services
    ._situational_perk_check_bonus`` (CHECK_BONUS) and ``magic.services.power_terms
    .vow_situational_power_term`` (POWER_BONUS) — one rule, one place.
    """
    if perk.battle_action_kind and perk.battle_action_kind != (ctx.battle_action_kind or ""):
        return False
    if perk.mission_template_id is not None:
        if ctx.mission is None or ctx.mission.template_id != perk.mission_template_id:
            return False
    if perk.mission_category_id is not None:
        if ctx.mission is None:
            return False
        if mission_category_ids is None:
            mission_category_ids = mission_category_ids_for(ctx)
        if perk.mission_category_id not in mission_category_ids:
            return False
    return True


def dormant_perk_firings(  # noqa: PLR0913 - applicable_perks' resolution/target/attacker
    # triple plus the Task-1 scope columns (mission/battle_action_kind) baked in here, unlike
    # applicable_perks, which leaves scope filtering to the caller.
    subject: CharacterSheet,
    *,
    effect_kind: str | tuple[str, ...],
    resolution: object | None,
    target: CharacterSheet | None,
    mission: MissionInstance | None = None,
    battle_action_kind: str | None = None,
    attacker: object | None = None,
) -> list[FiredPerk]:
    """Every ``VowSituationalPerk`` of ``effect_kind`` that would have fired for
    ``subject``'s resolution if their vow were still engaged (#2536 slice 3,
    Task 7 — ruling 2's "loud OFF state").

    Candidates are the SUBJECT'S OWN active-but-DISENGAGED memberships ONLY
    (``_dormant_self_candidates`` — the inverted mirror of ``_self_candidates``'s
    engaged-only filter); a co-present ally's perk is never dormant — ally
    beneficiaries key on the MATE's role, not the subject's, so a mate's own
    disengagement is simply invisible here (the slice-2 reversal already made
    a mate's engagement irrelevant to whether their perk reaches the subject
    at all). Runs the SAME ``_PerkResolver`` situation evaluation
    ``applicable_perks`` runs, **plus** the Task-1 scope filter
    (``perk_scope_matches``, hoisted mission-category ids) inline — unlike
    ``applicable_perks``, which leaves scope filtering to each call site, this
    function returns an already-scope-filtered set so every wiring seam can
    hand its result straight to ``announce_dormant_perks`` (a CHECK_BONUS
    caller still applies its OWN ``check_type`` filter on top, same as it does
    for the live set).

    **Zero queries when the subject has no disengaged active membership** —
    ``_dormant_self_candidates`` reads the SAME cached
    ``character.covenant_roles.active_memberships`` list the live
    ``applicable_perks`` call (made immediately before this one at every
    wiring seam) has already warmed; this is the every-check fast path.
    """
    candidates = _dormant_self_candidates(subject)
    if not candidates:
        return []

    kinds = (effect_kind,) if isinstance(effect_kind, str) else tuple(effect_kind)
    role_ids = {role_id for role_id, _holder, _beneficiaries in candidates}
    perks_by_role = _fetch_candidate_perks(role_ids, kinds)
    if not perks_by_role:
        return []

    resolver = _PerkResolver(
        subject=subject, target=target, resolution=resolution, attacker=attacker
    )
    fired: list[FiredPerk] = []
    for role_id, holder, allowed_beneficiaries in candidates:
        for perk in perks_by_role.get(role_id, ()):
            if perk.beneficiary not in allowed_beneficiaries:
                continue
            result = resolver.resolve(perk, holder=holder)
            if result is not None:
                fired.append(result)
    if not fired:
        return []

    scope_ctx = SituationContext(
        holder=subject,
        subject=subject,
        target=target,
        resolution=resolution,
        mission=mission,
        battle_action_kind=battle_action_kind,
        attacker=attacker,
    )
    mission_category_ids = mission_category_ids_for(scope_ctx)
    return [
        firing
        for firing in fired
        if perk_scope_matches(firing.perk, scope_ctx, mission_category_ids=mission_category_ids)
    ]


def announce_dormant_perks(dormant: list[FiredPerk], *, subject: CharacterSheet) -> None:
    """Announce every dormant firing as the "loud OFF state" (#2536 slice 3,
    Task 7, ruling 2): a disengaged vow says so out loud, at the exact moment
    it would have answered, instead of silently doing nothing.

    Exact line: ``"your vow lies dormant — {perk.name} would have answered
    here"`` — delivered to the HOLDER (= ``subject``) ONLY, never the room
    (unlike ``announce_fired_perks``, which broadcasts). Dual dispatch, single
    recipient:

    - A narrator-authored WHISPER-mode ``Interaction``, receiver-scoped to the
      subject's PRIMARY persona — mirrors ``record_whisper_interaction``'s
      receiver/target-persona shape (``receivers=[subject_persona],
      target_personas=[subject_persona]``), but is NOT built by calling
      ``record_whisper_interaction`` directly: that function derives its
      AUTHOR persona from a ``character`` argument (the whisperer), which
      would wrongly attribute the line to the subject narrating to
      themselves rather than to the system Narrator. This function instead
      calls ``create_interaction`` directly with ``persona=narrator``.
    - The WS payload is sent ONLY to ``subject.character`` via
      ``_send_to_objects`` — deliberately NOT via ``push_interaction``, which
      would resolve the broadcast location from the WRITER persona's
      (narrator's) own — usually unset — character location, the exact
      "resolve delivery off the wrong object" bug class ``announce_fired_perks``'s
      docstring documents for ``message_location``. Sending directly to
      ``[subject.character]`` sidesteps location resolution entirely — there
      is nowhere to broadcast to; this is a single addressed message.
    - A direct ``subject.character.msg(text)`` telnet companion, mirroring
      ``announce_fired_perks``'s own dual-dispatch discipline.

    No-op (no query, no dispatch) when ``dormant`` is empty, ``subject`` has
    no character, or the character has no primary persona.
    """
    if not dormant:
        return

    subject_character = subject.character
    if subject_character is None:
        return

    try:
        subject_persona = subject.primary_persona
    except ObjectDoesNotExist:
        return

    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _build_interaction_payload,
        _send_to_objects,
        create_interaction,
        get_active_scene,
    )
    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    narrator = get_or_create_narrator_persona()
    scene = get_active_scene(subject_character.location)

    for firing in dormant:
        text = f"your vow lies dormant — {firing.perk.name} would have answered here"

        interaction = create_interaction(
            persona=narrator,
            content=text,
            mode=InteractionMode.WHISPER,
            scene=scene,
            receivers=[subject_persona],
            target_personas=[subject_persona],
        )
        payload = _build_interaction_payload(
            interaction_id=interaction.pk,
            persona=narrator,
            content=interaction.content,
            mode=interaction.mode,
            timestamp=interaction.timestamp.isoformat(),
            scene_id=interaction.scene_id,
            receiver_persona_ids=[subject_persona.pk],
            target_persona_ids=[subject_persona.pk],
        )
        _send_to_objects([subject_character], payload)
        # Telnet companion (mirrors announce_fired_perks's dual-dispatch
        # discipline) — addressed directly, HOLDER-only, never the room.
        subject_character.msg(text)


def _self_candidates(subject: CharacterSheet) -> list[_Candidate]:
    """Subject's own engaged roles — anchor AND resolved sub-role both apply.

    One query (the covenant-roles handler's cached ``active_memberships``) +
    a resolve call per subject's own engaged membership (bounded by the
    subject's own role count, not by perk count or mate count).
    """
    character = subject.character
    if character is None:
        return []

    from world.covenants.services import resolve_effective_role  # noqa: PLC0415

    role_ids: set[int] = set()
    for membership in character.covenant_roles.active_memberships:
        if not membership.engaged:
            continue
        role_ids.add(membership.covenant_role_id)
        resolved_role = resolve_effective_role(character=character, role=membership.covenant_role)
        role_ids.add(resolved_role.pk)

    return [(role_id, subject, _SELF_BENEFICIARIES) for role_id in role_ids]


def _dormant_self_candidates(subject: CharacterSheet) -> list[_Candidate]:
    """Subject's own DISENGAGED (but still active) roles — the dormant-vow
    mirror of ``_self_candidates`` (#2536 slice 3, Task 7, ruling 2's "loud
    OFF state"). Same anchor + resolved sub-role ADD semantics, same
    ``_SELF_BENEFICIARIES`` set — a disengaged vow never buffs allies (dormant
    perks are never ``COVENANT_ALLIES``/``WHOLE_GROUP``-for-a-mate; the
    slice-2 reversal documented at the top of this module only concerns a
    co-present MATE's own engagement, never the SUBJECT's).

    Zero queries beyond the cached handler list: ``character.covenant_roles
    .active_memberships`` is the SAME cached ``_rows`` list ``_self_candidates``
    already reads — every wiring seam calls this function right after its own
    live ``applicable_perks`` call, which has already warmed the cache, so
    this never issues a query of its own (the every-check fast path the
    module docstring's query-discipline section documents for the live path).
    """
    character = subject.character
    if character is None:
        return []

    from world.covenants.services import resolve_effective_role  # noqa: PLC0415

    role_ids: set[int] = set()
    for membership in character.covenant_roles.active_memberships:
        if membership.engaged:
            continue
        role_ids.add(membership.covenant_role_id)
        resolved_role = resolve_effective_role(character=character, role=membership.covenant_role)
        role_ids.add(resolved_role.pk)

    return [(role_id, subject, _SELF_BENEFICIARIES) for role_id in role_ids]


def _ally_candidates(subject: CharacterSheet, resolution: object | None) -> list[_Candidate]:
    """Covenant-mates grouped with ``subject`` for this resolution.

    See the module docstring's "What counts as a covenant-mate" — a
    non-departed role in a covenant the SUBJECT is actively engaged in AND
    co-present per ``_group_sheet_ids``. The mate's OWN ``engaged`` flag is
    irrelevant (Tehom's 2026-07-20 reversal — a KO'd mate still in the fight
    keeps buffing; no death-spiral). Ally roles use BOTH the mate's STORED
    (anchor) ``covenant_role`` AND their resolved sub-role (ADD semantics,
    mirroring ``_self_candidates``) — see ``_ally_sub_role_candidates`` for
    the batched (not per-mate) resolution.
    """
    character = subject.character
    if character is None:
        return []

    engaged_covenant_ids = {
        m.covenant_id for m in character.covenant_roles.active_memberships if m.engaged
    }
    if not engaged_covenant_ids:
        return []

    group_ids = _group_sheet_ids(subject, resolution)
    if not group_ids:
        return []

    from world.covenants.models import CharacterCovenantRole  # noqa: PLC0415

    mate_rows = list(
        CharacterCovenantRole.objects.filter(
            character_sheet_id__in=group_ids,
            covenant_id__in=engaged_covenant_ids,
            left_at__isnull=True,
        ).select_related("character_sheet", "covenant_role")
    )
    if not mate_rows:
        return []

    candidates = [
        (row.covenant_role_id, row.character_sheet, _ALLY_BENEFICIARIES) for row in mate_rows
    ]
    candidates.extend(_ally_sub_role_candidates(mate_rows))
    return candidates


def _ally_sub_role_candidates(mate_rows: list[CharacterCovenantRole]) -> list[_Candidate]:
    """Resolved sub-role candidates for ``mate_rows`` — the ally-side mirror
    of ``_self_candidates``' anchor+sub-role ADD semantics (#2536 review: a
    perk authored on a mate's sub-role — e.g. a level-3 resonance vow — must
    be able to fire for the group, not just the mate's base/anchor perks).

    Batched, not per-mate: ONE query fetches every relevant mate's active
    COVENANT_ROLE ``Thread`` row in a single shot (keyed by
    ``(owner, target_covenant_role)`` — the same pair the DB's
    ``one active thread per (owner, role)`` constraint enforces, so at most
    one thread per mate per role). ``CovenantRole.matching_variant`` is then
    called in Python per row; because ``CovenantRole`` is a SharedMemoryModel,
    mates who share the same anchor role resolve against the SAME identity-
    mapped Python instance, so ``matching_variant``'s underlying
    ``cached_sub_roles`` query fires once per DISTINCT role held among the
    mates, never once per mate (see the module docstring's query-discipline
    section).
    """
    from world.covenants.models import CovenantRole  # noqa: PLC0415
    from world.magic.constants import TargetKind  # noqa: PLC0415
    from world.magic.models import Thread  # noqa: PLC0415

    # Threads anchor COVENANT_ROLE resonance investment on the PRIMARY role
    # only (mirrors `_resolve_covenant_role_variant`'s single-depth guard) --
    # a mate whose stored membership already points at a sub-role has no
    # further sub-role to resolve.
    anchor_rows = [row for row in mate_rows if row.covenant_role.parent_role_id is None]
    if not anchor_rows:
        return []

    sheet_ids = {row.character_sheet_id for row in anchor_rows}
    role_ids = {row.covenant_role_id for row in anchor_rows}

    threads_by_owner_role = {
        (thread.owner_id, thread.target_covenant_role_id): thread
        for thread in Thread.objects.filter(
            owner_id__in=sheet_ids,
            target_kind=TargetKind.COVENANT_ROLE,
            target_covenant_role_id__in=role_ids,
            retired_at__isnull=True,
        ).select_related("resonance")
    }
    if not threads_by_owner_role:
        return []

    candidates: list[_Candidate] = []
    for row in anchor_rows:
        thread = threads_by_owner_role.get((row.character_sheet_id, row.covenant_role_id))
        if thread is None:
            continue
        variant = CovenantRole.matching_variant(
            row.covenant_role, resonance=thread.resonance, thread_level=thread.level
        )
        if variant is not None:
            candidates.append((variant.pk, row.character_sheet, _ALLY_BENEFICIARIES))
    return candidates


def _group_sheet_ids(subject: CharacterSheet, resolution: object | None) -> list[int]:
    """``CharacterSheet`` PKs grouped with ``subject`` for this resolution
    (never includes ``subject``).

    Combat: every other ACTIVE ``CombatParticipant`` in the same encounter as
    ``evaluators._resolution_participant(resolution)`` (the single shared
    duck-read helper every combat-positioning evaluator also uses) — one
    query, the same co-presence roster ``evaluators.ally_low_health`` reads
    off ``resolution``. Non-combat
    (the honest documented choice, spec §2's "document what 'same group'
    means for non-combat"): co-present in ``subject``'s location's active
    Scene — room contents are an in-memory Evennia list (no query, same
    pattern ``handlers.can_engage_membership`` already uses for DURANCE
    co-presence); confirming an active Scene exists there is one query (the
    same ``get_active_scene`` lookup ``evaluators.during_negotiation`` uses).
    Empty when neither context is resolvable — a solo, ungrouped resolution
    has no allies.
    """
    from world.covenants.perks.evaluators import _resolution_participant  # noqa: PLC0415

    participant = _resolution_participant(resolution)
    if participant is not None:
        from world.combat.constants import ParticipantStatus  # noqa: PLC0415
        from world.combat.models import CombatParticipant  # noqa: PLC0415

        return list(
            CombatParticipant.objects.filter(
                encounter_id=participant.encounter_id,
                status=ParticipantStatus.ACTIVE,
            )
            .exclude(character_sheet=subject)
            .values_list("character_sheet_id", flat=True)
        )

    character = subject.character
    if character is None:
        return []
    location = character.location
    if location is None:
        return []

    from world.scenes.interaction_services import get_active_scene  # noqa: PLC0415

    if get_active_scene(location) is None:
        return []

    return [
        obj.character_sheet.pk
        for obj in location.contents
        if obj.character_sheet is not None and obj.character_sheet.pk != subject.pk
    ]


def _fetch_candidate_perks(
    role_ids: set[int], effect_kinds: tuple[str, ...]
) -> dict[int, list[VowSituationalPerk]]:
    """Every candidate perk of the requested kinds on ``role_ids``, keyed by role.

    ONE query + 2 prefetch queries (``situations``, ``rungs``) — 3 total,
    independent of how many perks/situations/rungs match, and independent of
    how many kinds are requested (the module docstring's query-discipline
    contract; ``effect_kind__in`` costs the same one query as a single
    ``effect_kind=`` would).
    """
    from world.covenants.models import VowSituationalPerk  # noqa: PLC0415

    perks = VowSituationalPerk.objects.filter(
        covenant_role_id__in=role_ids, effect_kind__in=effect_kinds
    ).prefetch_related("situations", "rungs")  # noqa: PREFETCH_STRING

    by_role: dict[int, list[VowSituationalPerk]] = {}
    for perk in perks:
        by_role.setdefault(perk.covenant_role_id, []).append(perk)
    return by_role


class _PerkResolver:
    """Evaluates candidate perks against the ONE (subject, target, resolution,
    attacker) tuple shared by every candidate holder in a single
    ``applicable_perks`` call. Holds a per-call situation-evaluation cache
    (keyed on ``(situation, holder_pk)``) so a situation shared by multiple
    candidate perks/holders is evaluated at most once.
    """

    def __init__(
        self,
        *,
        subject: CharacterSheet,
        target: CharacterSheet | None,
        resolution: object | None,
        attacker: object | None = None,
    ) -> None:
        self.subject = subject
        self.target = target
        self.resolution = resolution
        self.attacker = attacker
        self._eval_cache: dict[tuple[str, int], bool] = {}

    def _holds(self, situation: str, holder: CharacterSheet) -> bool:
        key = (situation, holder.pk)
        if key not in self._eval_cache:
            ctx = SituationContext(
                holder=holder,
                subject=self.subject,
                target=self.target,
                resolution=self.resolution,
                attacker=self.attacker,
            )
            self._eval_cache[key] = SITUATION_EVALUATORS[situation](ctx)
        return self._eval_cache[key]

    def resolve(self, perk: VowSituationalPerk, *, holder: CharacterSheet) -> FiredPerk | None:
        """``None`` if the perk's base situations don't all hold; else a
        ``FiredPerk`` at base or the highest qualifying rung (spec §2's
        cumulative rung-resolution rule — each rung requires every lower
        rung's extra situation to also hold).
        """
        base_situations = [row.situation for row in perk.situations.all()]
        if not all(self._holds(situation, holder) for situation in base_situations):
            return None

        magnitude_tenths = perk.magnitude_tenths
        rung_number: int | None = None
        cumulative_situations = list(base_situations)
        for rung in perk.rungs.all():  # Meta.ordering = ["perk", "rung_number"]
            cumulative_situations.append(rung.extra_situation)
            if not all(self._holds(situation, holder) for situation in cumulative_situations):
                break
            magnitude_tenths = rung.magnitude_tenths
            rung_number = rung.rung_number

        return FiredPerk(
            perk=perk, holder=holder, magnitude_tenths=magnitude_tenths, rung_number=rung_number
        )


def announce_fired_perks(
    fired: list[FiredPerk],
    *,
    subject: CharacterSheet,
    location: ObjectDB | None,
) -> None:
    """Announce every fired perk as a loud, visible moment in BOTH clients
    (#2536 spec §5, ruling 1 — HARD telnet parity; Task 6).

    **Dual dispatch per firing:** a persisted, Narrator-authored OUTCOME
    ``Interaction`` broadcast over the interaction WebSocket payload — the
    same machinery ``combat.interaction_services.broadcast_action_outcome``
    uses (``create_interaction`` + ``_build_interaction_payload`` +
    ``_broadcast_to_location``) — PLUS a direct ``location.msg_contents(text)``
    text companion so bare telnet clients render the identical line. This is
    the verified gap the spec calls out: ``broadcast_action_outcome`` alone is
    WS-only (no text companion), so it must NOT be reused as-is for this path.

    **The telnet primitive is ``location.msg_contents``, called directly on
    the caller-supplied ``location`` — NOT ``flows.service_functions
    .communication.message_location``.** ``message_location`` resolves its
    broadcast room internally from ``caller.obj.location`` (an object it is
    handed), ignoring the ``location`` this function actually received; every
    existing production caller of it (e.g. ``world.scenes.interaction_views``'
    pose-create view) supplies a caller who is genuinely standing where the
    text should land, so that resolution is invisible there. This function has
    no single "acting character" that is reliably co-located with ``location``
    (a mate's fired perk, an ally-benefit firing, etc. can legitimately name a
    ``holder`` elsewhere) — the one value this function is actually handed
    that is guaranteed to be the right room is ``location`` itself. Calling
    ``location.msg_contents(text)`` directly (mirroring
    ``world.combat.escalation``'s room-wide surge narration, the other
    precedent in the codebase for a caller-less room broadcast) reaches every
    telnet session physically present in ``location`` — the honest primitive
    for "broadcast to this room," independent of who or what triggered it.

    ``announce_template`` is rendered with the firing's ``holder`` name and
    ``subject``'s name via plain ``str.format`` (the template's documented
    ``{holder}``/``{subject}`` placeholders — NOT the funcparser actor-
    stance syntax ``message_location``'s own ``mapping`` machinery
    understands), then prefixed with ``perk.name`` — the "announced label"
    per the model's own help_text (e.g. "Scout's Instinct") — mirroring
    spec §5's presentation example ("Scout's Instinct: you have revealed a
    trap!") so two different perks firing for one character stay
    distinguishable in the announce line itself, not only in the ledger. By
    the time either dispatch sees the text it is fully resolved — mirrors
    how ``interaction_views.py`` hands an already-authored player pose
    straight to ``message_location``.

    **Call once per resolution — dedup is a CALL-SITE discipline, not a
    loop-internal one.** Call this from the provider/seam that computed
    ``fired`` (``vow_situational_power_term`` for POWER_BONUS,
    ``_situational_perk_check_bonus`` for CHECK_BONUS), never from
    ``applicable_perks`` itself: ``applicable_perks`` may legitimately be
    called more than once for a single player action (e.g. a combat
    action's offense check and its separate penetration check are two
    distinct resolutions, each entitled to its own announce). Both wired
    seams are verified to invoke ``applicable_perks`` exactly once per real
    resolution: ``_derive_power`` is called exactly once inside
    ``use_technique``'s orchestration (the single production entry point
    for a cast — combat, clash, and non-combat casts all converge there
    before any power derivation happens), and a production
    ``perform_check`` call computes its breakdown exactly once (the test-
    rig forced-outcome branch is mutually exclusive with the normal-roll
    branch — never both run for one call). Calling from inside each
    provider therefore cannot double-announce a single firing. A perk's
    ``effect_kind`` is a single value, so the SAME perk row can never fire
    from both seams for one resolution either — no cross-seam duplicate is
    possible.

    No-ops (no query, no dispatch) when ``fired`` is empty or ``location``
    is ``None`` (nowhere to broadcast — mirrors ``message_location``'s and
    ``push_interaction``'s own "no location, no message" guards; this
    function's own guard covers ``location.msg_contents`` needing a real
    room too).
    """
    if not fired or location is None:
        return

    from world.scenes.constants import InteractionMode  # noqa: PLC0415
    from world.scenes.interaction_services import (  # noqa: PLC0415
        _broadcast_to_location,
        _build_interaction_payload,
        create_interaction,
        get_active_scene,
    )
    from world.scenes.narrator import get_or_create_narrator_persona  # noqa: PLC0415

    subject_character = subject.character
    subject_name = subject_character.key if subject_character is not None else str(subject)

    narrator = get_or_create_narrator_persona()
    # Scene link (Minor review fix, mirrors broadcast_action_outcome's
    # scene=encounter.scene): resolved from location the same way every other
    # room-scoped active-scene lookup does, so a perk-announce OUTCOME row
    # participates in scene-log replay like the precedent it's modeled on.
    scene = get_active_scene(location)

    for firing in fired:
        holder_character = firing.holder.character
        holder_name = holder_character.key if holder_character is not None else str(firing.holder)
        rendered = firing.perk.announce_template.format(holder=holder_name, subject=subject_name)
        # perk.name is the "announced label" (its help_text's own words, e.g.
        # "Scout's Instinct") — spec §5's presentation example prefixes it
        # onto the templated line ("Scout's Instinct: you have revealed a
        # trap!") so two different perks firing for one character stay
        # distinguishable in BOTH the WS payload and the telnet line, not
        # only in the (separately labeled) power/check ledger.
        text = f"{firing.perk.name}: {rendered}"

        interaction = create_interaction(
            persona=narrator, content=text, mode=InteractionMode.OUTCOME, scene=scene
        )
        payload = _build_interaction_payload(
            interaction_id=interaction.pk,
            persona=narrator,
            content=interaction.content,
            mode=interaction.mode,
            timestamp=interaction.timestamp.isoformat(),
            scene_id=interaction.scene_id,
        )
        _broadcast_to_location(location, payload)
        # Telnet companion (CRITICAL review fix — ruling 1, HARD): deliver
        # directly to `location` via Evennia's own room-broadcast primitive
        # rather than `message_location` (which would resolve the broadcast
        # room from an unrelated caller's own location — see docstring).
        location.msg_contents(text)
