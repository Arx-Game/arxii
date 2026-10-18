"""Skill terms for magical rolls (#4450).

A magical roll keeps its own check type and adds skills as ``ExtraTraitTerm`` rows.
Two sources feed them: staff-mapped ``MagicActivitySkill`` rows (per kind of roll) and
the technique skill (override, Path, or Gift). Nothing here names a skill; unmapped
configuration means no term.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.types import ExtraTraitTerm
from world.magic.constants import GiftKind, MagicActivity
from world.magic.models.magic_activity import MagicActivitySkill
from world.magic.services.anima import get_character_cast_check
from world.magic.types.magic_skills import CastCheck

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.magic.models import Technique
    from world.skills.models import Skill

TECHNIQUE_SKILL_WEIGHT = Decimal("1.00")


def activity_skill_terms(activity: MagicActivity) -> tuple[ExtraTraitTerm, ...]:
    """The skill terms staff mapped to ``activity``; empty when none are mapped.

    Rows whose skill is inactive are skipped.
    """
    rows = MagicActivitySkill.objects.filter(
        activity=activity, skill__is_active=True
    ).select_related("skill__trait")
    return tuple(ExtraTraitTerm(trait=row.skill.trait, weight=row.weight) for row in rows)


def _technique_skill(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> Skill | None:
    """The skill a technique adds for ``character``, before the active check.

    The technique's own skill wins. Otherwise a Major Gift technique takes the caster's
    current Path skill and a Minor Gift technique takes the Gift's skill.
    """
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    if technique.skill is not None:
        return technique.skill
    gift = technique.gift
    if gift.kind == GiftKind.MINOR:
        return gift.technique_skill
    path = current_path_for_character(character)
    return path.technique_skill if path is not None else None


def technique_skill_term(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> ExtraTraitTerm | None:
    """The technique skill as a roll term for ``character``, or None.

    None when no skill resolves (no override, no Path or sheet for a Major Gift, no Gift
    skill for a Minor one) or the resolved skill is inactive.
    """
    skill = _technique_skill(character, technique)
    if skill is None or not skill.is_active:
        return None
    return ExtraTraitTerm(trait=skill.trait, weight=TECHNIQUE_SKILL_WEIGHT)


def resolve_cast_check(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> CastCheck | None:
    """The check type and skill terms a cast of ``technique`` rolls, or None.

    Check type precedence is unchanged (ADR-0096): the caster's personal magic check,
    else the technique's action template check. None when neither exists; callers that
    require a concrete check guard on that.
    """
    check_type = get_character_cast_check(character)
    if check_type is None and technique.action_template is not None:
        check_type = technique.action_template.check_type
    if check_type is None:
        return None
    term = technique_skill_term(character, technique)
    return CastCheck(check_type=check_type, extra_traits=(term,) if term is not None else ())


def involved_trait_ids(
    check_type: CheckType, extra_traits: Sequence[ExtraTraitTerm]
) -> tuple[int, ...]:
    """Trait ids a roll involves: the check type's traits, then the terms', once each."""
    # check_type.traits is the reverse FK manager from CheckTypeTrait.
    type_ids = check_type.traits.values_list("trait_id", flat=True)  # type: ignore[attr-defined]
    return tuple(dict.fromkeys([*type_ids, *(term.trait.pk for term in extra_traits)]))
