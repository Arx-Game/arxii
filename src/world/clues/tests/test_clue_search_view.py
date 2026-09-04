"""API tests for GET /api/clues/search/ (#3566).

The GM-only clue picker for the stake reward line editor: a GM (SENIOR+) or staff
account searches by name among clues whose target kind AUTOMATIC resolution can
actually deliver on its own. SECRET targets stay staff-only, and ITEM-target clues
never surface here (a bare pointer isn't a coherent reward payload).
"""

from rest_framework import status
from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.clues.constants import ClueTargetKind
from world.clues.factories import ClueFactory
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.items.factories import ItemTemplateFactory
from world.secrets.factories import SecretFactory

URL = "/api/clues/search/"


class ClueSearchViewTests(APITestCase):
    def test_player_without_profile_forbidden(self):
        account = AccountFactory()
        self.client.force_authenticate(user=account)
        response = self.client.get(URL)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_senior_gm_sees_codex_target_not_secret_target(self):
        account = AccountFactory()
        GMProfileFactory(account=account, level=GMLevel.SENIOR)
        codex_clue = ClueFactory(name="Torn Ledger Page")
        ClueFactory(
            name="Whispered Confession",
            target_kind=ClueTargetKind.SECRET,
            target_codex_entry=None,
            target_secret=SecretFactory(),
        )

        self.client.force_authenticate(user=account)
        response = self.client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data]
        assert codex_clue.name in names
        assert "Whispered Confession" not in names

    def test_staff_sees_both_codex_and_secret_targets(self):
        staff = AccountFactory(is_staff=True)
        codex_clue = ClueFactory(name="Torn Ledger Page")
        secret_clue = ClueFactory(
            name="Whispered Confession",
            target_kind=ClueTargetKind.SECRET,
            target_codex_entry=None,
            target_secret=SecretFactory(),
        )

        self.client.force_authenticate(user=staff)
        response = self.client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data]
        assert codex_clue.name in names
        assert secret_clue.name in names

    def test_item_target_clue_never_appears(self):
        staff = AccountFactory(is_staff=True)
        ClueFactory(
            name="Bloodied Dagger",
            target_kind=ClueTargetKind.ITEM,
            target_codex_entry=None,
            target_item_template=ItemTemplateFactory(),
        )

        self.client.force_authenticate(user=staff)
        response = self.client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data]
        assert "Bloodied Dagger" not in names

    def test_q_narrows_by_name(self):
        staff = AccountFactory(is_staff=True)
        ClueFactory(name="Torn Ledger Page")
        ClueFactory(name="Faded Portrait")

        self.client.force_authenticate(user=staff)
        response = self.client.get(URL, {"q": "ledger"})

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data]
        assert names == ["Torn Ledger Page"]

    def test_disallowed_rows_do_not_starve_an_allowed_row_off_the_page(self):
        """The target-kind policy filters before the top-25 slice, not after (#3566).

        A non-staff SENIOR GM cannot see SECRET-target clues. If the queryset were
        sliced to 25 rows first and filtered after, 26 alphabetically-early SECRET
        clues would fill the whole page and push an allowed, later-sorting clue off
        the result entirely.
        """
        account = AccountFactory()
        GMProfileFactory(account=account, level=GMLevel.SENIOR)
        for i in range(26):
            ClueFactory(
                name=f"Aardvark Secret Clue {i:02d}",
                target_kind=ClueTargetKind.SECRET,
                target_codex_entry=None,
                target_secret=SecretFactory(),
            )
        allowed_clue = ClueFactory(name="Zzyzx Allowed Clue")

        self.client.force_authenticate(user=account)
        response = self.client.get(URL, {"q": "clue"})

        assert response.status_code == status.HTTP_200_OK
        names = [row["name"] for row in response.data]
        assert allowed_clue.name in names
        assert all("Secret Clue" not in name for name in names)

    def test_result_rows_carry_exactly_id_name_target_kind(self):
        staff = AccountFactory(is_staff=True)
        clue = ClueFactory(name="Torn Ledger Page")

        self.client.force_authenticate(user=staff)
        response = self.client.get(URL)

        assert response.status_code == status.HTTP_200_OK
        row = response.data[0]
        assert set(row.keys()) == {"id", "name", "target_kind"}
        assert row["id"] == clue.id
        assert row["target_kind"] == ClueTargetKind.CODEX
