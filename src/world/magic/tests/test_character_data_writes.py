"""A player cannot write magic rows the game owns through the raw REST routes (#4898).

A gift is gained through ``grant_gift_to_character``, anima moves through its rituals, an
aura and resonances through their services. The router's own create, update and delete on
these viewsets skipped every one of those rules, so a player could give themselves any gift
or refill their anima. Those routes are staff-only now; reads keep their scope, and an
aura's glimpse actions (the web client's real writers) are untouched.
"""

from __future__ import annotations

from rest_framework.test import APITestCase

from evennia_extensions.factories import AccountFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.magic.constants import GiftKind
from world.magic.factories import (
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterGiftFactory,
    CharacterResonanceFactory,
    GiftFactory,
)
from world.magic.models import CharacterGift
from world.roster.factories import grant_test_tenure

GIFTS = "/api/magic/character-gifts/"


class _PlayerAndStaff(APITestCase):
    def setUp(self) -> None:
        self.player = AccountFactory()
        self.sheet = CharacterSheetFactory()
        grant_test_tenure(self.sheet, self.player)
        self.staff = AccountFactory(is_staff=True)
        self.client.force_authenticate(user=self.player)

    def as_staff(self) -> None:
        self.client.force_authenticate(user=self.staff)


class CharacterGiftWrites(_PlayerAndStaff):
    def setUp(self) -> None:
        super().setUp()
        self.gift = GiftFactory(name="Writes Gift", kind=GiftKind.MINOR)
        self.other_gift = GiftFactory(name="Writes Other", kind=GiftKind.MINOR)
        self.row = CharacterGiftFactory(character=self.sheet, gift=self.other_gift)

    def test_a_player_still_reads_their_gifts(self) -> None:
        response = self.client.get(GIFTS, {"character": self.sheet.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [self.row.pk])

    def test_a_player_cannot_create_update_or_delete(self) -> None:
        created = self.client.post(
            GIFTS, {"character": self.sheet.pk, "gift": self.gift.pk}, format="json"
        )
        patched = self.client.patch(f"{GIFTS}{self.row.pk}/", {"gift": self.gift.pk}, format="json")
        deleted = self.client.delete(f"{GIFTS}{self.row.pk}/")

        self.assertEqual(
            [created.status_code, patched.status_code, deleted.status_code], [403, 403, 403]
        )
        self.assertEqual(
            list(CharacterGift.objects.filter(character=self.sheet).values_list("gift", flat=True)),
            [self.other_gift.pk],
        )

    def test_a_player_cannot_create_a_row_on_someone_elses_sheet(self) -> None:
        stranger = CharacterSheetFactory()

        response = self.client.post(
            GIFTS, {"character": stranger.pk, "gift": self.gift.pk}, format="json"
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(CharacterGift.objects.filter(character=stranger).exists())

    def test_staff_create_update_and_delete(self) -> None:
        self.as_staff()

        created = self.client.post(
            GIFTS, {"character": self.sheet.pk, "gift": self.gift.pk}, format="json"
        )
        self.assertEqual(created.status_code, 201, created.content)
        third = GiftFactory(name="Writes Third", kind=GiftKind.MINOR)
        patched = self.client.patch(f"{GIFTS}{self.row.pk}/", {"gift": third.pk}, format="json")
        self.assertEqual(patched.status_code, 200, patched.content)
        deleted = self.client.delete(f"{GIFTS}{self.row.pk}/")
        self.assertEqual(deleted.status_code, 204)


class SiblingRowsAreNotPlayerWritable(_PlayerAndStaff):
    """The other character-data routes whose rows the game writes through services."""

    def _refused(self, url: str, pk: int, payload: dict) -> list[int]:
        return [
            self.client.post(url, payload, format="json").status_code,
            self.client.patch(f"{url}{pk}/", payload, format="json").status_code,
            self.client.delete(f"{url}{pk}/").status_code,
        ]

    def test_anima(self) -> None:
        anima = CharacterAnimaFactory(character=self.sheet, current=1, maximum=10)

        codes = self._refused(
            "/api/magic/character-anima/", anima.pk, {"character": self.sheet.pk, "current": 10}
        )

        self.assertEqual(codes, [403, 403, 403])
        anima.refresh_from_db()
        self.assertEqual(anima.current, 1)

    def test_resonances(self) -> None:
        held = CharacterResonanceFactory(character_sheet=self.sheet, balance=0)

        codes = self._refused(
            "/api/magic/character-resonances/",
            held.pk,
            {"character_sheet": self.sheet.pk, "balance": 999},
        )

        self.assertEqual(codes, [403, 403, 403])
        held.refresh_from_db()
        self.assertEqual(held.balance, 0)

    def test_aura(self) -> None:
        aura = CharacterAuraFactory(character=self.sheet)

        codes = self._refused("/api/magic/character-auras/", aura.pk, {"character": self.sheet.pk})

        self.assertEqual(codes, [403, 403, 403])
        self.assertEqual(self.client.get("/api/magic/character-auras/").status_code, 200)

    def test_the_gift_catalog(self) -> None:
        gift = GiftFactory(name="Writes Catalog", kind=GiftKind.MINOR)

        codes = self._refused("/api/magic/gifts/", gift.pk, {"name": "Renamed by a player"})

        self.assertEqual(codes, [403, 403, 403])
        gift.refresh_from_db()
        self.assertEqual(gift.name, "Writes Catalog")
