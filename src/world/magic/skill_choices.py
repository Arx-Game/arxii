"""Which skills a magic skill picker offers and accepts (#4547).

The skills a magical roll adds are bespoke Magic skills that staff make and point each
roll at (ADR-4450). They are never skills a character can pick anywhere else, so a cast
never counts one skill twice. Four pickers hold that line with these values:
``MagicActivitySkill.skill``, ``Path.technique_skill``, ``Gift.technique_skill`` and
``Technique.skill``.

``limit_choices_to`` does both jobs: the admin form and its autocomplete offer only these
skills, and ``Model.full_clean()`` refuses any other (``ForeignKey.validate`` filters by
it), with ``MAGIC_SKILL_ERROR_MESSAGES`` saying why. The set follows a skill's trait
category, never its name. ``magic_category_skills()`` reads the same filter and adds the
active flag; a picker keeps an inactive Magic skill valid, because staff deactivating a
skill means it adds nothing, not that every row pointing at it must change.

A cross-table rule like this cannot be a database check constraint.
"""

from __future__ import annotations

from django.db.models import Q

from world.traits.models import TraitCategory

MAGIC_SKILL_CHOICES = Q(trait__category=TraitCategory.MAGIC)

MAGIC_SKILL_ERROR_MESSAGES = {
    "invalid": (
        "Choose a skill in the Magic category. A magical roll adds only skills made for "
        "magic, so it never counts a skill a character picks elsewhere."
    ),
}

MAGIC_SKILL_HELP = "Magic-category skills only."
