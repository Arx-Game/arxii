"""Rivalry services — double-opt-in mutual rivalry (#2170)."""

from django.test import TestCase

from world.roster.factories import RosterTenureFactory
from world.scenes.friend_services import (
    declare_rival,
    is_rival,
    rivaled_tenures_for,
    undeclare_rival,
)
from world.scenes.models import Rivalry


class RivalryServicesTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.a = RosterTenureFactory()
        cls.b = RosterTenureFactory()

    def test_one_sided_declaration_is_not_a_rivalry(self) -> None:
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        # Double opt-in: A named B, but B hasn't named A — not mutual, so not a RIVALS-mode pass.
        self.assertFalse(is_rival(owner_tenure=self.a, rival_tenure=self.b))
        self.assertFalse(is_rival(owner_tenure=self.b, rival_tenure=self.a))

    def test_mutual_declaration_is_a_rivalry_both_ways(self) -> None:
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        declare_rival(rivaler_tenure=self.b, rival_tenure=self.a)
        self.assertTrue(is_rival(owner_tenure=self.a, rival_tenure=self.b))
        self.assertTrue(is_rival(owner_tenure=self.b, rival_tenure=self.a))

    def test_declare_is_idempotent(self) -> None:
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        self.assertEqual(Rivalry.objects.filter(rivaler_tenure=self.a).count(), 1)

    def test_undeclare_breaks_mutuality(self) -> None:
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        declare_rival(rivaler_tenure=self.b, rival_tenure=self.a)
        self.assertTrue(undeclare_rival(rivaler_tenure=self.a, rival_tenure=self.b))
        self.assertFalse(is_rival(owner_tenure=self.a, rival_tenure=self.b))

    def test_alt_privacy_one_character_does_not_declare_for_another(self) -> None:
        other = RosterTenureFactory(player_data=self.a.player_data)
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        declare_rival(rivaler_tenure=self.b, rival_tenure=self.a)
        # The mutual rivalry is A↔B; the same player's other character is not dragged in.
        self.assertFalse(is_rival(owner_tenure=other, rival_tenure=self.b))

    def test_rivaled_tenures_for_lists_declarations(self) -> None:
        declare_rival(rivaler_tenure=self.a, rival_tenure=self.b)
        self.assertIn(self.b, list(rivaled_tenures_for(self.a)))
