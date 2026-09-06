"""Seed content for the companion defeat consequence (#3652).

Savaged is the pool's middle outcome made real: a companion that survived a
lethal mauling is out of action while it mends. It gates the two verbs that
send a companion back into a fight (companion fight, companion deploy) and
nothing else - a savaged companion is still present, still poseable, still
someone's.

INGAME_TIME rather than PERMANENT or UNTIL_CURED: the sweep inside
get_active_conditions expires it on read, so nothing has to schedule a recovery
and no heal verb has to exist. A duration that needed curing would brick the
companion forever, which is death with extra steps.

ConditionTemplate and ConditionCategory are CONTENT_MODELS, so this resolves
the authored row rather than creating one - see world.seeds.sample_content.
"""

from __future__ import annotations

SAVAGED_CONDITION_NAME = "Savaged"

#: IC hours a savaged companion stays out of action.
SAVAGED_IC_HOURS = 72


def ensure_companion_defeat_conditions() -> None:
    """Resolve the Savaged ConditionTemplate, sampling only when enabled."""
    from world.conditions.constants import DurationType  # noqa: PLC0415
    from world.conditions.models import ConditionCategory, ConditionTemplate  # noqa: PLC0415
    from world.seeds.sample_content import authored_or_sample  # noqa: PLC0415

    category = authored_or_sample(
        ConditionCategory,
        {
            "description": "States a bound companion carries out of a fight.",
            "is_negative": True,
            "display_order": 55,
        },
        name="Companion Injury",
    )
    if category is None:
        return

    authored_or_sample(
        ConditionTemplate,
        {
            "description": (
                "Torn up badly enough that another fight would finish it. The "
                "beast is out of action until it mends."
            ),
            "category": category,
            "default_duration_type": DurationType.INGAME_TIME,
            "default_duration_value": SAVAGED_IC_HOURS,
            "is_stackable": False,
            "max_stacks": 1,
            "has_progression": False,
            "can_be_dispelled": True,
        },
        name=SAVAGED_CONDITION_NAME,
    )
