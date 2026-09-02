"""GM authoring of a beat's scenario graph (#3565).

A beat's ``required_mission`` can point at either a catalog (staff-authored)
MissionTemplate or a scenario graph the beat's own Lead GM authors as that
beat's body. This module owns the create path for the latter -- the story
side, so ``world.missions`` never imports ``Story`` (ADR-0010): ownership is
read back through ``template.story_scenario``.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from world.missions.constants import ArcScope, ConflictMode, MissionVisibility
from world.missions.models import MissionNode, MissionTemplate
from world.stories.models import StoryScenario

if TYPE_CHECKING:
    from world.stories.models import Beat

_ERR_REQUIRED_MISSION = "This beat already uses a catalog mission; a scenario cannot take it over."
_ERR_NAME_TAKEN = "A scenario with that name already exists."


@transaction.atomic
def create_scenario_for_beat(
    beat: Beat, *, name: str, summary: str, risk_tier: int
) -> MissionTemplate:
    """Create (or idempotently return) the scenario graph backing ``beat``.

    A beat with no ``required_mission`` gets a fresh MissionTemplate (RESTRICTED,
    zero draw weight, empty availability rule -- never a front-door quest),
    a ``StoryScenario`` link to the beat's story, and a single entry
    ``MissionNode``; the beat's ``required_mission`` is then set to it.

    Idempotent: a repeat call against a beat whose ``required_mission`` is
    already this story's scenario returns that same template (the view's
    POST /scenario/ action uses this to answer 200 instead of erroring or
    duplicating). A beat whose ``required_mission`` points at some OTHER
    (catalog/staff-authored) template raises
    ``ValidationError({"required_mission": [...]})`` -- a scenario never
    silently takes over an existing assignment.

    Raises:
        django.core.exceptions.ValidationError: ``{"required_mission": [...]}``
            when the beat already uses a non-scenario template, or
            ``{"name": [...]}`` when ``name`` collides with an existing
            MissionTemplate.
    """
    story = beat.episode.chapter.story
    if beat.required_mission_id is not None:
        existing = StoryScenario.objects.filter(
            template_id=beat.required_mission_id, story=story
        ).first()
        if existing is not None:
            return existing.template
        raise ValidationError({"required_mission": [_ERR_REQUIRED_MISSION]})

    try:
        # Savepoint: an IntegrityError on the unique `name` must not poison
        # the enclosing @transaction.atomic (mirrors
        # MissionTemplateSerializer.create's next_available_name retry guard).
        with transaction.atomic():
            template = MissionTemplate.objects.create(
                name=name,
                summary=summary,
                risk_tier=risk_tier,
                level_band_min=1,
                level_band_max=99,
                cooldown=timedelta(0),
                arc_scope=ArcScope.GLOBAL,
                percent_replace=0,
                base_weight=0,
                visibility=MissionVisibility.RESTRICTED,
                availability_rule={},
            )
    except IntegrityError as exc:
        raise ValidationError({"name": [_ERR_NAME_TAKEN]}) from exc

    MissionNode.objects.create(
        template=template,
        key="start",
        is_entry=True,
        conflict_mode=ConflictMode.GROUP_VOTE,
    )
    StoryScenario.objects.create(story=story, template=template)
    beat.required_mission = template
    beat.save(update_fields=["required_mission"])
    return template
