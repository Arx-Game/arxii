"""Skill terms for magical rolls (#4450).

A magical roll keeps its own check type and adds skills as ``ExtraTraitTerm`` rows.
Two sources feed them: staff-mapped ``MagicActivitySkill`` rows (per kind of roll) and
the technique skill (override, Path, or Gift). Nothing here names a skill; unmapped
configuration means no term.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from world.checks.types import ExtraTraitTerm
from world.magic.constants import GiftKind, MagicActivity
from world.magic.models.magic_activity import MagicActivitySkill
from world.magic.services.anima import get_character_cast_check
from world.magic.skill_choices import MAGIC_SKILL_CHOICES
from world.magic.types.magic_skills import CastCheck
from world.skills.models import Skill

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from evennia.objects.models import ObjectDB

    from world.checks.models import CheckType
    from world.classes.models import Path
    from world.magic.models import Technique

TECHNIQUE_SKILL_WEIGHT = Decimal("1.00")


def magic_category_skills() -> QuerySet[Skill]:
    """The active skills whose trait is in the Magic category.

    Staff control the set by a skill's category, never by name. Called by character
    creation (the skills a Tradition's schooling stance lifts at finalize, the points a
    draft may not spend on them), the Anima Check filter, which excludes them so a
    skill is never counted twice in a magical roll (#4450, #4457), and the Required
    content dashboard. ``MAGIC_SKILL_CHOICES`` is the same filter the four magic skill
    pickers offer and accept (#4547); this adds the active flag.
    """
    return Skill.objects.filter(MAGIC_SKILL_CHOICES, is_active=True)


def activity_skill_terms(activity: MagicActivity) -> tuple[ExtraTraitTerm, ...]:
    """The skill terms staff mapped to ``activity``; empty when none are mapped.

    Rows whose skill is inactive are skipped.
    """
    rows = MagicActivitySkill.objects.filter(
        activity=activity, skill__is_active=True
    ).select_related("skill__trait")
    return tuple(ExtraTraitTerm(trait=row.skill.trait, weight=row.weight) for row in rows)


def technique_paths(technique_ids: Iterable[int]) -> dict[int, list[Path]]:
    """Technique pk -> the Paths whose list holds it, in Path order (#4555).

    A technique belongs to the Paths whose ``PathGiftGrant.starter_techniques`` list
    holds it. One query for any number of techniques; a technique on no list is absent.
    """
    from world.magic.models import PathGiftGrant  # noqa: PLC0415

    rows = (
        PathGiftGrant.starter_techniques.through.objects.filter(
            technique_id__in=list(technique_ids)
        )
        .select_related("pathgiftgrant__path__technique_skill__trait")
        .order_by(
            "pathgiftgrant__path__stage",
            "pathgiftgrant__path__sort_order",
            "pathgiftgrant__path__name",
            "pathgiftgrant__path__pk",
        )
    )
    paths: dict[int, list[Path]] = {}
    for row in rows:
        paths.setdefault(row.technique_id, []).append(row.pathgiftgrant.path)
    return paths


def invalidate_technique_own_paths() -> None:
    """Drop every cached ``Technique.cached_own_paths`` (#4555).

    Called by the admin saves that change which Paths list a technique (a Path Gift
    Grant's list, a Path's grants, a Path's order). Techniques are identity-mapped, so
    an answer cached before the edit would otherwise last the life of the process.
    """
    from world.magic.models import Technique  # noqa: PLC0415

    for technique in Technique.get_all_cached_instances():
        technique.__dict__.pop("cached_own_paths", None)


def skill_path(current_path: Path | None, own_paths: Sequence[Path]) -> Path | None:
    """The Path whose technique skill a Major Gift technique's cast adds (#4555).

    The caster's current Path when it is one of the technique's own Paths
    (``own_paths``, from :func:`technique_paths`); otherwise the technique's first own
    Path in Path order (stage, sort order, name, then pk), so a technique cast after a
    Crossing, or learned from another
    Path's teacher, adds its own Path's skill. A technique on no Path's list keeps the
    caster's current Path.
    """
    if current_path is not None and any(path.pk == current_path.pk for path in own_paths):
        return current_path
    return own_paths[0] if own_paths else current_path


def _skill_for_path(
    technique: Technique, path: Path | None, own_paths: Sequence[Path] | None = None
) -> Skill | None:
    """The skill a technique adds for a caster whose current Path is ``path``.

    The technique's own skill wins. Otherwise a Major Gift technique takes the skill of the
    Path :func:`skill_path` picks and a Minor Gift technique takes the Gift's skill.
    ``own_paths`` is the technique's own Paths when the caller read them in bulk; None
    reads ``technique.cached_own_paths``.

    An override wins even when its skill is inactive: the technique then adds no term and
    does NOT fall back to the Path or Gift skill. Staff deactivating a skill means that
    skill is off, not that the technique should borrow another (deliberate ruling, #4450).
    """
    if technique.skill is not None:
        return technique.skill
    gift = technique.gift
    if gift.kind == GiftKind.MINOR:
        return gift.technique_skill
    if own_paths is None:
        own_paths = technique.cached_own_paths
    chosen = skill_path(path, own_paths)
    return chosen.technique_skill if chosen is not None else None


def _skill_term(skill: Skill | None) -> ExtraTraitTerm | None:
    """``skill`` as a roll term, or None when there is no skill or it is inactive."""
    if skill is None or not skill.is_active:
        return None
    return ExtraTraitTerm(trait=skill.trait, weight=TECHNIQUE_SKILL_WEIGHT)


def technique_skill_term_for_path(
    technique: Technique, path: Path | None, own_paths: Sequence[Path] | None = None
) -> ExtraTraitTerm | None:
    """The technique skill term for a caster whose current Path is ``path``.

    Same rule as :func:`technique_skill_term` with the Path already in hand, so a caller
    resolving many techniques for one caster reads the Path once. Such a caller passes
    each technique's ``own_paths`` from one :func:`technique_paths` call; None reads them
    per technique.
    """
    return _skill_term(_skill_for_path(technique, path, own_paths))


def technique_skill_term(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> ExtraTraitTerm | None:
    """The technique skill as a roll term for ``character``, or None.

    None when no skill resolves (no override, neither an own Path nor a current Path for a
    Major Gift, no Gift skill for a Minor one) or the resolved skill is inactive. Only a
    Major Gift technique without an override reads the caster's current Path and the
    technique's own Paths.
    """
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    needs_path = technique.skill is None and technique.gift.kind != GiftKind.MINOR
    path = current_path_for_character(character) if needs_path else None
    return technique_skill_term_for_path(technique, path)


def cast_check_type(personal_check: CheckType | None, technique: Technique) -> CheckType | None:
    """The check type a cast of ``technique`` rolls, given the caster's personal check.

    ADR-0096 precedence, held in one place: the caster's personal magic check, else the
    technique's action template check, else None. A caller resolving many techniques for
    one caster reads ``get_character_cast_check`` once and passes it in.
    """
    if personal_check is not None:
        return personal_check
    template = technique.action_template
    return template.check_type if template is not None else None


def resolve_cast_check(
    character: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> CastCheck | None:
    """The check type and skill terms a cast of ``technique`` rolls, or None.

    Check type precedence is unchanged (ADR-0096): the caster's personal magic check,
    else the technique's action template check. None when neither exists; callers that
    require a concrete check guard on that.
    """
    check_type = cast_check_type(get_character_cast_check(character), technique)
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


def cast_involved_trait_ids(cast_check: CastCheck | None) -> tuple[int, ...]:
    """Trait ids a cast rolls, for the thread pulls that cast can use; empty without a check.

    A TRAIT thread is in a cast's action when its trait is one of these, so the cast's stat,
    its skills and its technique skill all count. One query: call it once per cast.
    """
    if cast_check is None:
        return ()
    return involved_trait_ids(cast_check.check_type, cast_check.extra_traits)
