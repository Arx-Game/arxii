"""Journeys for Academy training that costs coin (#4523).

A TRAIN offer teaches a technique for a Golden Hare and, when staff price it, coin. Each
journey stands a learner in front of the Academy's trainer, takes the offer through the
real ``hire`` command, then reads back what she was told and what she still holds.

Names are invented. Staff-authored copy is left as bracketed slots.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import tag
from evennia.utils.ansi import strip_ansi

from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.action_points.models import ActionPointPool
from world.checks.factories import CheckTypeFactory
from world.checks.models import CheckType, CheckTypeTrait
from world.checks.test_helpers import force_check_outcome
from world.classes.factories import PathFactory
from world.currency.models import FavorTokenDetails
from world.currency.services import (
    get_or_create_purse,
    get_or_create_treasury,
    mint_favor_token,
    transfer,
)
from world.magic.constants import GiftKind, MagicActivity
from world.magic.factories import (
    CharacterGiftUnlockFactory,
    GiftFactory,
    GiftUnlockFactory,
    MagicActivitySkillFactory,
    PathGiftGrantFactory,
    ResonanceFactory,
    TechniqueFactory,
    TechniqueStyleFactory,
    TechniqueTeachingOfferFactory,
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
# A learner's first technique from a gift sizes its meter at 3 x the offer's 5 points.
FIRST_TECHNIQUE_METER = 15
# The self-study penalty: 20 tenths of a level's width, which the seeded ladder makes 8 points.
SELF_STUDY_PENALTY = 16
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
                "outsider_line": None,
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

    def _train_once(self, learner, *, by: str):
        """One session as ``learner``, rolled as a Success; returns the roll and the reply.

        ``by`` is ``telnet`` (the reply is the text she reads) or ``web`` (the reply is the
        dispatch result's message). Each call is one AP of training.
        """
        success = CheckOutcome.objects.get(name="Success")
        with force_check_outcome(success) as roll:
            if by == "telnet":
                reply = strip_ansi(self.telnet(learner, f"train {self.technique.name}=1"))
            else:
                result = self.web(learner, "train_technique", technique_id=self.technique.pk)
                self.assertTrue(result.detail.success, result.detail.message)
                reply = result.detail.message
        return roll, reply

    def _meter_rows(self, learner) -> dict:
        """The learner's technique meters as the progress list serves them, by technique."""
        response = self.api(self.account_of(learner)).get("/api/magic/technique-progress/")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["technique_id"]: row for row in response.data}

    def test_the_meter_carries_the_trainers_instruction_into_every_later_session(self) -> None:
        self._staff_author_training_check()
        self._ask_to_be_taught(self.hobb)
        sheet = self.hobb.sheet_data
        meter = TechniqueProgress.objects.get(character_sheet=sheet, technique=self.technique)
        self.assertEqual(meter.instruction_bonus, INSTRUCTION_BONUS)
        self.assertEqual(meter.total_required, FIRST_TECHNIQUE_METER)

        # Staff retune the offer afterwards; the meter she already holds keeps its own value,
        # and a restart (a cold identity map) reads it back from the row.
        self.details.instruction_bonus = 3
        self.details.save()
        TechniqueProgress.flush_instance_cache()
        meter = TechniqueProgress.objects.get(character_sheet=sheet, technique=self.technique)
        self.assertEqual(meter.instruction_bonus, INSTRUCTION_BONUS)

        # The trainer is never in the hall. Each session still rolls her bonus from the meter
        # (not the retuned 3) and the style's skill once, by telnet and by the web dispatch,
        # and the line she reads names the points her meter now holds.
        roll, told = self._train_once(self.hobb, by="telnet")
        self.assertIn(
            f"You train {self.technique.name} (Success): 1/{FIRST_TECHNIQUE_METER}.", told
        )
        self.assertEqual(roll.extra_modifiers, INSTRUCTION_BONUS)
        self.assertEqual([term.trait.pk for term in roll.extra_traits], [self.style_skill.pk])
        roll, message = self._train_once(self.hobb, by="web")
        self.assertEqual(
            message, f"You train {self.technique.name} (Success): 2/{FIRST_TECHNIQUE_METER}."
        )
        self.assertEqual(roll.extra_modifiers, INSTRUCTION_BONUS)
        meter.refresh_from_db()
        self.assertEqual(meter.points_accumulated, 2)

        # Her own progress list calls the Academy's meter paid instruction, not self-study.
        (row,) = self._meter_rows(self.hobb).values()
        self.assertFalse(row["is_self_study"])
        self.assertIsNone(row["teacher_name"])

    def test_the_style_skill_counts_once_however_staff_wired_it(self) -> None:
        self._staff_author_training_check()
        self._ask_to_be_taught(self.hobb)

        # Staff already mapped the style's skill to technique learning at weight 0.5: it
        # keeps that weight and is not added again at the technique's own weight.
        mapping = MagicActivitySkillFactory(
            activity=MagicActivity.TECHNIQUE_LEARNING, skill=self.style_skill, weight=Decimal("0.5")
        )
        roll, _ = self._train_once(self.hobb, by="telnet")
        self.assertEqual(
            [(term.trait.pk, term.weight) for term in roll.extra_traits],
            [(self.style_skill.pk, Decimal("0.5"))],
        )

        # Unmapped, but the Technique Training check type already weights that skill: the
        # check type counts it, so the roll adds no term of its own.
        mapping.delete()
        CheckTypeTrait.objects.create(
            check_type=CheckType.objects.get(name="Technique Training"),
            trait=self.style_skill,
            weight=Decimal("1.0"),
        )
        roll, _ = self._train_once(self.hobb, by="telnet")
        self.assertEqual(roll.extra_traits, ())

    def test_paid_instruction_is_not_self_study_though_the_teacher_is_away(self) -> None:
        self._staff_author_training_check()
        self._ask_to_be_taught(self.hobb)
        # Ysmay takes up the same technique from a player, Wren, through the real accept
        # action, then Wren leaves the hall: her meter trains at self-study rates.
        wren = self.make_player("Wren", room=self.hall)
        teaching = TechniqueTeachingOfferFactory(
            teacher=wren.sheet_data.roster_entry.tenures.get(end_date__isnull=True),
            technique=self.technique,
            learn_ap_cost=5,
            banked_ap=0,
        )
        told = strip_ansi(self.telnet(self.ysmay, f"learn technique {teaching.pk}"))
        self.assertIn(f"You learn {self.technique.name}.", told)
        wren.move_to(self.make_room("The Road"), quiet=True)

        academy_roll, _ = self._train_once(self.hobb, by="telnet")
        self_study_roll, _ = self._train_once(self.ysmay, by="telnet")

        # The Academy roll is easier by exactly the self-study penalty, carries the bonus,
        # and both rolls carry the style's skill once.
        self.assertEqual(
            self_study_roll.target_difficulty - academy_roll.target_difficulty, SELF_STUDY_PENALTY
        )
        self.assertEqual(academy_roll.extra_modifiers, INSTRUCTION_BONUS)
        self.assertFalse(self_study_roll.extra_modifiers)
        for roll in (academy_roll, self_study_roll):
            self.assertEqual([term.trait.pk for term in roll.extra_traits], [self.style_skill.pk])

        # The web dispatch agrees: Ysmay's session is self-study, Hobb's is not.
        self.assertTrue(self._train_once_data(self.ysmay)["self_study"])
        self.assertFalse(self._train_once_data(self.hobb)["self_study"])

        # Her list names the teacher, so it is not self-study either; his names none.
        hobb_row = self._meter_rows(self.hobb)[self.technique.pk]
        ysmay_row = self._meter_rows(self.ysmay)[self.technique.pk]
        self.assertFalse(hobb_row["is_self_study"])
        self.assertIn("Wren", ysmay_row["teacher_name"])
        self.assertFalse(ysmay_row["is_self_study"])

    @tag("regression")
    def test_a_teacher_is_not_present_when_neither_character_is_in_the_world(self) -> None:
        """Regression for #2741. A player teacher counts only when standing in the learner's
        room. With both characters out of the world (no room at all) the web session must
        train at self-study rates, not as if the two shared a room."""
        self._staff_author_training_check()
        wren = self.make_player("Wren", room=self.hall)
        teaching = TechniqueTeachingOfferFactory(
            teacher=wren.sheet_data.roster_entry.tenures.get(end_date__isnull=True),
            technique=self.technique,
            learn_ap_cost=5,
            banked_ap=0,
        )
        self.telnet(self.ysmay, f"learn technique {teaching.pk}")
        for character in (wren, self.ysmay):
            character.location = None
            character.save()
        self.assertTrue(self._train_once_data(self.ysmay)["self_study"])

    def _train_once_data(self, learner) -> dict:
        result = self.web(learner, "train_technique", technique_id=self.technique.pk)
        self.assertTrue(result.detail.success, result.detail.message)
        return result.detail.data
