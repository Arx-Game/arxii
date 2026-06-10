"""Tests for the PendingAudereOffer surface (#873): model, services, hook."""

from dataclasses import dataclass
from unittest.mock import MagicMock

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.conditions.models import ConditionStage, ConditionTemplate
from world.magic.audere import (
    SOULFRAY_CONDITION_NAME,
    AudereThreshold,
    PendingAudereOffer,
    maybe_create_audere_offer,
    resolve_audere_offer,
)
from world.magic.exceptions import AudereOfferNotFoundError, AudereOfferStaleError
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
    TechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import IntensityTier
from world.magic.services import use_technique
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


@dataclass(frozen=True)
class AudereGateFixture:
    """Authored rows that open the Audere eligibility gate (shared by test classes)."""

    soulfray_template: ConditionTemplate
    soulfray_stage: ConditionStage
    minor_tier: IntensityTier
    major_tier: IntensityTier
    threshold: AudereThreshold


def build_audere_gate_fixture(*, tier_suffix: str) -> AudereGateFixture:
    """Seed Soulfray stages, IntensityTiers, and the AudereThreshold gate config.

    ``tier_suffix`` keeps IntensityTier names distinct per test class so
    SharedMemoryModel identity-map caching never hands one class another's rows.
    """
    wire_audere_power_multipliers()

    soulfray_template = ConditionTemplateFactory(name=SOULFRAY_CONDITION_NAME, has_progression=True)
    ConditionStageFactory(condition=soulfray_template, stage_order=1, name="Fraying")
    ConditionStageFactory(condition=soulfray_template, stage_order=2, name="Tearing")
    soulfray_stage = ConditionStageFactory(
        condition=soulfray_template, stage_order=3, name="Ripping"
    )

    minor_tier = IntensityTierFactory(name=f"Minor_{tier_suffix}", threshold=1, control_modifier=0)
    major_tier = IntensityTierFactory(
        name=f"Major_{tier_suffix}", threshold=15, control_modifier=-5
    )
    threshold = AudereThresholdFactory(
        minimum_intensity_tier=major_tier,
        minimum_warp_stage=soulfray_stage,
        intensity_bonus=20,
        anima_pool_bonus=30,
        warp_multiplier=2,
    )
    return AudereGateFixture(
        soulfray_template=soulfray_template,
        soulfray_stage=soulfray_stage,
        minor_tier=minor_tier,
        major_tier=major_tier,
        threshold=threshold,
    )


class PendingAudereOfferModelTests(TestCase):
    """Model shape: one pending offer per character sheet."""

    def test_unique_per_character_sheet(self) -> None:
        sheet = CharacterSheetFactory()
        PendingAudereOffer.objects.create(
            character_sheet=sheet, fired_intensity=20, soulfray_stage_order=2
        )
        offer, created = PendingAudereOffer.objects.update_or_create(
            character_sheet=sheet,
            defaults={"fired_intensity": 25, "soulfray_stage_order": 3},
        )
        assert created is False
        assert offer.fired_intensity == 25
        assert PendingAudereOffer.objects.filter(character_sheet=sheet).count() == 1


