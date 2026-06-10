"""Tests for the PendingAudereOffer surface (#873): model, services, hook."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.magic.audere import (
    SOULFRAY_CONDITION_NAME,
    PendingAudereOffer,
    maybe_create_audere_offer,
    resolve_audere_offer,
)
from world.magic.exceptions import AudereOfferNotFoundError, AudereOfferStaleError
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterAnimaFactory,
    IntensityTierFactory,
    wire_audere_power_multipliers,
)
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


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
        wire_audere_power_multipliers()

        cls.soulfray_template = ConditionTemplateFactory(
            name=SOULFRAY_CONDITION_NAME, has_progression=True
        )
        cls.stage1 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=1, name="Fraying"
        )
        cls.stage2 = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=2, name="Tearing"
        )
        cls.soulfray_stage = ConditionStageFactory(
            condition=cls.soulfray_template, stage_order=3, name="Ripping"
        )

        cls.minor_tier = IntensityTierFactory(name="Minor_os", threshold=1, control_modifier=0)
        cls.major_tier = IntensityTierFactory(name="Major_os", threshold=15, control_modifier=-5)
        cls.threshold = AudereThresholdFactory(
            minimum_intensity_tier=cls.major_tier,
            minimum_warp_stage=cls.soulfray_stage,
            intensity_bonus=20,
            anima_pool_bonus=30,
            warp_multiplier=2,
        )
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
