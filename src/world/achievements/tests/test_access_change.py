"""Tests for announce_access_change and announce_achievement (achievements/discovery.py)."""

from django.test import TestCase

from world.achievements.constants import AccessChangeSource
from world.achievements.factories import AchievementFactory
from world.achievements.models import CharacterAchievement, Discovery
from world.character_sheets.factories import CharacterSheetFactory
from world.conditions.factories import CapabilityTypeFactory
from world.magic.factories import TechniqueFactory
from world.narrative.constants import NarrativeCategory
from world.narrative.models import NarrativeMessage, NarrativeMessageDelivery
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class AnnounceAccessChangePersonalMessageTest(TestCase):
    def test_personal_message_lists_gained_and_lost(self):
        sheet = CharacterSheetFactory()
        t1 = TechniqueFactory(name="Flame Lash")
        t2 = TechniqueFactory(name="Ash Step")
        from world.achievements.discovery import announce_access_change

        announce_access_change(
            sheet,
            gained=[t1],
            lost=[t2],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        msg = NarrativeMessage.objects.latest("id")
        self.assertIn("Flame Lash", msg.body)
        self.assertIn("Ash Step", msg.body)
        self.assertEqual(msg.category, NarrativeCategory.ABILITY)


class AnnounceAccessChangeDiscoveryAchievementTest(TestCase):
    def test_gained_with_discovery_achievement_fires_first_ever_gamewide(self):
        # `other` must have an active tenure so active_player_character_sheets() includes it.
        other = CharacterSheetFactory()
        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=other), end_date=None)
        ach = AchievementFactory(hidden=True)
        tech = TechniqueFactory(discovery_achievement=ach)
        sheet = CharacterSheetFactory()
        from world.achievements.discovery import announce_access_change

        announce_access_change(
            sheet,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        self.assertTrue(
            CharacterAchievement.objects.filter(character_sheet=sheet, achievement=ach).exists()
        )
        self.assertTrue(Discovery.objects.filter(achievement=ach).exists())
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=other).exists(),
            "Gamewide first-ever message should be delivered to other active sheet.",
        )


class AnnounceAccessChangeCapabilityTest(TestCase):
    def test_capabilities_ride_same_lists_without_covenant_branch(self):
        cap = CapabilityTypeFactory(name="phasewalk")
        sheet = CharacterSheetFactory()
        from world.achievements.discovery import announce_access_change

        announce_access_change(
            sheet,
            gained=[cap],
            lost=[],
            source=AccessChangeSource.COVENANT_ROLE_ENGAGED,
        )
        msg = NarrativeMessage.objects.latest("id")
        self.assertIn("phasewalk", msg.body)
