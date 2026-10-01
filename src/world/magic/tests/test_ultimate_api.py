"""Audere ultimate REST surface (#4098): owner-only, no undiscovered leak."""

from rest_framework.test import APITestCase

from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.constants import RoleArchetype
from world.magic.constants import GiftKind
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterGiftFactory,
    GiftFactory,
    PathGiftGrantFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory

_STATE = "/api/magic/audere/ultimates/"
_CHOOSE = "/api/magic/audere/ultimates/choose/"


class AudereUltimateApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.audere, _ = wire_audere_power_multipliers()
        AudereThresholdFactory(sword_reveal_label="Edge")
        cls.tenure = RosterTenureFactory()
        cls.account = cls.tenure.player_data.account
        cls.sheet = cls.tenure.roster_entry.character_sheet
        gift = GiftFactory(kind=GiftKind.MAJOR)
        CharacterGiftFactory(character=cls.sheet, gift=gift)
        grant = PathGiftGrantFactory(gift=gift)
        CharacterPathHistoryFactory(character=cls.sheet, path=grant.path)
        cls.secret = UltimateTechniqueFactory(
            gift=gift,
            name="Secretname",
            description="Secret effect",
            archetype_alignment=RoleArchetype.SWORD,
        )
        grant.ultimate_techniques.add(cls.secret)
        CharacterEngagementFactory(character=cls.sheet, engagement_type=EngagementType.COMBAT)
        CombatParticipantFactory(encounter=CombatEncounterFactory(), character_sheet=cls.sheet)
        cls.stranger = RosterTenureFactory().player_data.account

    def setUp(self) -> None:
        ConditionInstanceFactory(target=self.sheet.character, condition=self.audere)

    def test_reveal_never_leaks_undiscovered(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.get(_STATE, {"character_sheet_id": self.sheet.pk})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn(b"Secretname", response.content)
        self.assertNotIn(b"Secret effect", response.content)
        card = response.data["reveal"]["groups"][0]["cards"][0]
        # A CATEGORY card's choice_key is "category:<source>:<source_id>:<category>" —
        # never "known:<pk>"/"upgrade:<pk>" (those kinds are the only ones that embed a
        # technique pk, and that pk is never this undiscovered technique's own). Assert
        # the structural shape rather than a raw substring: the pool's source_id can
        # coincidentally collide numerically with an unrelated technique's pk on a fresh
        # test database (#4098 fix round 1).
        self.assertEqual(card["kind"], "category")
        self.assertEqual(card["name"], "")
        self.assertNotIn(f"known:{self.secret.pk}", card["choice_key"])
        self.assertNotIn(f"upgrade:{self.secret.pk}", card["choice_key"])
        self.assertEqual(card["label"], "Edge")

    def test_choose_reveals_and_readies(self) -> None:
        self.client.force_authenticate(user=self.account)
        state = self.client.get(_STATE, {"character_sheet_id": self.sheet.pk}).data
        key = state["reveal"]["groups"][0]["cards"][0]["choice_key"]
        response = self.client.post(
            _CHOOSE, {"character_sheet_id": self.sheet.pk, "choice_key": key}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["name"], "Secretname")
        self.assertTrue(KnownUltimate.objects.get(character=self.sheet).readied)

    def test_other_account_refused(self) -> None:
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(_STATE, {"character_sheet_id": self.sheet.pk})
        self.assertEqual(response.status_code, 400)

    def test_bad_key_is_400_with_user_message(self) -> None:
        self.client.force_authenticate(user=self.account)
        response = self.client.post(
            _CHOOSE,
            {"character_sheet_id": self.sheet.pk, "choice_key": "known:999999"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
