"""Tests for Audere corruption advisory (Spec §3.5 risk-transparency).

When a character has any resonance at corruption stage 3+, offer_audere
must surface an advisory containing the explicit phrase "character loss".
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    offer_audere,
)
from world.magic.factories import AudereThresholdFactory, CharacterAnimaFactory, ResonanceFactory


def _make_corruption_template_with_stages(resonance):
    """Create a Corruption ConditionTemplate with 5 stages for the given resonance."""
    template = ConditionTemplateFactory(
        name=f"Corruption ({resonance.name})",
        has_progression=True,
        corruption_resonance=resonance,
    )
    thresholds = [50, 200, 500, 1000, 1500]
    stages = []
    for i, threshold in enumerate(thresholds, start=1):
        stages.append(
            ConditionStageFactory(
                condition=template,
                stage_order=i,
                severity_threshold=threshold,
            )
        )
    return template, stages


class AudereCorruptionAdvisoryTests(TestCase):
    """offer_audere advisory_text content based on corruption stage."""

    def test_advisory_present_when_at_stage_3(self) -> None:
        """A character with corruption at stage 3 receives a character-loss advisory."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        template, stages = _make_corruption_template_with_stages(resonance)
        # Place at stage 3
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[2],  # stage_order=3
        )

        result = offer_audere(sheet.character, accept=False)

        assert result.advisory_text != ""
        assert "character loss" in result.advisory_text.lower()

    def test_advisory_contains_resonance_name(self) -> None:
        """The advisory names the affected resonance."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory(name="Wild Hunt")
        template, stages = _make_corruption_template_with_stages(resonance)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[2],  # stage_order=3
        )

        result = offer_audere(sheet.character, accept=False)

        assert "Wild Hunt" in result.advisory_text

    def test_advisory_present_when_at_stage_4(self) -> None:
        """Stage 4 also warrants the advisory."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        template, stages = _make_corruption_template_with_stages(resonance)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[3],  # stage_order=4
        )

        result = offer_audere(sheet.character, accept=False)

        assert "character loss" in result.advisory_text.lower()

    def test_advisory_present_when_at_stage_5(self) -> None:
        """Stage 5 (terminal) also warrants the advisory."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        template, stages = _make_corruption_template_with_stages(resonance)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[4],  # stage_order=5
        )

        result = offer_audere(sheet.character, accept=False)

        assert "character loss" in result.advisory_text.lower()

    def test_no_advisory_when_stage_2(self) -> None:
        """Stage 2 corruption is below the advisory threshold — no advisory."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        template, stages = _make_corruption_template_with_stages(resonance)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[1],  # stage_order=2
        )

        result = offer_audere(sheet.character, accept=False)

        assert result.advisory_text == ""

    def test_no_advisory_when_no_corruption(self) -> None:
        """Healthy characters see no advisory."""
        sheet = CharacterSheetFactory()

        result = offer_audere(sheet.character, accept=False)

        assert result.advisory_text == ""

    def test_advisory_surfaced_on_accepted_offer(self) -> None:
        """Advisory is also present when the offer is accepted."""
        sheet = CharacterSheetFactory()
        resonance = ResonanceFactory()
        template, stages = _make_corruption_template_with_stages(resonance)
        ConditionInstanceFactory(
            target=sheet.character,
            condition=template,
            current_stage=stages[2],  # stage_order=3
        )

        # Provide Audere prerequisite infrastructure so offer can be accepted.
        ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)  # must exist for apply_condition
        from world.magic.factories import IntensityTierFactory

        tier = IntensityTierFactory(name="MajorAdvisory", threshold=15)
        AudereThresholdFactory(
            minimum_intensity_tier=tier,
            minimum_warp_stage=stages[0],
            intensity_bonus=10,
            anima_pool_bonus=20,
        )
        CharacterAnimaFactory(character=sheet.character, current=20, maximum=50)
        from django.contrib.contenttypes.models import ContentType
        from evennia.objects.models import ObjectDB

        from world.mechanics.constants import EngagementType
        from world.mechanics.engagement import CharacterEngagement

        obj_ct = ContentType.objects.get_for_model(ObjectDB)
        CharacterEngagement.objects.create(
            character=sheet.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=obj_ct,
            source_id=sheet.character.pk,
        )

        result = offer_audere(sheet.character, accept=True)

        assert result.accepted is True
        assert "character loss" in result.advisory_text.lower()
