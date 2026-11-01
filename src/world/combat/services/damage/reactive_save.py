"""The healer's reactive save: soften a blow that would drop an ally (#4810, #4759).

At the pre-damage point, after interposes and companion defense have answered, a
blow that would still drop a player-character ally (into the knockout band or
below) can be softened by a covenant-mate who heals. It is a reaction, not an
action: she keeps her own turn, the save counts as one of her reactions this
round (``record_reaction``), and it costs anima that rises with every reaction she
has already made (``rising_reaction_cost``, ratified decision 12 in #4759).

**Who can save.** An ACTIVE participant of the same fight, able to act, sharing an
active covenant with the ally, whose engaged vow specialises in the Mend function
(a ``CovenantRoleTechniqueSpecialty`` row with ``function=MEND``, read on the
resolved role and its anchor) and who knows a technique tagged Mend. The gate is
the capability, never a vow's name. Holding both is the opt-in, the way holding a
dodging capability is (``reactions.py``); there is no per-round toggle yet.

**What it does.** The blow is cut to whatever would leave the ally just above the
knockout line, but by at most ``MovementConfig.reactive_save_max_cut`` percent of the
blow, so a huge hit
is softened rather than erased. "Would drop" is judged on the pre-damage amount,
before thread reduction, resistance, armor and cover, since those run after this
hook. The save counts against the hit's answer cap (``ABSORPTION_CAP_PER_MOMENT``),
as an interpose does.
"""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal
import math
from typing import TYPE_CHECKING

from world.combat.constants import ABSORPTION_CAP_PER_MOMENT, ParticipantStatus
from world.combat.models import CombatParticipant
from world.combat.services.damage.interception import rising_reaction_cost
from world.magic.constants import TechniqueFunction
from world.scenes.constants import RoundStatus
from world.vitals.constants import KNOCKOUT_HEALTH_THRESHOLD

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from flows.events.payloads import DamagePreApplyPayload
    from world.character_sheets.models import CharacterSheet
    from world.vitals.models import CharacterVitals


def reactive_save_anima_cost(healer: CombatParticipant) -> int:
    """The anima her next save costs: the dodge's anima base, rising per reaction."""
    from world.combat.services.reactions import reaction_tuning  # noqa: PLC0415

    return rising_reaction_cost(reaction_tuning().dodge_anima_cost, healer.reactions_used)


def _vow_specialises_in_mend(sheet: CharacterSheet) -> bool:
    """True when an engaged vow, resolved or its anchor, carries a Mend specialty."""
    from world.covenants.models import CovenantRoleTechniqueSpecialty  # noqa: PLC0415

    role_ids: set[int] = set()
    for role in sheet.character.covenant_roles.currently_engaged_roles():
        role_ids.add(role.pk)
        if role.parent_role_id is not None:
            role_ids.add(role.parent_role_id)
    if not role_ids:
        return False
    return CovenantRoleTechniqueSpecialty.objects.filter(
        covenant_role_id__in=role_ids, function=TechniqueFunction.MEND
    ).exists()


def can_make_reactive_save(sheet: CharacterSheet) -> bool:
    """True when her engaged vow specialises in Mend and she knows a Mend technique."""
    from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

    if not _vow_specialises_in_mend(sheet):
        return False
    return CharacterTechnique.objects.filter(
        character=sheet, technique__function_tags__function=TechniqueFunction.MEND
    ).exists()


def _knockout_line(vitals: CharacterVitals) -> int:
    """The highest health that is still in the knockout band."""
    return math.floor(vitals.max_health * KNOCKOUT_HEALTH_THRESHOLD)


def _would_drop(vitals: CharacterVitals, amount: int) -> bool:
    """True when she is standing now and this amount would put her in the band or below."""
    if vitals.max_health <= 0:
        return False
    line = _knockout_line(vitals)
    return vitals.health > line and vitals.health - amount <= line


def _softened_amount(vitals: CharacterVitals, amount: int) -> int:
    """The blow cut to leave her just above the line, by at most the max cut."""
    leaves_her_standing = max(0, vitals.health - _knockout_line(vitals) - 1)
    from world.combat.services.reactions import reaction_tuning  # noqa: PLC0415

    max_cut = Decimal(reaction_tuning().reactive_save_max_cut) / 100
    least_allowed = int((Decimal(amount) * (1 - max_cut)).to_integral(ROUND_CEILING))
    return max(leaves_her_standing, least_allowed)


