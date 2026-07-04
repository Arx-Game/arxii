"""Cast-time application of a signed technique's SignatureMotifBonus payload (#1582).

When a character casts a technique they have *signed* (their active TECHNIQUE-kind
Thread for that technique carries a ``SignatureMotifBonus``), the bonus's effect
payload applies on top of the technique's own payload:

- ``flat_intensity_delta`` folds into the resolved cast intensity at the power
  computation — exposed via :func:`signature_intensity_delta`, which both cast
  paths add to ``use_technique(power_intensity_bonus=...)`` (so it flows through
  the PowerLedger into the effective intensity used for damage + conditions).
- ``condition_applications`` apply through the SAME
  :func:`world.magic.services.condition_application.apply_technique_conditions`
  seam the technique's own conditions use — exposed via
  :func:`apply_signature_bonus_conditions`. No parallel apply path.

Damage profiles authored on a SignatureMotifBonus ARE applied — not here (there is
no cast-time damage seam; standalone casts deal no damage), but at the combat
damage seam via :func:`signature_damage_profiles`, consumed by
``CombatTechniqueResolver._apply_damage`` (``world/combat/services.py``), which
appends the signed technique's bonus profiles to the technique's own before
resolving damage. Capability grants authored on a SignatureMotifBonus remain
unapplied: there is no cast-time OR combat seam for technique-authored capability
grants today. Cosmetic narration of the bonus is Task 6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from world.magic.services.condition_application import apply_technique_conditions
from world.magic.services.signature import signature_bonus_for

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.conditions.types import AppliedConditionResult
    from world.magic.models.techniques import Technique


def signature_intensity_delta(character, technique: Technique) -> int:
    """Return the signed technique's ``flat_intensity_delta``, or 0 when unsigned.

    Cheap read through the cached ``character.threads`` handler (via
    :func:`signature_bonus_for`). Callers add the result to
    ``use_technique(power_intensity_bonus=...)`` so it folds into the resolved
    cast intensity at the power computation.

    Args:
        character: The casting game Character (not CharacterSheet).
        technique: The technique being cast.

    Returns:
        The active ``SignatureMotifBonus.flat_intensity_delta``, or 0 if the
        technique is not signed.
    """
    bonus = signature_bonus_for(character, technique)
    return bonus.flat_intensity_delta if bonus is not None else 0


def signature_damage_profiles(character, technique: Technique) -> list:
    """Return the signed technique's SignatureMotifBonusDamageProfile rows, or [].

    Cheap read through the cached ``character.threads`` handler (via
    :func:`signature_bonus_for`). The combat damage seam (``_apply_damage``)
    appends these to the technique's own profiles so the bonus's authored damage
    lands alongside it. NO-OP (``[]``) when the technique is not signed.

    Args:
        character: The casting game Character (not CharacterSheet).
        technique: The technique being cast.

    Returns:
        The active ``SignatureMotifBonus.cached_damage_profiles``, or ``[]`` if
        the technique is not signed.
    """
    bonus = signature_bonus_for(character, technique)
    return bonus.cached_damage_profiles if bonus is not None else []


def apply_signature_bonus_conditions(  # noqa: PLR0913 - cohesive condition-application params
    *,
    character,
    technique: Technique,
    success_level: int,
    eff_intensity: int,
    targets_by_kind: dict[str, list[ObjectDB]],  # noqa: OBJECTDB_PARAM
    source_character: ObjectDB,  # noqa: OBJECTDB_PARAM
) -> list[AppliedConditionResult]:
    """Apply the signed technique's bonus conditions to the pre-resolved targets.

    NO-OP (returns ``[]``) when the technique is not signed or the bonus carries
    no condition rows. Otherwise the bonus's ``SignatureMotifBonusAppliedCondition``
    rows are applied through the shared ``apply_technique_conditions`` seam — the
    same target map, success level, and effective intensity the technique's own
    conditions used — with provenance pointing at the cast *technique*.

    Args:
        character: The casting game Character (used to resolve the signed thread).
        technique: The technique being cast (provenance for the applied conditions).
        success_level: The cast roll's success level.
        eff_intensity: The effective intensity (post-PowerLedger).
        targets_by_kind: Pre-resolved ``{ConditionTargetKind: [ObjectDB, ...]}``
            map the caller already built for the technique's own conditions.
        source_character: The caster's ``ObjectDB``.

    Returns:
        The list of ``AppliedConditionResult`` from the shared seam (empty on no-op).
    """
    bonus = signature_bonus_for(character, technique)
    if bonus is None:
        return []
    rows = bonus.cached_condition_applications
    if not rows:
        return []
    return apply_technique_conditions(
        technique=technique,
        success_level=success_level,
        eff_intensity=eff_intensity,
        targets_by_kind=targets_by_kind,
        source_character=source_character,
        applied_condition_rows=rows,
    )
