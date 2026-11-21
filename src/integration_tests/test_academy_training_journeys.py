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
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
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
    TechniqueStyleFactory,
)
from world.magic.models import CharacterTechnique, TechniqueProgress, TrainingOutcomeAward
from world.npc_services.constants import OfferKind
from world.npc_services.factories import (
    FunctionaryFactory,
    NPCRoleFactory,
    NPCServiceOfferFactory,
    TrainOfferDetailsFactory,
)
from world.progression.factories import CharacterPathHistoryFactory
from world.seeds.modifier_values import seed_pool_and_cap_lanes
from world.skills.factories import MagicSkillFactory
from world.societies.factories import OrganizationFactory
from world.traits.factories import ensure_level_ladder
from world.traits.models import CheckOutcome

# What staff priced the training at: 2 gold and 5 silver, written in coppers.
PRICE = 250
STARTING_AP = 200
# What staff set the trainer's instruction at, in check points.
INSTRUCTION_BONUS = 12
# The trainer's menu line: the coin and Hare paid now, then training sized by learn_ap_cost.
MENU_LINE = "2g 5s · 1 Golden Hare · 5 points of training or more, paid in AP"


class TrainingAtTheAcademy(JourneyCase):
    """Ysmay and Hobb each ask Master Orsolya to teach them a technique for 2g 5s and a Hare."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        seed_pool_and_cap_lanes()

    def setUp(self) -> None:
        super().setUp()
        self.hall = self.make_room("The Shroudwatch Hall")
        self.academy = OrganizationFactory(name="Shroudwatch Academy")
        self.path = PathFactory()
        # The gift's style has a casting skill, so a session also rolls that skill.
        self.style_skill = MagicSkillFactory(name="Steelwork")
        self.style = TechniqueStyleFactory(name="Steel", skill=self.style_skill)
        self.gift = GiftFactory(kind=GiftKind.MINOR, style=self.style)
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
        self.details = TrainOfferDetailsFactory(
            offer=self.offer,
            technique=self.technique,
            learn_ap_cost=5,
            gold_cost=PRICE,
            instruction_bonus=INSTRUCTION_BONUS,
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

    def _staff_author_training_check(self) -> None:
        """The content a session rolls on: the Technique Training check and its Success payout."""
        ensure_level_ladder()
        CheckTypeFactory(name="Technique Training")
        success, _ = CheckOutcome.objects.get_or_create(
            name="Success", defaults={"success_level": 1}
        )
        TrainingOutcomeAward.objects.update_or_create(
            outcome_tier=success, defaults={"dev_point_multiplier": 1}
        )

    def test_the_meter_carries_the_trainers_instruction_into_every_later_session(self) -> None:
        self._staff_author_training_check()
        self._ask_to_be_taught(self.hobb)
        sheet = self.hobb.sheet_data
        meter = TechniqueProgress.objects.get(character_sheet=sheet, technique=self.technique)
        self.assertEqual(meter.instruction_bonus, INSTRUCTION_BONUS)

        # Staff retune the offer afterwards; the meter she already holds keeps its own value,
        # and a restart (a cold identity map) reads it back from the row.
        self.details.instruction_bonus = 3
        self.details.save()
        TechniqueProgress.flush_instance_cache()
        meter = TechniqueProgress.objects.get(character_sheet=sheet, technique=self.technique)
        self.assertEqual(meter.instruction_bonus, INSTRUCTION_BONUS)

        # The trainer is never in the hall. Each session still rolls her bonus from the meter
        # (not the retuned 3) and the style's skill once, by telnet and by the web dispatch.
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as roll:
            told = strip_ansi(self.telnet(self.hobb, f"train {self.technique.name}=2"))
        self.assertIn(f"You train {self.technique.name} (Success)", told)
        self.assertEqual(roll.extra_modifiers, INSTRUCTION_BONUS)
        self.assertEqual([term.trait.pk for term in roll.extra_traits], [self.style_skill.pk])
        with force_check_outcome(success) as roll:
            result = self.web(self.hobb, "train_technique", technique_id=self.technique.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        self.assertFalse(result.detail.data["self_study"])
        self.assertEqual(roll.extra_modifiers, INSTRUCTION_BONUS)
        meter.refresh_from_db()
        self.assertGreater(meter.points_accumulated, 0)
