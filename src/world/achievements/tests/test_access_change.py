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


class AnnounceAccessChangeDiscoveryIdempotencyTest(TestCase):
    """Ceremony must fire at most once per character per achievement."""

    def test_regrant_discoverer_fires_ceremony_only_once(self):
        """Calling announce_access_change twice for the same discoverer must not re-fire the
        ceremony on the second call."""
        other = CharacterSheetFactory()
        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=other), end_date=None)
        ach = AchievementFactory(hidden=True)
        tech = TechniqueFactory(discovery_achievement=ach)
        sheet = CharacterSheetFactory()
        from world.achievements.discovery import announce_access_change

        # First call — should fire the first-ever gamewide ceremony.
        announce_access_change(
            sheet,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        # Count deliveries to `other` (active sheet): only ceremony messages reach it, not
        # personal access-change messages.  This is the canary for ceremony re-fire.
        ceremony_deliveries_after_first = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=other
        ).count()
        ca_count_after_first = CharacterAchievement.objects.filter(
            achievement=ach, character_sheet=sheet
        ).count()
        self.assertEqual(
            ca_count_after_first, 1, "CharacterAchievement should exist after first grant"
        )
        self.assertEqual(
            ceremony_deliveries_after_first, 1, "One gamewide ceremony delivery to other"
        )

        # Second call (same technique re-gained, e.g. assume→revert→assume) — must be a no-op for
        # the discovery ceremony.
        announce_access_change(
            sheet,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        ceremony_deliveries_after_second = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=other
        ).count()
        ca_count_after_second = CharacterAchievement.objects.filter(
            achievement=ach, character_sheet=sheet
        ).count()

        # The ceremony delivery count to `other` must not have grown.
        self.assertEqual(
            ceremony_deliveries_after_first,
            ceremony_deliveries_after_second,
            "No additional ceremony NarrativeMessageDelivery to 'other' on the second call.",
        )
        self.assertEqual(
            ca_count_after_second, 1, "CharacterAchievement must remain exactly one row."
        )

    def test_later_earner_gets_personal_not_gamewide_and_only_once(self):
        """A second character gaining the same discoverable technique gets a personal (not
        gamewide first-ever) message, and a third call for that same character fires nothing."""
        other = CharacterSheetFactory()
        RosterTenureFactory(roster_entry=RosterEntryFactory(character_sheet=other), end_date=None)
        ach = AchievementFactory(hidden=True)
        tech = TechniqueFactory(discovery_achievement=ach)
        first_discoverer = CharacterSheetFactory()
        second_earner = CharacterSheetFactory()
        from world.achievements.discovery import announce_access_change

        # First discoverer claims the first-ever ceremony.
        announce_access_change(
            first_discoverer,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )

        # Second earner triggers a personal ceremony only.
        announce_access_change(
            second_earner,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        # The most recent NarrativeMessage whose body is a ceremony (not an access-change list)
        # should be the personal ceremony for second_earner.  Filter by body content.
        ceremony_msgs = NarrativeMessage.objects.filter(body__icontains="manifested").order_by(
            "-id"
        )
        self.assertTrue(
            ceremony_msgs.exists(), "Expected at least one 'manifested' ceremony message"
        )
        personal_msg = ceremony_msgs.first()
        self.assertIn(
            "You have manifested",
            personal_msg.body,
            "Second earner should receive a personal 'You have manifested' message.",
        )
        self.assertNotIn(
            "first time in recorded history",
            personal_msg.body,
            "Second earner must NOT receive the gamewide first-ever message body.",
        )
        # Delivery should be to second_earner only, not gamewide.
        self.assertTrue(
            NarrativeMessageDelivery.objects.filter(
                message=personal_msg, recipient_character_sheet=second_earner
            ).exists()
        )
        self.assertFalse(
            NarrativeMessageDelivery.objects.filter(
                message=personal_msg, recipient_character_sheet=other
            ).exists(),
            "Gamewide recipient (other) must NOT receive the personal message.",
        )

        # Count ceremony deliveries to `other` before and after the third call.
        ceremony_deliveries_before = NarrativeMessageDelivery.objects.filter(
            recipient_character_sheet=other
        ).count()
        # Third call for same second_earner — must be a no-op for the ceremony.
        announce_access_change(
            second_earner,
            gained=[tech],
            lost=[],
            source=AccessChangeSource.ASSUMED_ALTERNATE_SELF,
        )
        self.assertEqual(
            ceremony_deliveries_before,
            NarrativeMessageDelivery.objects.filter(recipient_character_sheet=other).count(),
            "No additional ceremony deliveries to 'other' on repeat call for second earner.",
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
