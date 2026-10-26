"""Journeys for Academy training that costs coin (#4523).

A TRAIN offer teaches a technique for a Golden Hare and, when staff price it, coin. Each
journey stands a learner in front of the Academy's trainer, takes the offer through the
real ``hire`` command, then reads back what she was told and what she still holds.

Names are invented. Staff-authored copy is left as bracketed slots.
"""

from __future__ import annotations

from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointPool
from world.classes.factories import PathFactory
from world.currency.models import FavorTokenDetails
from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    mint_favor_token,
    transfer,
)
from world.magic.constants import GiftKind
from world.magic.factories import (
    CharacterGiftUnlockFactory,
    GiftFactory,
    GiftUnlockFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
)
from world.magic.models import CharacterTechnique, TechniqueProgress
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    FunctionaryFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
    TrainOfferDetailsFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.societies.factories import OrganizationFactory

# What staff priced the training at: 2 gold and 5 silver, written in coppers.
PRICE = 250
STARTING_AP = 200
# The trainer's menu line: the coin and Hare paid now, then training sized by learn_ap_cost.
MENU_LINE = "2g 5s · 1 Golden Hare · 5 points of training or more, paid in AP"


class TrainingAtTheAcademy(JourneyCase):
    """Ysmay and Hobb each ask Master Orsolya to teach them a technique for 2g 5s and a Hare."""

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("The Shroudwatch Hall")
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.path = PathFactory()
        self.gift = GiftFactory(kind=GiftKind.MINOR)
        self.gift.resonances.add(ResonanceFactory())
        self.unlock = GiftUnlockFactory(gift=self.gift)
        self.technique = TechniqueFactory(gift=self.gift)
        PathGiftGrantFactory(path=self.path, gift=self.gift).starter_techniques.add(self.technique)

        self.role = NPCRoleFactory(name="Academy Trainer", faction_affiliation=self.academy)
        FunctionaryFactory(
            role=self.role,
            room=RoomProfileFactory(objectdb=self.hall),
            name_override="Master Orsolya",
        )
        self.offer = NPCServiceOfferFactory(
            role=self.role, kind=OfferKind.TRAIN, label="Learn a technique", is_final=True
        )
        TrainOfferDetailsFactory(
            offer=self.offer, technique=self.technique, learn_ap_cost=5, gold_cost=PRICE
        )

        self.ysmay = self._learner("Ysmay", coppers=90)
        self.hobb = self._learner("Hobb", coppers=400)
        self.hares = {
            name: mint_favor_token(self.academy, learner.sheet_data, provenance_note="a deed")
            for name, learner in (("Ysmay", self.ysmay), ("Hobb", self.hobb))
        }

    def _learner(self, name: str, *, coppers: int):
        """A player on the Academy's path who holds the gift's receipt, 200 AP and some coin."""
        learner = self.make_player(name, room=self.hall)
        sheet = learner.sheet_data
        CharacterPathHistoryFactory(character=sheet, path=self.path)
        CharacterGiftUnlockFactory(character=sheet, unlock=self.unlock)
        pool = ActionPointPool.get_or_create_for_character(learner)
        pool.current = STARTING_AP
        pool.save()
        transfer(
            amount=coppers, reason="a purse for the journey", to_purse=get_or_create_purse(sheet)
        )
        return learner

    def _ask_to_be_taught(self, learner) -> str:
        self.telnet(learner, "hire Master Orsolya")
        return strip_ansi(self.telnet(learner, f"hire offer {self.offer.pk}"))

    def _hare_is_unspent(self, name: str) -> bool:
        return FavorTokenDetails.objects.get(pk=self.hares[name].pk).redeemed_at is None

    def test_a_learner_short_of_coin_is_told_the_price_and_her_purse(self) -> None:
        told = self._ask_to_be_taught(self.ysmay)

        self.assertIn("This training costs 2g 5s and you have 9s.", told)
        self.assertNotIn("Hare", told)
        # Nothing was taken from her and nothing was started.
        sheet = self.ysmay.sheet_data
        self.assertEqual(get_or_create_purse(sheet).balance, 90)
        self.assertEqual(get_or_create_treasury(self.academy).balance, 0)
        self.assertEqual(
            ActionPointPool.get_or_create_for_character(self.ysmay).current, STARTING_AP
        )
        self.assertTrue(self._hare_is_unspent("Ysmay"))
        self.assertFalse(TechniqueProgress.objects.filter(character_sheet=sheet).exists())
        self.assertFalse(CharacterTechnique.objects.filter(character=sheet).exists())

    def test_a_learner_with_the_coin_and_a_hare_begins_training(self) -> None:
        told = self._ask_to_be_taught(self.hobb)

        self.assertIn(
            f"Shroudwatch Academy's trainer begins your training in {self.technique.name}.", told
        )
        self.assertNotIn("costs", told)
        sheet = self.hobb.sheet_data
        self.assertTrue(TechniqueProgress.objects.filter(character_sheet=sheet).exists())
        # The coin went to the Academy, the Hare was called in, and AP is spent per session.
        self.assertEqual(get_or_create_purse(sheet).balance, 400 - PRICE)
        self.assertEqual(get_or_create_treasury(self.academy).balance, PRICE)
        self.assertFalse(self._hare_is_unspent("Hobb"))
        self.assertEqual(
            ActionPointPool.get_or_create_for_character(self.hobb).current, STARTING_AP
        )

    def test_she_can_return_once_she_has_the_coin(self) -> None:
        self._ask_to_be_taught(self.ysmay)
        transfer(
            amount=PRICE,
            reason="a purse for the journey",
            to_purse=get_or_create_purse(self.ysmay.sheet_data),
        )

        told = self._ask_to_be_taught(self.ysmay)

        self.assertIn("begins your training", told)
        self.assertEqual(get_or_create_purse(self.ysmay.sheet_data).balance, 90)
        self.assertFalse(self._hare_is_unspent("Ysmay"))

    def test_telnet_line_names_the_hare_and_coin_and_no_ap_charge(self) -> None:
        menu = strip_ansi(self.telnet(self.hobb, "hire Master Orsolya"))
        self.assertRegex(menu, rf"Learn a technique.*{MENU_LINE}")

        # The line is right: accepting took the coin and the Hare, not a single AP.
        self.telnet(self.hobb, f"hire offer {self.offer.pk}")
        self.assertEqual(
            ActionPointPool.get_or_create_for_character(self.hobb).current, STARTING_AP
        )
        self.assertEqual(get_or_create_purse(self.hobb.sheet_data).balance, 400 - PRICE)
        self.assertFalse(self._hare_is_unspent("Hobb"))

    def test_web_menu_carries_the_same_line(self) -> None:
        client = self.api(self.account_of(self.hobb))
        response = client.post(
            "/api/npc-services/interactions/start/", {"role_id": self.role.pk}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        (offer,) = response.data["available_offers"]
        self.assertEqual(
            offer["price"],
            {
                "ap": 0,
                "coppers": PRICE,
                "golden_hares": 1,
                "per_session_ap": None,
                "development_remaining": None,
                "development_total": None,
                "training_points": 5,
                "teaching_line": None,
                "fit_line": None,
                "display": MENU_LINE,
            },
        )
