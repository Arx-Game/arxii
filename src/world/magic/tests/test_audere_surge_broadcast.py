"""Tests for the plain-Audere surge broadcast on accept (#3451).

The Audere Majora manifestation's smaller echo: an authored
``AudereThreshold.surge_manifestation_text`` is EMITted to the active scene
when a character accepts the surge; blank text keeps the accept room-silent.

Blank-text coverage lives in its own TestCase (not a mutated shared fixture):
a ``save()`` on a setUpTestData row survives the per-test rollback inside the
idmapper identity map and would leak into sibling tests.
"""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import ConditionStageFactory, ConditionTemplateFactory
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    offer_audere,
)
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory
from world.scenes.models import Interaction


def _make_lifecycle_character(db_key: str) -> ObjectDB:
    """A character able to accept a surge: sheet + anima + active engagement."""
    character = CharacterSheetFactory(character__db_key=db_key).character
    CharacterAnimaFactory(character=character.sheet_data, current=10, maximum=50)
    CharacterEngagement.objects.create(
        character=character.sheet_data,
        engagement_type=EngagementType.CHALLENGE,
        source_content_type=ContentType.objects.get_for_model(ObjectDB),
        source_id=character.pk,
    )
    return character


def _make_threshold(*, surge_text: str, tier_name: str):
    ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
    soulfray = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    stage = ConditionStageFactory(condition=soulfray, stage_order=3, name="Ripping")
    tier = IntensityTierFactory(name=tier_name, threshold=15)
    return AudereThresholdFactory(
        minimum_intensity_tier=tier,
        minimum_warp_stage=stage,
        intensity_bonus=20,
        anima_pool_bonus=30,
        surge_manifestation_text=surge_text,
    )


def _emit_count(scene=None) -> int:
    qs = Interaction.objects.filter(mode=InteractionMode.EMIT)
    if scene is not None:
        qs = qs.filter(scene=scene)
    return qs.count()


class AudereSurgeBroadcastTests(TestCase):
    """With authored text, accept announces; decline and no-scene stay silent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(
            surge_text="{name} answers the surge.", tier_name="Major_surge_bc"
        )

    def setUp(self) -> None:
        self.character = _make_lifecycle_character("surge_bc_char")

    def test_accept_broadcasts_substituted_text_to_active_scene(self) -> None:
        scene = SceneFactory(location=self.character.location, is_active=True)
        persona_name = self.character.sheet_data.primary_persona.name

        result = offer_audere(self.character, accept=True)

        assert result.accepted is True
        emits = Interaction.objects.filter(scene=scene, mode=InteractionMode.EMIT)
        assert emits.count() == 1
        assert emits.first().content == f"{persona_name} answers the surge."

    def test_decline_stays_silent(self) -> None:
        scene = SceneFactory(location=self.character.location, is_active=True)

        result = offer_audere(self.character, accept=False)

        assert result.accepted is False
        assert _emit_count(scene) == 0

    def test_no_active_scene_no_ops(self) -> None:
        result = offer_audere(self.character, accept=True)

        assert result.accepted is True
        assert _emit_count() == 0


class AudereSurgeBlankTextTests(TestCase):
    """The default blank text keeps an accepted surge room-silent."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.threshold = _make_threshold(surge_text="", tier_name="Major_surge_blank")

    def test_blank_text_stays_silent(self) -> None:
        character = _make_lifecycle_character("surge_blank_char")
        scene = SceneFactory(location=character.location, is_active=True)

        result = offer_audere(character, accept=True)

        assert result.accepted is True
        assert _emit_count(scene) == 0
