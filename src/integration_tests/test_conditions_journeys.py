"""Journeys through the conditions a character carries (#3657, tranche 1 pilot).

Each journey types what a player types, or sends what the web client sends,
and asserts what the player was told. The die is pinned (``ROLL_WELL``): the
roll is the one thing a journey cannot drive and still be a journey.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import tag

from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.models import ConsequenceEffect
from world.conditions.constants import BreakFreeMode, TreatmentTargetKind
from world.conditions.factories import (
    ConditionCategoryFactory,
    ConditionInstanceFactory,
    ConditionTemplateFactory,
    TreatmentTemplateFactory,
)
from world.conditions.models import ConditionInstance
from world.conditions.services import apply_condition, has_condition
from world.gm.constants import GMLevel
from world.gm.factories import GMProfileFactory
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    CharacterAnimaFactory,
    RestoreToSenseActionTemplateFactory,
)
from world.progression.seeds import seed_social_engagement_kudos_category
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.models import Interaction, Scene
from world.seeds.game_content.social import SocialContent
from world.traits.factories import CheckSystemSetupFactory
from world.vitals.constants import SLEEPING_CONDITION_NAME
from world.vitals.models import CharacterVitals, WoundDetails

# A roll of 95 lands in the top band of every chart CheckSystemSetupFactory builds.
ROLL_WELL = patch("world.checks.services.random.randint", return_value=95)
# A roll of 1 lands in the bottom band.
ROLL_BADLY = patch("world.checks.services.random.randint", return_value=1)


def severity_of(instance: ConditionInstance) -> int:
    """The severity the database holds (``refresh_from_db`` is a no-op on idmapper rows)."""
    return ConditionInstance.objects.filter(pk=instance.pk).values_list("severity", flat=True).get()


def feed_of(scene: Scene) -> list[str]:
    """What the scene's feed shows, oldest first. Outcome and narration lines are
    recorded here and pushed to connected sessions; a harness character has no
    session, so the feed row is the player-facing copy a journey can read."""
    rows = Interaction.objects.filter(scene=scene).order_by("pk")
    return list(rows.values_list("content", flat=True))


def fresh_check_system() -> None:
    """Outcomes and charts for the roll (the chart cache is emptied between tests)."""
    CheckSystemSetupFactory.create()


class ShakingOffACharm(JourneyCase):
    """Ysmay is under a charm that alters her behavior and fights it off herself."""

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.hobb)
        charm = ConditionTemplateFactory(
            name="Honeyed Words",
            category=ConditionCategoryFactory(name="Charm", alters_behavior=True),
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(name="Resolve"),
            break_free_difficulty=10,
        )
        self.charm = ConditionInstanceFactory(target=self.ysmay, condition=charm, severity=3)

    def test_she_pushes_back_and_the_hold_weakens(self) -> None:
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "breakfree")
        self.assertIn("You push back against the effect, weakening its hold.", told)
        self.assertEqual(severity_of(self.charm), 2)
        self.assertNotTold(self.hobb, "weakening its hold")

    def test_a_second_try_at_once_is_refused(self) -> None:
        with ROLL_WELL:
            self.telnet(self.ysmay, "breakfree")
        told = self.telnet(self.ysmay, "breakfree")
        self.assertIn("You are still fighting the grip of the effect.", told)
        self.assertEqual(severity_of(self.charm), 2)

    def test_with_nothing_to_fight_he_is_told_so(self) -> None:
        self.assertIn("You have nothing you can fight off.", self.telnet(self.hobb, "breakfree"))

    def test_a_friend_rallies_her_and_her_next_attempt_carries_it(self) -> None:
        with ROLL_WELL:
            told = self.telnet(self.hobb, "rally Ysmay")
        self.assertIn(
            "You rally Ysmay, granting them +5 to their next attempt to break free.", told
        )
        self.assertEqual(severity_of(self.charm), 3)
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "breakfree")
        self.assertIn("You push back against the effect, weakening its hold.", told)
        self.assertEqual(severity_of(self.charm), 2)

    def test_rallying_someone_with_nothing_to_fight(self) -> None:
        told = self.telnet(self.ysmay, "rally Hobb")
        self.assertIn("They don't seem to be fighting anything.", told)


class ShakingOffAResonanceConflict(JourneyCase):
    """Ysmay carries a self-shakeable condition (Resonance Conflict's category).

    The category sets ``self_shakeable`` and not ``alters_behavior``: she can
    ``breakfree`` and be rallied, and she stays in control throughout.
    """

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.watch(self.hobb)
        self.conflict = ConditionTemplateFactory(
            name="Test Conflict",
            category=ConditionCategoryFactory(
                name="Conflict", alters_behavior=False, self_shakeable=True
            ),
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(name="Focus"),
            break_free_difficulty=10,
        )
        self.held = ConditionInstanceFactory(target=self.ysmay, condition=self.conflict, severity=3)

    def test_she_shakes_it_off_and_never_leaves_control(self) -> None:
        self.assertTrue(self.ysmay.sheet_data.in_control)
        with ROLL_WELL:
            told = self.telnet(self.ysmay, "breakfree")
        self.assertIn("You push back against the effect, weakening its hold.", told)
        self.assertEqual(severity_of(self.held), 2)
        self.assertTrue(self.ysmay.sheet_data.in_control)

    def test_a_friend_rallies_her(self) -> None:
        with ROLL_WELL:
            told = self.telnet(self.hobb, "rally Ysmay")
        self.assertIn(
            "You rally Ysmay, granting them +5 to their next attempt to break free.", told
        )
        self.assertTrue(self.ysmay.sheet_data.in_control)


class StirringUpAResonanceConflict(JourneyCase):
    """An authored social action applies the condition again and advances its hold.

    No new code path: the Intimidate template's pool applies the condition to its
    target through the ordinary APPLY_CONDITION effect.
    """

    def setUp(self) -> None:
        super().setUp()
        content = SocialContent.create_all()
        seed_social_engagement_kudos_category()
        self.room = self.make_room("The Lantern")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.scene = SceneFactory(
            room=self.room,
            participants=[self.account_of(self.ysmay), self.account_of(self.hobb)],
        )
        self.conflict = ConditionTemplateFactory(
            name="Test Conflict",
            category=ConditionCategoryFactory(
                name="Conflict", alters_behavior=False, self_shakeable=True
            ),
            break_free_mode=BreakFreeMode.SELF_INITIATED,
            break_free_check_type=CheckTypeFactory(name="Focus"),
            break_free_difficulty=10,
        )
        pool = content.templates["intimidate"].consequence_pool
        for effect in ConsequenceEffect.objects.filter(
            consequence__pool_entries__pool=pool, condition_template__isnull=False
        ):
            effect.condition_template = self.conflict
            effect.condition_severity = 2
            effect.save()
        self.held = ConditionInstanceFactory(target=self.hobb, condition=self.conflict, severity=1)

    def test_being_stirred_advances_the_hold_and_she_can_still_shake_it(self) -> None:
        self.telnet(self.ysmay, "intimidate Hobb")
        with ROLL_WELL:
            self.telnet(self.hobb, "accept")
        self.assertEqual(severity_of(self.held), 2)
        self.assertTrue(self.hobb.sheet_data.in_control)
        with ROLL_WELL:
            told = self.telnet(self.hobb, "breakfree")
        self.assertIn("You push back against the effect, weakening its hold.", told)
        self.assertEqual(severity_of(self.held), 1)


class TreatingAFeverAtTheClinic(JourneyCase):
    """Hobb offers Ysmay a poultice in a scene; she accepts; the fever recedes."""

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Clinic")
        self.hobb = self.make_player("Hobb", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.scene = SceneFactory(
            room=self.room,
            participants=[self.account_of(self.hobb), self.account_of(self.ysmay)],
        )
        fever = ConditionTemplateFactory(name="Marsh Fever")
        self.poultice = TreatmentTemplateFactory(
            name="Willow Poultice",
            target_condition=fever,
            target_kind=TreatmentTargetKind.PRIMARY,
        )
        self.fever = ConditionInstanceFactory(target=self.ysmay, condition=fever, severity=5)
        self.watch(self.ysmay)

    def test_an_accepted_offer_treats_the_fever(self) -> None:
        listing = self.telnet(self.hobb, "treat Ysmay")
        self.assertIn("Treatable conditions on Ysmay:", listing)
        self.assertIn("1. Willow Poultice on", listing)
        self.assertIn("Marsh Fever", listing)

        offer = self.telnet(self.hobb, "treat Ysmay 1")
        self.assertIn("You offer to treat Ysmay for", offer)
        self.assertIn("with Willow Poultice. Awaiting their response", offer)

        with ROLL_WELL:
            accepted = self.telnet(self.ysmay, "accept")
        self.assertIn("You accept the action against you.", accepted)
        self.assertIn(
            "Hobb applies Willow Poultice to Ysmay. The treatment takes hold.", feed_of(self.scene)
        )
        self.assertEqual(severity_of(self.fever), 2)

    def test_a_number_that_is_not_on_the_list_is_refused(self) -> None:
        self.assertIn("Invalid candidate number.", self.telnet(self.hobb, "treat Ysmay 4"))
        self.assertEqual(severity_of(self.fever), 5)

    def test_nothing_to_treat_says_so(self) -> None:
        self.assertIn(
            "There are no treatable conditions on that character in this scene.",
            self.telnet(self.ysmay, "treat Hobb"),
        )

    def test_the_sheet_and_the_treat_panel_read_the_same_rows(self) -> None:
        sheet = self.api(self.account_of(self.ysmay)).get(
            "/api/conditions/character/", HTTP_X_CHARACTER_ID=str(self.ysmay.pk)
        )
        self.assertEqual(sheet.status_code, 200, sheet.content)
        self.assertEqual([row["name"] for row in sheet.json()], ["Marsh Fever"])

        persona = self.ysmay.sheet_data.primary_persona
        panel = self.api(self.account_of(self.hobb)).get(
            "/api/conditions/treatments/",
            {"target_persona_id": persona.pk},
            HTTP_X_CHARACTER_ID=str(self.hobb.pk),
        )
        self.assertEqual(panel.status_code, 200, panel.content)
        self.assertIn("Willow Poultice", panel.content.decode())


class FirstAidOnAWound(JourneyCase):
    """Hobb tends Ysmay's 20-damage wound through a scene ``treat`` offer (#4600).

    Mundane first aid (a treatment that spends no anima or resonance and needs no
    bond) has its own share of a wound it may heal, 0.50 of the damage: it stops at
    10 of the 20 however much the bandage offers. A magical treatment offered the
    same way costs anima and keeps the never-to-full ceiling, 0.75: it stops at 15.
    """

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Roadside")
        self.hobb = self.make_player("Hobb", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.scene = SceneFactory(
            room=self.room,
            participants=[self.account_of(self.hobb), self.account_of(self.ysmay)],
        )
        self.gash = ConditionTemplateFactory(name="Deep Gash")
        self.wound = ConditionInstanceFactory(target=self.ysmay, condition=self.gash, severity=1)
        WoundDetails.objects.create(condition_instance=self.wound, damage_taken=20)
        CharacterVitals.objects.create(
            character_sheet=self.ysmay.sheet_data, health=30, max_health=100, base_max_health=100
        )
        CharacterAnimaFactory(character=self.hobb.sheet_data, current=20, maximum=30)

    def tending(self, name: str, *, anima_cost: int) -> None:
        """A treatment for the gash that offers far more than any share allows."""
        TreatmentTemplateFactory(
            name=name,
            target_condition=self.gash,
            target_kind=TreatmentTargetKind.PRIMARY,
            anima_cost=anima_cost,
            reduction_on_crit=0,
            reduction_on_success=0,
            reduction_on_partial=0,
            mend_on_crit=50,
            mend_on_success=50,
            mend_on_partial=50,
        )

    def offer_and_accept(self, name: str) -> None:
        self.assertIn("You offer to treat Ysmay for", self.telnet(self.hobb, "treat Ysmay 1"))
        with ROLL_WELL:
            self.telnet(self.ysmay, "accept")
        self.assertIn(
            f"Hobb applies {name} to Ysmay. The treatment takes hold.", feed_of(self.scene)
        )

    def mended(self) -> int:
        details = WoundDetails.objects.filter(condition_instance=self.wound)
        return details.values_list("health_mended_total", flat=True).get()

    def ysmays_health(self) -> int:
        vitals = CharacterVitals.objects.filter(character_sheet=self.ysmay.sheet_data)
        return vitals.values_list("health", flat=True).get()

    def test_first_aid_heals_half_the_wound_and_no_more(self) -> None:
        self.tending("Linen Bandage", anima_cost=0)
        self.offer_and_accept("Linen Bandage")
        self.assertEqual(self.mended(), 10)
        self.assertEqual(self.ysmays_health(), 40)

    def test_a_magical_tending_through_treat_keeps_the_ceiling(self) -> None:
        self.tending("Lifeward Laying On", anima_cost=5)
        self.offer_and_accept("Lifeward Laying On")
        self.assertEqual(self.mended(), 15)
        self.assertEqual(self.ysmays_health(), 45)


class TalkingABerserkerDown(JourneyCase):
    """Hobb has gone berserk in the scene; Ysmay talks him down, and he lets her try."""

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Yard")
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.hobb = self.make_player("Hobb", room=self.room)
        self.scene = SceneFactory(
            room=self.room,
            participants=[self.account_of(self.ysmay), self.account_of(self.hobb)],
        )
        self.berserk = BerserkConditionTemplateFactory()
        RestoreToSenseActionTemplateFactory(check_type=CheckTypeFactory(name="Willpower"))
        apply_condition(self.hobb, self.berserk)
        self.watch(self.hobb)

    def test_a_steady_voice_brings_him_back(self) -> None:
        told = self.telnet(self.ysmay, "restore_sense Hobb")
        self.assertIn("You move to restore_sense Hobb. Awaiting their response", told)
        self.assertTrue(has_condition(self.hobb, self.berserk))
        with ROLL_WELL:
            accepted = self.telnet(self.hobb, "accept")
        self.assertIn("You accept the action against you.", accepted)
        self.assertFalse(has_condition(self.hobb, self.berserk))

    def test_a_faltering_voice_leaves_him_raging(self) -> None:
        self.telnet(self.ysmay, "restore_sense Hobb")
        with ROLL_BADLY:
            accepted = self.telnet(self.hobb, "accept")
        self.assertIn("You accept the action against you.", accepted)
        self.assertTrue(has_condition(self.hobb, self.berserk))


class AGMAppliesAConditionAtTheTable(JourneyCase):
    """Ravenna runs the scene; from the GM panel she marks Ysmay feverish, then clears it."""

    def setUp(self) -> None:
        super().setUp()
        self.room = self.make_room("The Long Table")
        self.ravenna = self.make_player("Ravenna", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        GMProfileFactory(account=self.account_of(self.ravenna), level=GMLevel.JUNIOR)
        self.scene = SceneFactory(room=self.room)
        SceneParticipationFactory(
            scene=self.scene, account=self.account_of(self.ravenna), is_gm=True
        )
        SceneParticipationFactory(scene=self.scene, account=self.account_of(self.ysmay))
        ConditionTemplateFactory(name="Marsh Fever")
        self.watch(self.ysmay)

    def test_the_player_hears_it_and_the_panel_lists_it(self) -> None:
        applied = self.web(
            self.ravenna,
            "gm_apply_condition",
            target=self.ysmay,
            condition_ref="Marsh Fever",
            severity=2,
            note="A chill from the marsh road.",
        )
        self.assertTrue(applied.detail.success, applied.detail.message)
        self.assertIn("Ysmay is now Marsh Fever.", applied.detail.message)
        self.assertIn("Ysmay is now Marsh Fever. A chill from the marsh road.", feed_of(self.scene))

        listed = self.web(self.ravenna, "gm_list_conditions", target=self.ysmay)
        self.assertTrue(listed.detail.success, listed.detail.message)
        self.assertIn("Marsh Fever (severity 2)", listed.detail.message)

        removed = self.web(
            self.ravenna,
            "gm_remove_condition",
            target=self.ysmay,
            condition="Marsh Fever",
            reason="the fever broke overnight",
        )
        self.assertTrue(removed.detail.success, removed.detail.message)
        self.assertIn(
            "Marsh Fever removed from Ysmay (the fever broke overnight).", removed.detail.message
        )
        self.assertFalse(
            ConditionInstance.objects.filter(target=self.ysmay, resolved_at__isnull=True).exists()
        )

    def test_a_player_who_is_not_the_gm_is_refused(self) -> None:
        refused = self.web(
            self.ysmay,
            "gm_apply_condition",
            target=self.ravenna,
            condition_ref="Marsh Fever",
            severity=1,
        )
        self.assertFalse(refused.detail.success)
        self.assertFalse(ConditionInstance.objects.filter(target=self.ravenna).exists())


@tag("postgres")
class WakingFromASleepSomeoneOfferedToTreat(JourneyCase):
    """A condition that a treat offer points at can still go away (#4475).

    The request kept the condition instance with PROTECT, so removing the condition
    (here Ysmay waking, which removes Sleeping) raised ProtectedError. The request now
    keeps what it treated by name and template; an offer still open when the condition
    goes is closed as expired.
    """

    def setUp(self) -> None:
        super().setUp()
        fresh_check_system()
        self.room = self.make_room("The Clinic")
        self.hobb = self.make_player("Hobb", room=self.room)
        self.ysmay = self.make_player("Ysmay", room=self.room)
        self.scene = SceneFactory(
            room=self.room,
            participants=[self.account_of(self.hobb), self.account_of(self.ysmay)],
        )
        sleeping = ConditionTemplateFactory(name=SLEEPING_CONDITION_NAME)
        TreatmentTemplateFactory(
            name="Smelling Salts",
            target_condition=sleeping,
            target_kind=TreatmentTargetKind.PRIMARY,
        )
        self.sleep = ConditionInstanceFactory(target=self.ysmay, condition=sleeping, severity=5)
        self.watch(self.ysmay)

    def _offer(self) -> SceneActionRequest:
        self.telnet(self.hobb, "treat Ysmay 1")
        return SceneActionRequest.objects.get(
            initiator_persona__character_sheet=self.hobb.sheet_data
        )

    def test_waking_closes_an_offer_still_open_and_keeps_what_it_treated(self) -> None:
        offer = self._offer()
        self.assertEqual(offer.status, ActionRequestStatus.PENDING)

        told = self.telnet(self.ysmay, "wake")

        self.assertIn("You wake from your dream.", told)
        self.assertFalse(ConditionInstance.objects.filter(pk=self.sleep.pk).exists())
        offer = SceneActionRequest.objects.get(pk=offer.pk)
        self.assertEqual(offer.status, ActionRequestStatus.EXPIRED)
        self.assertIsNone(offer.target_condition_instance_id)
        self.assertEqual(offer.target_condition_name, SLEEPING_CONDITION_NAME)
        self.assertEqual(offer.target_condition_template.name, SLEEPING_CONDITION_NAME)
        self.assertEqual(offer.treatment.name, "Smelling Salts")

    def test_waking_after_a_treatment_took_hold_keeps_the_resolved_record(self) -> None:
        offer = self._offer()
        with ROLL_WELL:
            self.telnet(self.ysmay, "accept")
        self.assertEqual(
            SceneActionRequest.objects.get(pk=offer.pk).status, ActionRequestStatus.RESOLVED
        )

        self.telnet(self.ysmay, "wake")

        offer = SceneActionRequest.objects.get(pk=offer.pk)
        self.assertEqual(offer.status, ActionRequestStatus.RESOLVED)
        self.assertIsNone(offer.target_condition_instance_id)
        self.assertEqual(offer.target_condition_name, SLEEPING_CONDITION_NAME)

    def test_an_offer_closed_by_the_wake_cannot_be_accepted_later(self) -> None:
        offer = self._offer()
        self.telnet(self.ysmay, "wake")

        late = self.telnet(self.ysmay, f"accept {offer.pk}")

        self.assertNotIn("Traceback", late)
        self.assertEqual(
            SceneActionRequest.objects.get(pk=offer.pk).status, ActionRequestStatus.EXPIRED
        )
