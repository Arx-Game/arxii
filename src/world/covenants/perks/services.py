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
  matches on purpose): a covenant-mate is a character who BOTH (a) holds an
  ENGAGED role (``CharacterCovenantRole.engaged``) in a covenant the acting
  character is also actively engaged in, AND (b) is physically grouped with
  the acting character for this resolution — the same combat encounter's
  active roster in combat, the same active Scene otherwise (see
  ``_group_sheet_ids``). Perks are a benefit of ACTIVE, PRESENT vows: an
  unengaged member is "in civilian garb" (does not extend or receive
  group-beneficiary perks even though ``Character.shares_covenant_with``
  would still say they share a covenant), and an engaged member who isn't
  here right now cannot lend their vow to a fight or a negotiation they are
  not part of.
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
- ``COVENANT_ALLIES``/``WHOLE_GROUP`` perks on an engaged covenant-mate's
  (see above) engaged (anchor) role.

``COVENANT_ALLIES`` never fires for the holder's own action because the
subject is structurally excluded from being counted as their own covenant-
mate; ``WHOLE_GROUP`` fires for both cases (the holder's own action via the
first bullet, a mate's action via the second) — "includes the holder."

## Query discipline

Every step below is a small, FIXED number of queries independent of how many
perks/situations/rungs are authored: one query for the subject's own active
memberships (cached per-character by the covenant-roles handler), a bounded
number of resolve calls for the subject's own engaged roles (scales with the
subject's OWN role count, not perk count), one query for the co-presence
roster, one query for the batched ally ``CharacterCovenantRole`` fetch, and
ONE query (plus 2 prefetch queries — ``situations``, ``rungs``) for the
candidate-perk fetch regardless of how many perks match. That last group (3
queries: base + 2 prefetches) is the part this module's contract calls out
explicitly as never scaling with perk count — see
``test_perk_resolution.PerkResolutionQueryBudgetTests``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from world.covenants.perks.constants import PerkBeneficiary
from world.covenants.perks.context import SituationContext
from world.covenants.perks.evaluators import SITUATION_EVALUATORS

if TYPE_CHECKING:
    from world.character_sheets.models import CharacterSheet
    from world.covenants.models import VowSituationalPerk

#: Beneficiaries that fire on the perk-owning holder's OWN action.
_SELF_BENEFICIARIES = frozenset({PerkBeneficiary.SELF, PerkBeneficiary.WHOLE_GROUP})

#: Beneficiaries that fire on an engaged covenant-mate's action (never the
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
    effect_kind: str,
    resolution: object | None,
    target: CharacterSheet | None,
) -> list[FiredPerk]:
    """Return every ``VowSituationalPerk`` of ``effect_kind`` that fires for
    ``subject``'s resolution right now (#2536 spec §2, Task 3).

    ``resolution`` is the SUBJECT's live resolution context (a
    ``CombatRoundContext`` in combat, a check-pipeline context otherwise, or
    ``None``) — see ``SituationContext``'s docstring; it is reused unchanged
    across every candidate holder evaluated here. ``target`` is the subject's
    action target, or ``None``.
    """
    candidates = _self_candidates(subject) + _ally_candidates(subject, resolution)
    if not candidates:
        return []

    role_ids = {role_id for role_id, _holder, _beneficiaries in candidates}
    perks_by_role = _fetch_candidate_perks(role_ids, effect_kind)
    if not perks_by_role:
        return []

    resolver = _PerkResolver(subject=subject, target=target, resolution=resolution)
    fired: list[FiredPerk] = []
    for role_id, holder, allowed_beneficiaries in candidates:
        for perk in perks_by_role.get(role_id, ()):
            if perk.beneficiary not in allowed_beneficiaries:
                continue
            result = resolver.resolve(perk, holder=holder)
            if result is not None:
                fired.append(result)
    return fired


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


def _ally_candidates(subject: CharacterSheet, resolution: object | None) -> list[_Candidate]:
    """Engaged covenant-mates grouped with ``subject`` for this resolution.

    See the module docstring's "What counts as a covenant-mate" — engaged
    role in a shared covenant AND co-present per ``_group_sheet_ids``. Ally
    roles use the STORED (anchor) ``covenant_role`` only — no per-mate
    sub-role resolution, which would cost one query per mate; see the module
    docstring's query-discipline section.
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

    mate_rows = CharacterCovenantRole.objects.filter(
        character_sheet_id__in=group_ids,
        covenant_id__in=engaged_covenant_ids,
        engaged=True,
        left_at__isnull=True,
    ).select_related("character_sheet")

    return [(row.covenant_role_id, row.character_sheet, _ALLY_BENEFICIARIES) for row in mate_rows]


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
    role_ids: set[int], effect_kind: str
) -> dict[int, list[VowSituationalPerk]]:
    """Every candidate perk of ``effect_kind`` on ``role_ids``, keyed by role.

    ONE query + 2 prefetch queries (``situations``, ``rungs``) — 3 total,
    independent of how many perks/situations/rungs match (the module
    docstring's query-discipline contract).
    """
    from world.covenants.models import VowSituationalPerk  # noqa: PLC0415

    perks = VowSituationalPerk.objects.filter(
        covenant_role_id__in=role_ids, effect_kind=effect_kind
    ).prefetch_related("situations", "rungs")  # noqa: PREFETCH_STRING

    by_role: dict[int, list[VowSituationalPerk]] = {}
    for perk in perks:
        by_role.setdefault(perk.covenant_role_id, []).append(perk)
    return by_role


class _PerkResolver:
    """Evaluates candidate perks against the ONE (subject, target, resolution)
    triple shared by every candidate holder in a single ``applicable_perks``
    call. Holds a per-call situation-evaluation cache (keyed on
    ``(situation, holder_pk)``) so a situation shared by multiple candidate
    perks/holders is evaluated at most once.
    """

    def __init__(
        self,
        *,
        subject: CharacterSheet,
        target: CharacterSheet | None,
        resolution: object | None,
    ) -> None:
        self.subject = subject
        self.target = target
        self.resolution = resolution
        self._eval_cache: dict[tuple[str, int], bool] = {}

    def _holds(self, situation: str, holder: CharacterSheet) -> bool:
        key = (situation, holder.pk)
        if key not in self._eval_cache:
            ctx = SituationContext(
                holder=holder, subject=self.subject, target=self.target, resolution=self.resolution
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
