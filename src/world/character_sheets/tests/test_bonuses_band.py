"""The sheet payload's Bonuses band follows the stats section's visibility (#5206)."""

from __future__ import annotations

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from evennia_extensions.models import PlayerData
from world.distinctions.factories import (
    CharacterDistinctionFactory,
    DistinctionEffectFactory,
    DistinctionFactory,
)
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.mechanics.services import create_distinction_modifiers
from world.roster.factories import RosterEntryFactory, RosterTenureFactory


class BonusesBandTests(APITestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.owner = AccountFactory()
        roster_entry = RosterEntryFactory()
        owner_data, _ = PlayerData.objects.get_or_create(account=cls.owner)
        RosterTenureFactory(player_data=owner_data, roster_entry=roster_entry)
        cls.sheet = roster_entry.character_sheet  # stats visibility defaults to SELF

        aspect = ModifierCategoryFactory(name="aspect")
        martial = ModifierTargetFactory(category=aspect, name="martial", description="Of war.")
        soldier = DistinctionFactory(name="Example Soldier")
        DistinctionEffectFactory(distinction=soldier, target=martial, value_per_rank=5)
        create_distinction_modifiers(
            CharacterDistinctionFactory(character=cls.sheet, distinction=soldier)
        )

        cls.stranger = AccountFactory()
        stranger_data, _ = PlayerData.objects.get_or_create(account=cls.stranger)
        RosterTenureFactory(player_data=stranger_data, roster_entry=RosterEntryFactory())

    def _bonuses(self, viewer) -> list:
        self.client.force_authenticate(user=viewer)
        return self.client.get(f"/api/character-sheets/{self.sheet.pk}/").data["bonuses"]

    def test_owner_receives_the_band(self) -> None:
        self.assertEqual(
            self._bonuses(self.owner),
            [
                {
                    "category": "aspect",
                    "heading": "Aspect",
                    "rows": [
                        {
                            "target": "martial",
                            "label": "martial",
                            "definition": "Of war.",
                            "total": 5,
                            "immune": False,
                            "sources": [{"label": "Example Soldier", "value": 5}],
                        }
                    ],
                }
            ],
        )

    def test_stranger_gets_nothing_while_stats_are_private(self) -> None:
        self.assertEqual(self._bonuses(self.stranger), [])
