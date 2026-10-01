"""Audere ultimate REST surface (#4098): owner-only, no undiscovered leak."""

from rest_framework.test import APITestCase

from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.conditions.factories import ConditionInstanceFactory
from world.covenants.constants import RoleArchetype
from world.magic.constants import GiftKind
from world.magic.exceptions import UltimateChoiceUnavailable
from world.magic.factories import (
    AudereThresholdFactory,
    CharacterGiftFactory,
    GiftFactory,
    PathGiftGrantFactory,
    UltimateTechniqueFactory,
    wire_audere_power_multipliers,
)
from world.magic.models import KnownUltimate
from world.magic.services.ultimates import choose_ultimate, ultimate_reveal_for
from world.mechanics.constants import EngagementType
from world.mechanics.factories import CharacterEngagementFactory
from world.progression.factories import CharacterPathHistoryFactory
from world.roster.factories import RosterTenureFactory

_STATE = "/api/magic/audere/ultimates/"
_CHOOSE = "/api/magic/audere/ultimates/choose/"
_SHEET_URL = "/api/character-sheets/{pk}/"


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
        cls.grant = PathGiftGrantFactory(gift=gift)
        CharacterPathHistoryFactory(character=cls.sheet, path=cls.grant.path)
        cls.secret = UltimateTechniqueFactory(
            gift=gift,
            name="Secretname",
            description="Secret effect",
            archetype_alignment=RoleArchetype.SWORD,
        )
        cls.grant.ultimate_techniques.add(cls.secret)
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
        # technique pk). Assert the exact key (rather than a raw pk-substring check,
        # which coincidentally collided with the pool's source_id on a fresh test
        # database, #4098 fix round 1) plus the full no-leak shape: name, description
        # and upgrade_of_name all blank for an undiscovered card.
        self.assertEqual(card["kind"], "category")
        self.assertEqual(card["choice_key"], f"category:owned:{self.grant.pk}:sword")
        self.assertEqual(card["name"], "")
        self.assertEqual(card["description"], "")
        self.assertEqual(card["upgrade_of_name"], "")
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
        self.assertIn(UltimateChoiceUnavailable.user_message, str(response.data))

    def test_choice_appears_on_sheet_without_stale_prefetch(self) -> None:
        """#4098 fix round 1: the sheet's magic.ultimates must never go stale.

        A ``to_attr`` prefetch on the idmapper-shared CharacterSheet is silently
        skipped on a later fetch once the attribute already exists on the
        identity-mapped instance (reference-idmapper-defeats-to-attr-prefetch) — so
        an ultimate picked mid-session would never show up on a later GET. The fix
        is a plain per-read query; this proves it by GETting, picking, then GETting
        again against the SAME identity-mapped sheet.
        """
        self.client.force_authenticate(user=self.account)
        url = _SHEET_URL.format(pk=self.sheet.pk)
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200, before.content)
        self.assertEqual(before.data["magic"]["ultimates"], [])

        reveal = ultimate_reveal_for(self.sheet)
        card = reveal.groups[0].cards[0]
        choose_ultimate(self.sheet, card.choice_key)

        after = self.client.get(url)
        self.assertEqual(after.status_code, 200, after.content)
        self.assertEqual(
            after.data["magic"]["ultimates"],
            [{"name": "Secretname", "description": "Secret effect", "label": "Edge"}],
        )
