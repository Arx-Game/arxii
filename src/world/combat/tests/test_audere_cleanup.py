"""Encounter cleanup ends Audere (reverting modifiers) and deletes pending offers (#873)."""

from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from evennia.objects.models import ObjectDB

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.services import cleanup_completed_encounter
from world.conditions.models import ConditionInstance
from world.magic.audere import AUDERE_CONDITION_NAME, PendingAudereOffer, offer_audere
from world.magic.factories import CharacterAnimaFactory, PendingAudereOfferFactory
from world.magic.tests.audere_test_helpers import build_audere_gate_fixture
from world.mechanics.constants import EngagementType
from world.mechanics.engagement import CharacterEngagement


class CleanupAudereTeardownTests(TestCase):
    """cleanup_completed_encounter must end Audere via end_audere (reverting the
    engagement intensity modifier and anima-pool expansion) BEFORE the generic
    end-of-combat condition sweep strips the condition, and must delete any
    unanswered PendingAudereOffer rows for participants."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.gate = build_audere_gate_fixture(tier_suffix="cleanup")
        cls.obj_ct = ContentType.objects.get_for_model(ObjectDB)

    def setUp(self) -> None:
        self.character = ObjectDB.objects.create(db_key="audere_cleanup_char")
        self.sheet = CharacterSheetFactory(character=self.character)
        self.anima = CharacterAnimaFactory(character=self.character, current=10, maximum=50)
        self.engagement = CharacterEngagement.objects.create(
            character=self.character,
            engagement_type=EngagementType.CHALLENGE,
            source_content_type=self.obj_ct,
            source_id=self.character.pk,
        )
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter, character_sheet=self.sheet
        )

    def test_cleanup_ends_audere_and_reverts_modifiers(self) -> None:
        original_maximum = self.anima.maximum
        result = offer_audere(self.character, accept=True)
        assert result.accepted is True

        cleanup_completed_encounter(self.encounter)

        self.engagement.refresh_from_db()
        self.anima.refresh_from_db()
        assert self.engagement.intensity_modifier == 0
        assert self.anima.maximum == original_maximum
        assert self.anima.pre_audere_maximum is None
        assert not ConditionInstance.objects.filter(
            target=self.character, condition__name=AUDERE_CONDITION_NAME
        ).exists()

    def test_cleanup_deletes_pending_offers(self) -> None:
        PendingAudereOfferFactory(character_sheet=self.sheet)

        cleanup_completed_encounter(self.encounter)

        assert not PendingAudereOffer.objects.filter(character_sheet=self.sheet).exists()
