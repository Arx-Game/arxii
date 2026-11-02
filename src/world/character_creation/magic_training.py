"""The Magic skills a draft trains from its Tradition's creation pool, and its style (#4921).

A combat style's own skill is a Magic skill (#4844 decision 16), so
``magic_category_skills()`` holds every style's skill. A draft trains only the chosen
style's: ``training_skills`` is the Magic set less every other style's skill. The rules
that must still see every Magic skill (CG skill points never buy one; the Anima Check
never picks one) keep reading ``magic_category_skills()``.

``reconcile_combat_style`` keeps a draft's style and allocation consistent when its
Tradition or style changes: a style the Tradition does not teach is cleared, and points
allocated to a style skill that is not the chosen style's are dropped.
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
    """The active Magic skills the draft may train: none of a style's but its own style's."""
    from world.magic.services.magic_skills import magic_category_skills  # noqa: PLC0415

    unstyled = Q(combat_style__isnull=True)
    if draft.selected_combat_style_id is not None:
        unstyled |= Q(combat_style__pk=draft.selected_combat_style_id)
    return magic_category_skills().filter(unstyled)


def taught_styles(draft: CharacterDraft) -> QuerySet[CombatStyle]:
    """The combat styles the draft's selected Tradition teaches, in name order."""
    from world.covenants.models import CombatStyle  # noqa: PLC0415

    if draft.selected_tradition_id is None:
        return CombatStyle.objects.none()
    return CombatStyle.objects.filter(taught_by__pk=draft.selected_tradition_id).order_by("name")


def reconcile_combat_style(draft: CharacterDraft) -> None:
    """Clear a style the Tradition does not teach; drop other styles' skill allocations.

    Saves only what changed.
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
        style_skills = Skill.objects.filter(combat_style__isnull=False)
        if draft.selected_combat_style_id is not None:
            style_skills = style_skills.exclude(combat_style__pk=draft.selected_combat_style_id)
        dropped = {str(pk) for pk in style_skills.values_list("pk", flat=True)}
        kept = {key: value for key, value in allocation.items() if key not in dropped}
        if len(kept) != len(allocation):
            draft.draft_data["magic_skills"] = kept
            update_fields.append("draft_data")

    if update_fields:
        draft.save(update_fields=update_fields)
