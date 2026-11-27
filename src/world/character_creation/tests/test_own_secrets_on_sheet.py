"""A player's sheet shows them their own secrets after approval (#5206).

Owner ruling (2026-11-26): a sheet shows its own player everything but GM and staff notes,
so a player always sees the secrets about their character that the character knows, even
though no other player sees them unless they are shared. A secret the character does not
know about itself (``subject_aware=False``) is GM material and stays off.
"""

from __future__ import annotations

from django.test import TestCase
from evennia.accounts.models import AccountDB
from rest_framework.test import APIClient

from world.character_creation.services import submit_draft_for_review
from world.character_creation.tests.finalization_fixtures import FinalizationTestMixin
from world.character_sheets.models import CharacterSheet
from world.distinctions.factories import DistinctionFactory
from world.roster.models import RosterEntry
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.services import author_secret

CARD_NAME = "Hidden Shame"
WHISPER = "Ione once sank a ship."
UNAWARE = "Ione is not her mother's daughter."


class OwnSecretsOnTheSheetTest(FinalizationTestMixin, TestCase):
    def setUp(self) -> None:
        self._flush_common_caches()
        self.account = AccountDB.objects.create(username="own_secrets_owner")
        self.staff = AccountDB.objects.create(username="own_secrets_staff", is_staff=True)
        self.stranger = AccountDB.objects.create(username="own_secrets_stranger")
        self._setup_finalization_base(self, prefix="Own", height_min=700, height_max=800)
        card = DistinctionFactory(name=CARD_NAME, cost_per_rank=0, secret_by_default=True)
        self.draft = self._create_base_draft(
            first_name="Ione",
            distinctions=[
                {"distinction_id": card.pk, "distinction_name": CARD_NAME, "rank": 1, "cost": 0}
            ],
            introductions={"whispers": WHISPER},
        )

    def _approve(self) -> int:
        application = submit_draft_for_review(self.draft)
        staff = APIClient()
        staff.force_authenticate(user=self.staff)
        base = f"/api/character-creation/applications/{application.pk}"
        staff.post(f"{base}/claim/")
        self.assertEqual(staff.post(f"{base}/approve/").status_code, 200)
        sheet_id = RosterEntry.objects.get(
            tenures__player_data__account=self.account
        ).character_sheet_id
        author_secret(
            subject_sheet=CharacterSheet.objects.get(pk=sheet_id),
            provenance=SecretProvenance.GM_AUTHORED,
            level=SecretLevel.DANGEROUS,
            content=UNAWARE,
            subject_aware=False,
        )
        return sheet_id

    def _secrets(self, account: AccountDB, sheet_id: int) -> list[dict]:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(f"/api/character-sheets/{sheet_id}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["secrets"]

    def test_the_owner_reads_their_own_secrets(self) -> None:
        sheet_id = self._approve()

        contents = [row["content"] for row in self._secrets(self.account, sheet_id)]

        self.assertIn(CARD_NAME, contents)
        self.assertIn(WHISPER, contents)
        self.assertNotIn(UNAWARE, contents)

    def test_a_stranger_reads_none_of_them(self) -> None:
        sheet_id = self._approve()

        self.assertEqual(self._secrets(self.stranger, sheet_id), [])
