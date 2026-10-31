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
    from flows.events.payloads import DamagePreApplyPayload
    from world.character_sheets.models import CharacterSheet
    from world.vitals.models import CharacterVitals


def reactive_save_anima_cost(healer: CombatParticipant) -> int:
    """The anima her next save costs: the dodge's anima base, rising per reaction."""
    from world.combat.services.reactions import reaction_tuning  # noqa: PLC0415

    return rising_reaction_cost(reaction_tuning().dodge_anima_cost, healer.reactions_used)


def can_make_reactive_save(sheet: CharacterSheet) -> bool:
    """True when her engaged vow specialises in Mend and she knows a Mend technique."""
    from world.covenants.models import CovenantRoleTechniqueSpecialty  # noqa: PLC0415
    from world.magic.models.techniques import CharacterTechnique  # noqa: PLC0415

    role_ids: set[int] = set()
    for role in sheet.character.covenant_roles.currently_engaged_roles():
        role_ids.add(role.pk)
        if role.parent_role_id is not None:
            role_ids.add(role.parent_role_id)
    if not role_ids:
        return False
    if not CovenantRoleTechniqueSpecialty.objects.filter(
        covenant_role_id__in=role_ids, function=TechniqueFunction.MEND
    ).exists():
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


def _can_pay(sheet: CharacterSheet, cost: int) -> bool:
    from world.magic.models.anima import CharacterAnima  # noqa: PLC0415

    anima = CharacterAnima.objects.filter(character_id=sheet.pk).first()
    return anima is not None and anima.current >= cost


def _healers_for(ward: CombatParticipant) -> list[CombatParticipant]:
    """Covenant-mates in her fight who can make the save, in participant order."""
    from world.vitals.services import can_act  # noqa: PLC0415

    ally = ward.character_sheet.character
    candidates = (
        CombatParticipant.objects.filter(
            encounter_id=ward.encounter_id, status=ParticipantStatus.ACTIVE
        )
        .exclude(pk=ward.pk)
        .select_related("character_sheet__character")
        .order_by("pk")
    )
    return [
        healer
        for healer in candidates
        if can_act(healer.character_sheet)
        and healer.character_sheet.character.shares_covenant_with(ally)
        and can_make_reactive_save(healer.character_sheet)
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

    for healer in _healers_for(ward):
        cost = reactive_save_anima_cost(healer)
        if not _can_pay(healer.character_sheet, cost):
            continue
        deduct_anima(healer.character_sheet.character, cost, lethal=False)
        record_reaction(healer)
        pre_payload.amount = _softened_amount(vitals, amount)
        pre_payload.answers_consumed += 1
        _narrate_save(healer, ward)
        return True
    return False