def _anima_by_sheet(healers: list[CombatParticipant]) -> dict[int, int]:
    """Current anima for each healer's sheet, in one query."""
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    sheet_ids = [healer.character_sheet_id for healer in healers]
    return dict(
        CharacterAnima.objects.filter(character_id__in=sheet_ids).values_list(
            "character_id", "current"
        )
    )


def _healer_candidates(
    ward: CombatParticipant, ward_covenant_ids: frozenset[int]
) -> QuerySet[CombatParticipant]:
    """Fighters in her fight who pass the batched gates, in participant order.

    Three ``Exists`` filters run in the one query: an active membership in one of
    the ward's active covenants (exactly ``shares_covenant_with``), a known Mend
    technique (exactly the technique half of ``can_make_reactive_save``), and an
    engaged membership whose stored role, its parent or one of its sub-roles holds
    a Mend specialty. That last one is a superset: which sub-role a vow resolves to
    depends on her thread, so ``_vow_specialises_in_mend`` confirms it on the few
    rows left.
    """
    from django.db.models import Exists, OuterRef, Q  # noqa: PLC0415

    from world.covenants.models import (  # noqa: PLC0415
        CharacterCovenantRole,
        CovenantRoleTechniqueSpecialty,
    )
    from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

    sheet = OuterRef("character_sheet_id")
    active = CharacterCovenantRole.objects.filter(character_sheet_id=sheet, left_at__isnull=True)
    mend_roles = CovenantRoleTechniqueSpecialty.objects.filter(
        function=TechniqueFunction.MEND
    ).values("covenant_role_id")
    mend_vow = Q(covenant_role_id__in=mend_roles) | Q(covenant_role__parent_role_id__in=mend_roles)
    mend_vow |= Q(covenant_role__sub_roles__in=mend_roles)
    knows_mend = CharacterTechnique.objects.filter(
        character_id=sheet, technique__function_tags__function=TechniqueFunction.MEND
    )
    return (
        CombatParticipant.objects.filter(
            encounter_id=ward.encounter_id, status=ParticipantStatus.ACTIVE
        )
        .exclude(pk=ward.pk)
        .filter(Exists(active.filter(covenant_id__in=ward_covenant_ids)))
        .filter(Exists(active.filter(engaged=True).filter(mend_vow)))
        .filter(Exists(knows_mend))
        .select_related("character_sheet__character")
        .order_by("pk")
    )


def _healers_for(ward: CombatParticipant) -> list[CombatParticipant]:
    """Covenant-mates in her fight who can make the save, in participant order."""
    from world.vitals.services import can_act  # noqa: PLC0415

    ward_covenant_ids = ward.character_sheet.character.active_covenant_ids()
    if not ward_covenant_ids:
        return []
    return [
        healer
        for healer in _healer_candidates(ward, ward_covenant_ids)
        if can_act(healer.character_sheet) and _vow_specialises_in_mend(healer.character_sheet)
    ]


def _narrate_save(healer: CombatParticipant, ward: CombatParticipant) -> None:
    from world.scenes.interaction_services import narrate_privately  # noqa: PLC0415

    healer_char = healer.character_sheet.character
    ward_char = ward.character_sheet.character
    narrate_privately(healer_char, f"You reach {ward_char} as the blow falls, and it lands softer.")
    narrate_privately(ward_char, f"{healer_char}'s magic catches you as the blow falls.")


def try_reactive_save(
    ward: CombatParticipant,
    pre_payload: DamagePreApplyPayload,
    vitals: CharacterVitals,
) -> bool:
    """Let the first able covenant healer soften a blow that would drop *ward*.

    Returns True when a save landed. Mutates ``pre_payload.amount`` in place. A no-op
    outside a resolving round, when the hit's answer cap is spent, when the blow
    would not drop her, or when no healer qualifies and can pay.
    """
    if ward.encounter.status != RoundStatus.RESOLVING:
        return False
    if pre_payload.answers_consumed >= ABSORPTION_CAP_PER_MOMENT:
        return False
    amount = int(pre_payload.amount)
    if amount <= 0 or not _would_drop(vitals, amount):
        return False
    from world.combat.services.reactions import record_reaction  # noqa: PLC0415
    from world.magic.services.anima import deduct_anima  # noqa: PLC0415

    healers = _healers_for(ward)
    anima = _anima_by_sheet(healers)
    for healer in healers:
        cost = reactive_save_anima_cost(healer)
        if anima.get(healer.character_sheet_id, -1) < cost:
            continue
        deduct_anima(healer.character_sheet.character, cost, lethal=False)
        record_reaction(healer)
        pre_payload.amount = _softened_amount(vitals, amount)
        pre_payload.answers_consumed += 1
        _narrate_save(healer, ward)
        return True
    return False
