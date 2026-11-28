"""The Magic skills a draft trains from its Tradition's creation pool, and its style (#4921).

A combat style's own skill is a Magic skill (#4844 decision 16), so
``magic_category_skills()`` holds every style's skill. A draft trains only the chosen
style's: ``training_skills`` is the Magic set less every other style's skill. The rules
that must still see every Magic skill (CG skill points never buy one; the Anima Check
never picks one) keep reading ``magic_category_skills()``.

A draft is also offered only the affinity skills (Reflection, Heroism, Villainy) its own
Tradition teaches, and none of them with no Tradition (#5326, ``tradition_teaching``).

``reconcile_magic_training`` keeps a draft's style and allocation consistent when its
Tradition or style changes: a style the Tradition does not teach is cleared, and points
allocated to a skill the draft is no longer offered (another style's skill, or an affinity
skill the Tradition does not teach) are dropped.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from world.character_creation.models import CharacterDraft
    from world.covenants.models import CombatStyle
    from world.skills.models import Skill


def training_skills(draft: CharacterDraft) -> QuerySet[Skill]:
    """The active Magic skills the draft may train.

    None of a style's skills but its own style's, and no affinity skill the draft's
    Tradition does not teach. A draft with no Tradition is offered none of the affinity
    skills (#5326).
    """
    from world.magic.services.magic_skills import magic_category_skills  # noqa: PLC0415
    from world.magic.services.tradition_teaching import (  # noqa: PLC0415
        taught_affinity_skill_filter,
    )

    unstyled = Q(combat_style__isnull=True)
    if draft.selected_combat_style_id is not None:
        unstyled |= Q(combat_style__pk=draft.selected_combat_style_id)
    return (
        magic_category_skills()
        .filter(unstyled)
        .filter(taught_affinity_skill_filter(draft.selected_tradition_id))
    )


def taught_styles(draft: CharacterDraft) -> QuerySet[CombatStyle]:
    """The combat styles the draft's selected Tradition teaches, in name order."""
    from world.covenants.models import CombatStyle  # noqa: PLC0415

    if draft.selected_tradition_id is None:
        return CombatStyle.objects.none()
    return CombatStyle.objects.filter(taught_by__pk=draft.selected_tradition_id).order_by("name")


def reconcile_magic_training(draft: CharacterDraft) -> None:
    """Clear a style the Tradition does not teach; drop allocations the draft is not offered.

    A skill is dropped from the allocation when it is another style's skill or an affinity
    skill the draft's Tradition does not teach. Saves only what changed.
    """
    from world.skills.models import Skill  # noqa: PLC0415

    update_fields: list[str] = []
    if (
        draft.selected_combat_style_id is not None
        and not taught_styles(draft).filter(pk=draft.selected_combat_style_id).exists()
    ):
        draft.selected_combat_style = None
        update_fields.append("selected_combat_style")

    allocation = draft.draft_data.get("magic_skills")
    if isinstance(allocation, dict) and allocation:
        not_offered = Skill.objects.filter(
            Q(combat_style__isnull=False) | Q(affinity__isnull=False)
        ).exclude(pk__in=training_skills(draft).values("pk"))
        dropped = {str(pk) for pk in not_offered.values_list("pk", flat=True)}
        kept = {key: value for key, value in allocation.items() if key not in dropped}
        if len(kept) != len(allocation):
            draft.draft_data["magic_skills"] = kept
            update_fields.append("draft_data")

    if update_fields:
        draft.save(update_fields=update_fields)