class AudereOfferServiceTests(TestCase):
    """Service layer: maybe_create_audere_offer + resolve_audere_offer (#873)."""

    @classmethod
    def setUpTestData(cls) -> None:
        gate = build_audere_gate_fixture(tier_suffix="os")
        cls.soulfray_template = gate.soulfray_template
        cls.soulfray_stage = gate.soulfray_stage
        cls.threshold = gate.threshold
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def setUp(self) -> None:
        self.character = ObjectDB.objects.create(db_key="offer_surface_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.anima = CharacterAnimaFactory(character=self.character, current=10, maximum=50)
        self.engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=self.character.pk,
        )
        ConditionInstanceFactory(
            target=self.character,
            condition=self.soulfray_template,
            current_stage=self.soulfray_stage,
        )

    def test_creates_offer_when_eligible(self) -> None:
        offer = maybe_create_audere_offer(self.character, runtime_intensity=20)

        assert offer is not None
        assert offer.fired_intensity == 20
        assert offer.soulfray_stage_order == self.soulfray_stage.stage_order
        assert offer.character_sheet == self.sheet

    def test_no_offer_when_gate_closed(self) -> None:
        offer = maybe_create_audere_offer(self.character, runtime_intensity=1)

        assert offer is None
        assert not PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists()

    def test_no_offer_for_npc_without_sheet(self) -> None:
        npc = ObjectDB.objects.create(db_key="offer_surface_npc")

        assert maybe_create_audere_offer(npc, runtime_intensity=20) is None
        assert not PendingAudereOffer.objects.exists()

    def test_repeat_cast_updates_existing_row(self) -> None:
        maybe_create_audere_offer(self.character, runtime_intensity=20)
        maybe_create_audere_offer(self.character, runtime_intensity=30)

        offers = PendingAudereOffer.objects.filter(character_sheet=self.sheet)
        assert offers.count() == 1
        assert offers.first().fired_intensity == 30

    def test_resolve_accept_applies_and_deletes(self) -> None:
        offer = maybe_create_audere_offer(self.character, runtime_intensity=20)
        assert offer is not None

        result = resolve_audere_offer(offer.pk, accept=True)

        assert result.accepted is True
        assert result.intensity_bonus_applied == self.threshold.intensity_bonus
        assert not PendingAudereOffer.objects.filter(pk=offer.pk).exists()

    def test_resolve_decline_deletes_without_state_change(self) -> None:
        offer = maybe_create_audere_offer(self.character, runtime_intensity=20)
        assert offer is not None

        result = resolve_audere_offer(offer.pk, accept=False)

        assert result.accepted is False
        assert not PendingAudereOffer.objects.filter(pk=offer.pk).exists()
        self.engagement.refresh_from_db()
        assert self.engagement.intensity_modifier == 0

    def test_resolve_stale_offer_deletes_and_raises(self) -> None:
        offer = maybe_create_audere_offer(self.character, runtime_intensity=20)
        assert offer is not None

        self.engagement.delete()

        with self.assertRaises(AudereOfferStaleError):
            resolve_audere_offer(offer.pk, accept=True)
        assert not PendingAudereOffer.objects.filter(pk=offer.pk).exists()

    def test_resolve_missing_offer_raises_not_found(self) -> None:
        with self.assertRaises(AudereOfferNotFoundError):
            resolve_audere_offer(999999, accept=True)


class UseTechniqueAudereHookTests(TestCase):
    """use_technique surfaces the Audere gate by creating a PendingAudereOffer (#873)."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="hook")
        # intensity=20 resolves to the major tier (threshold 15) → passes the gate.
        # control=30 keeps the cast clean (no mishap path) even after the tier's -5.
        cls.technique = TechniqueFactory(intensity=20, control=30, anima_cost=3)
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def setUp(self) -> None:
        self.character = ObjectDB.objects.create(db_key="audere_hook_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.anima = CharacterAnimaFactory(character=self.character, current=50, maximum=50)
        self.engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=self.character.pk,
        )
        ConditionInstanceFactory(
            target=self.character,
            condition=self.gate.soulfray_template,
            current_stage=self.gate.soulfray_stage,
        )

    def test_qualifying_cast_creates_offer(self) -> None:
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
        )

        assert result.confirmed is True
        assert PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists()
        offer = PendingAudereOffer.objects.get(character_sheet=self.sheet)
        assert offer.fired_intensity == 20
        assert offer.soulfray_stage_order == self.gate.soulfray_stage.stage_order

    def test_unconfirmed_soulfray_checkpoint_creates_no_offer(self) -> None:
        """The soulfray-warning early return (confirmed=False) never creates an offer."""
        result = use_technique(
            character=self.character,
            technique=self.technique,
            resolve_fn=MagicMock(return_value="ok"),
            confirm_soulfray_risk=False,
        )

        assert result.confirmed is False
        assert result.soulfray_warning is not None
        assert not PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists()
