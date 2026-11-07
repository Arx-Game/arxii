"""The style a cast is worked in (#5002).

One rule for a cast's manner and its skill: the technique's Gift's own style when it
sets one (ADR-0199, a species gift the character never chose), else the caster's
current Path style (ADR-0167). Cast concealment (``cast_observation._concealment_for``)
and the cast skill (``magic_skills``) both read it, so the two never disagree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evennia.objects.models import ObjectDB

    from world.classes.models import Path
    from world.magic.models import Technique, TechniqueStyle


def casting_style_for_path(technique: Technique, path: Path | None) -> TechniqueStyle | None:
    """The style ``technique`` is cast in by a caster whose current Path is ``path``.

    The Gift's own style wins; otherwise the Path's style; None when neither sets one.
    """
    gift = technique.gift
    if gift.style_id is not None:
        return gift.style
    if path is None or path.style_id is None:
        return None
    return path.style


def casting_style(
    caster: ObjectDB,  # noqa: OBJECTDB_PARAM — Evennia character
    technique: Technique,
) -> TechniqueStyle | None:
    """The style ``caster`` works ``technique`` in, or None.

    Reads the caster's current Path only when the Gift sets no style of its own.
    """
    if technique.gift.style_id is not None:
        return technique.gift.style
    from world.progression.selectors import current_path_for_character  # noqa: PLC0415

    return casting_style_for_path(technique, current_path_for_character(caster))
