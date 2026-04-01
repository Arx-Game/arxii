"""Tests for Audere threshold, eligibility, and lifecycle."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import (
    AUDERE_CONDITION_NAME,
    SOULFRAY_CONDITION_NAME,
    AudereThreshold,
    check_audere_eligibility,
    end_audere,
    offer_audere,
)
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


class AudereThresholdModelTests(TestCase):
    """Test AudereThreshold configuration model."""

    def test_create_threshold(self) -> None:
        condition = ConditionTemplateFactory(has_progression=True)
        stage = ConditionStageFactory(condition=condition, stage_order=3)
        tier = IntensityTierFactory(name="Major", threshold=15)
        threshold = AudereThresholdFactory(
            minimum_intensity_tier=tier,
            minimum_warp_stage=stage,
            intensity_bonus=25,
            anima_pool_bonus=40,
            warp_multiplier=3,
        )
        assert threshold.intensity_bonus == 25
        assert threshold.anima_pool_bonus == 40
        assert threshold.warp_multiplier == 3
        assert threshold.minimum_intensity_tier == tier
        assert threshold.minimum_warp_stage == stage


class AudereEligibilityTests(TestCase):
    """Test the triple-gate eligibility check for Audere activation."""

    @classmethod
    def setUpTestData(cls) -> None:
        # Soulfray condition with stages
        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=1, name="Strain"
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=2, name="Fracture"
        )
        cls.stage3 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=3, name="Collapse"
        )

        # Intensity tiers
        cls.minor_tier = IntensityTierFactory(name="Minor", threshold=1, control_modifier=0)
        cls.major_tier = IntensityTierFactory(name="Major", threshold=15, control_modifier=-5)

        # Audere requires Major tier + stage 2+ soulfray
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=cls.major_tier,
            minimum_warp_stage=cls.stage2,
            intensity_bonus=20,
            anima_pool_bonus=30,
            warp_multiplier=2,
        )

        # Shared content type for engagement creation
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def _create_character(self) -> ObjectDB:
        return ObjectDB.objects.create(db_key="test_char")

    def _create_engagement(self, character: ObjectDB) -> CharacterEngagement:
        return CharacterEngagement.objects.create(
            character=character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=character.pk,
        )

    def test_all_gates_met(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage2
        )
        assert check_audere_eligibility(char, runtime_intensity=20) is True

    def test_no_engagement(self) -> None:
        char = self._create_character()
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage2
        )
        assert check_audere_eligibility(char, runtime_intensity=20) is False

    def test_intensity_too_low(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage2
        )
        assert check_audere_eligibility(char, runtime_intensity=5) is False

    def test_soulfray_stage_too_low(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage1
        )
        assert check_audere_eligibility(char, runtime_intensity=20) is False

    def test_no_soulfray_condition(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        assert check_audere_eligibility(char, runtime_intensity=20) is False

    def test_no_threshold_configured(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage2
        )
        AudereThreshold.objects.all().delete()
        assert check_audere_eligibility(char, runtime_intensity=20) is False

    def test_already_in_audere(self) -> None:
        char = self._create_character()
        self._create_engagement(char)
        ConditionInstanceFactory(
            target=char, condition=self.soulfray_template, current_stage=self.stage2
        )
        # Already has Audere condition
        audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)
        ConditionInstanceFactory(target=char, condition=audere_template)
        assert check_audere_eligibility(char, runtime_intensity=20) is False


class AudereLifecycleTests(TestCase):
    """Test Audere offer/accept flow and end lifecycle."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.audere_template = ConditionTemplateFactory(name=AUDERE_CONDITION_NAME)

        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=2, name="Fracture"
        )

        cls.major_tier = IntensityTierFactory(name="Major_lc", threshold=15, control_modifier=-5)
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=cls.major_tier,
            minimum_warp_stage=cls.stage2,
            intensity_bonus=20,
            anima_pool_bonus=30,
            warp_multiplier=2,
        )
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def setUp(self) -> None:
        self.character = ObjectDB.objects.create(db_key="lifecycle_char")
        self.anima = CharacterAnimaFactory(character=self.character, current=10, maximum=50)
        self.engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=self.character.pk,
        )

    def test_offer_audere_accepted(self) -> None:
        result = offer_audere(self.character, accept=True)

        assert result.accepted is True
        assert result.intensity_bonus_applied == 20
        assert result.anima_pool_expanded_by == 30

        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 20

        self.anima.refresh_from_db()
        assert self.anima.maximum == 80  # 50 + 30
        assert self.anima.pre_audere_maximum == 50

        from world.conditions.models import ConditionInstance

        assert ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_CONDITION_NAME
        ).exists()

    def test_offer_audere_declined(self) -> None:
        result = offer_audere(self.character, accept=False)

        assert result.accepted is False
        assert result.intensity_bonus_applied == 0
        assert result.anima_pool_expanded_by == 0

        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 0

        self.anima.refresh_from_db()
        assert self.anima.maximum == 50
        assert self.anima.pre_audere_maximum is None

    def test_end_audere_with_engagement(self) -> None:
        offer_audere(self.character, accept=True)
        end_audere(self.character)

        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 0

        self.anima.refresh_from_db()
        assert self.anima.maximum == 50
        assert self.anima.pre_audere_maximum is None

        from world.conditions.models import ConditionInstance

        assert not ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_CONDITION_NAME
        ).exists()

    def test_end_audere_on_engagement_delete(self) -> None:
        offer_audere(self.character, accept=True)

        # Engagement gets deleted (e.g., combat ends)
        self.engagement.delete()

        end_audere(self.character)

        self.anima.refresh_from_db()
        assert self.anima.maximum == 50
        assert self.anima.pre_audere_maximum is None

    def test_end_audere_noop_when_not_active(self) -> None:
        """end_audere is safe to call when Audere is not active."""
        end_audere(self.character)

        self.anima.refresh_from_db()
        assert self.anima.maximum == 50
        assert self.anima.pre_audere_maximum is None
