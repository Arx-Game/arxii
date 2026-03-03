"""Enhancement query functions for the action system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from actions.models import ActionEnhancement

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB


def get_involuntary_enhancements(
    action_key: str,
    actor: ObjectDB,
) -> list[ActionEnhancement]:
    """Return involuntary enhancements that apply to this actor for the given action.

    Queries all involuntary ActionEnhancements matching the action key, then
    filters to those whose source confirms applicability via
    ``should_apply_enhancement(actor, enhancement)``.
    """
    enhancements = ActionEnhancement.objects.filter(
        base_action_key=action_key,
        is_involuntary=True,
    ).select_related("distinction", "condition", "technique")

    results = []
    for enh in enhancements:
        source = enh.source
        if source and hasattr(source, "should_apply_enhancement"):
            if source.should_apply_enhancement(actor, enh):
                results.append(enh)
    return results
