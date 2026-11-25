"""A secret card's name stays off the Bonuses band for anyone but its owner and staff (#5206).

The band follows the statistics' visibility, so a player who opens their statistics to
the public shows every bonus total. A card relocated into a Secret is hidden from the
distinctions list for such a viewer, and its name must not reach them through the band's
source lines either; the total still counts it, as the buffed statistic does.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.services import submit_draft_for_review
from world.character_creation.tests.finalization_fixtures import (
    DEFAULT_STATS,
    FinalizationTestMixin,
)
from world.character_sheets.models import CharacterSheet
from world.character_sheets.types import SheetVisibility
from world.distinctions.factories import DistinctionEffectFactory, DistinctionFactory
from world.mechanics.constants import STAT_CATEGORY_NAME
from world.mechanics.factories import ModifierCategoryFactory, ModifierTargetFactory
from world.roster.models import RosterEntry
from world.traits.models import Trait

CARD_NAME = "Secretly Gifted"


class SecretCardsOffTheBonusesBandTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="secret_owner")
        self.staff = AccountDB.objects.create(username="secret_staff", is_staff=True)
        self.stranger = AccountDB.objects.create(username="secret_stranger")
        self._setup_finalization_base(self, prefix="Secret", height_min=700, height_max=800)
        charm = ModifierTargetFactory(
            name="charm",
            category=ModifierCategoryFactory(name=STAT_CATEGORY_NAME),
            target_trait=Trait.objects.get(name="charm"),
        )
        card = DistinctionFactory(name=CARD_NAME, cost_per_rank=0, secret_by_default=True)
        DistinctionEffectFactory(distinction=card, target=charm, value_per_rank=10)
        self.draft = self._create_base_draft(
            first_name="Vey",
            stats={**DEFAULT_STATS, "willpower": 30},
            distinctions=[
                {"distinction_id": card.pk, "distinction_name": CARD_NAME, "rank": 1, "cost": 0}
            ],
        )

    def _approve(self) -> int:
        application = submit_draft_for_review(self.draft)
        staff = APIClient()
        staff.force_authenticate(user=self.staff)
        base = f"/api/character-creation/applications/{application.pk}"
        staff.post(f"{base}/claim/")
        self.assertEqual(staff.post(f"{base}/approve/").status_code, 200)
        entry = RosterEntry.objects.get(tenures__player_data__account=self.account)
        sheet = CharacterSheet.objects.get(pk=entry.character_sheet_id)
        sheet.stats_visibility = SheetVisibility.PUBLIC
        sheet.save(update_fields=["stats_visibility"])
        return entry.character_sheet_id

    def _source_labels(self, account: AccountDB, sheet_id: int) -> tuple[list[str], list]:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(f"/api/character-sheets/{sheet_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        bonuses = response.data["bonuses"]
        labels = [
            source["label"]
            for group in bonuses
            for row in group["rows"]
            for source in row["sources"]
        ]
        return labels, bonuses

    def test_a_stranger_reads_the_total_but_not_the_secret_cards_name(self) -> None:
        sheet_id = self._approve()

        labels, bonuses = self._source_labels(self.stranger, sheet_id)

        self.assertNotIn(CARD_NAME, labels)
        (row,) = [row for group in bonuses for row in group["rows"] if row["target"] == "charm"]
        self.assertEqual(row["total"], 10)

    def test_the_owner_reads_the_secret_cards_name(self) -> None:
        sheet_id = self._approve()

        labels, _bonuses = self._source_labels(self.account, sheet_id)

        self.assertIn(CARD_NAME, labels)
