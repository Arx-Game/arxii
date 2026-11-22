"""Journeys for the Anima ritual with a partner (#5181).

Mara asks Tobin to take part in her Anima ritual in a live scene. Tobin is told what is asked
and what it will do to his fatigue before he agrees; Hobb stands there and sees none of it. Mara's
ritual rolls its own check (pinned to a Success), restores her anima and grows her two picks: a
Primal one at once, and an outward one (Celestial or Abyssal) that waits on Tobin's answer when he
is a player and is granted at once when he is a story NPC a GM runs. The affinity of the outward
pick decides whether Tobin's fatigue is taken (Abyssal), eased (Celestial) or left alone (a
Celestial affinity set to 0).

Numbers are worked out by hand, not read from the code. The Success award is 6 resonance, split by
Mara's aura (half Primal, half the outward affinity) into 3 and 3, and the anima budget for a
Success is 6, so Mara's anima goes from 2 to 8 and her Primal pick grows by 3 (the earn rates are
left at 100). The affinity sets 10 fatigue taken for Abyssal and 5 eased for Celestial; Tobin
starts at 0 and 7.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import override_settings
from rest_framework import status

from actions.constants import ActionCategory
from evennia_extensions.factories import AccountFactory, RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.services import difficulty_points
from world.checks.test_helpers import force_check_outcome
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import AnimaRitualEndorsement, GainSource, RitualExecutionKind
from world.magic.factories import (
    AnimaRitualResonanceAwardFactory,
    CharacterAnimaFactory,
    CharacterAuraFactory,
    CharacterResonanceFactory,
    ResonanceFactory,
    RitualCheckConfigFactory,
    RitualFactory,
    SoulfrayConfigFactory,
    ensure_conversion_pairs,
)
from world.magic.models import (
    Affinity,
    AffinityInteraction,
    AnimaRitualPerformance,
    CharacterAnima,
    CharacterResonance,
    ResonanceGrant,
)
from world.magic.models.soulfray import AnimaRitualBudgetAward
from world.roster.factories import RosterFactory
from world.roster.models.choices import RosterType
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.scenes.interaction_services import invalidate_active_scene_cache
from world.traits.factories import ensure_level_ladder
from world.traits.services import ensure_canonical_check_outcome

ACTION_REQUESTS = "/api/action-requests/"


def social_fatigue(character) -> int:
    return get_or_create_fatigue_pool(character.sheet_data).get_current(ActionCategory.SOCIAL)


def set_social_fatigue(character, value: int) -> None:
    pool = get_or_create_fatigue_pool(character.sheet_data)
    pool.set_current(ActionCategory.SOCIAL, value)
    pool.save()


@override_settings(SEED_SAMPLE_CONTENT=True)
class _RitualWithAPartner(JourneyCase):
    """Mara performs her anima ritual with Tobin, in the Lantern's live scene."""

    # What the affinity of Mara's resonance does to the partner's fatigue (set per class).
    AFFINITY = "Abyssal"
    SETTING = 10

    def setUp(self) -> None:
        super().setUp()
        ensure_level_ladder()
        self.seed_social_engagement()
        celestial, primal, abyssal = ensure_conversion_pairs()
        self.affinity = {"Celestial": celestial, "Primal": primal, "Abyssal": abyssal}[
            self.AFFINITY
        ]
        self.affinity.ritual_partner_fatigue = self.SETTING
        self.affinity.save()
        Affinity.objects.clear_cache()
        AffinityInteraction.objects.clear_cache()
        self.resonance = ResonanceFactory(name="Ruin", affinity=self.affinity)
        self.primal_resonance = ResonanceFactory(name="Hollow", affinity=primal)

        self.lantern = self.make_room("The Lantern")
        self.scene = SceneFactory(
            location=RoomProfileFactory(objectdb=self.lantern), is_active=True
        )
        invalidate_active_scene_cache(self.lantern)
        self.mara = self.make_player("Mara", room=self.lantern)
        self.tobin = self.make_player("Tobin", room=self.lantern)
        self.hobb = self.make_player("Hobb", room=self.lantern)
        for who in (self.mara, self.tobin, self.hobb):
            self.watch(who)
            self.connect_telnet(who)

        self.success = ensure_canonical_check_outcome("Success")
        AnimaRitualResonanceAwardFactory(outcome_tier=self.success, amount=6)
        AnimaRitualBudgetAward.objects.create(outcome_tier=self.success, budget=6)
        SoulfrayConfigFactory(ritual_severity_cost_per_point=1)
        CharacterAnimaFactory(character=self.mara.sheet_data, current=2, maximum=10)
        # The ritual feeds only the resonances she already holds, half her aura in each affinity.
        for held in (self.resonance, self.primal_resonance):
            CharacterResonanceFactory(character_sheet=self.mara.sheet_data, resonance=held)
        CharacterAuraFactory(
            character=self.mara.sheet_data,
            celestial=Decimal(50 if self.AFFINITY == "Celestial" else 0),
            primal=Decimal(50),
            abyssal=Decimal(50 if self.AFFINITY == "Abyssal" else 0),
        )
        self.check_type = CheckTypeFactory()
        self.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=self.account_of(self.mara),
            known_by=self.mara.sheet_data,
            # Mara has no magical profile here; the solo ritual is closed to such a character
            # unless the rite is a hedge rite (#3001).
            hedge_accessible=True,
        )
        RitualCheckConfigFactory(
            ritual=self.ritual,
            primal_resonance=self.primal_resonance,
            outward_resonance=self.resonance,
            check_type=self.check_type,
            target_difficulty_level=2,
        )

    def telnet(self, character, line: str) -> str:
        """A typed line, with the after-commit sends it causes run: the private result lines
        are stored narrative messages sent once the transaction commits."""
        with self.captureOnCommitCallbacks(execute=True):
            return super().telnet(character, line)

    def ask(self) -> str:
        return self.telnet(self.mara, "ritual anima Tobin")

    def agree(self):
        with force_check_outcome(self.success) as capture:
            told = self.telnet(self.tobin, "accept")
        self.capture = capture
        return told

    def balance(self, resonance=None) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=self.mara.sheet_data, resonance=resonance or self.primal_resonance
        ).first()
        return row.balance if row is not None else 0


class AnAbyssalRitualFeedsOnItsPartner(_RitualWithAPartner):
    def test_tobin_is_told_what_it_will_do_then_agrees_and_both_are_told_the_result(self) -> None:
        told = self.ask()

        self.assertIn("You ask Tobin to take part in your ritual.", told)
        self.assertTold(self.tobin, "Mara asks you to take part in their ritual.")
        self.assertTold(self.tobin, "It will add to your fatigue.")
        self.assertTold(self.tobin, "accept")
        # Nothing has happened yet.
        self.assertEqual(social_fatigue(self.tobin), 0)
        self.assertFalse(AnimaRitualPerformance.objects.exists())

        self.agree()

        # The ritual rolled its own check type at its own difficulty.
        self.assertEqual(self.capture.check_type, self.check_type)
        self.assertEqual(self.capture.target_difficulty, difficulty_points(2))
        self.assertTold(
            self.mara,
            "Your ritual feeds on Tobin. You recover 6 anima. Your Hollow grows by 3.",
        )
        self.assertTold(self.tobin, "Mara's ritual leaves you wearier.")
        # Tobin is asked whether the ritual reached him; Mara's Ruin waits on his answer.
        self.assertTold(self.tobin, "Mara's ritual reached for your ruin. Did it take hold of you?")
        self.assertTold(self.tobin, "ritual endorse Mara")
        self.assertEqual(social_fatigue(self.tobin), 10)
        self.assertEqual(self.balance(), 3)
        self.assertEqual(self.balance(self.resonance), 0)
        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 8)
        performance = AnimaRitualPerformance.objects.get()
        self.assertEqual(performance.target_character, self.tobin.sheet_data)
        self.assertEqual(performance.endorsement, AnimaRitualEndorsement.PENDING)
        self.assertEqual(performance.outward_amount_pending, 3)
        grant = ResonanceGrant.objects.get(source=GainSource.ANIMA_RITUAL)
        self.assertEqual(
            (grant.character_sheet, grant.resonance, grant.amount),
            (self.mara.sheet_data, self.primal_resonance, 3),
        )
        request = SceneActionRequest.objects.get(action_key="anima_ritual")
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        # Hobb read none of it.
        for private in ("ritual", "fatigue", "wearier", "grows by"):
            self.assertNotTold(self.hobb, private)

    def test_denying_does_nothing_and_the_ritual_can_be_asked_again(self) -> None:
        self.ask()

        self.telnet(self.tobin, "deny")

        self.assertEqual(social_fatigue(self.tobin), 0)
        self.assertEqual(self.balance(), 0)
        self.assertFalse(AnimaRitualPerformance.objects.exists())
        self.assertIn("You ask Tobin to take part in your ritual.", self.ask())

    def test_a_second_ritual_in_the_scene_is_refused_before_a_request_exists(self) -> None:
        self.ask()
        self.agree()

        told = self.ask()

        self.assertIn("You have already performed your anima ritual in this scene.", told)
        self.assertEqual(SceneActionRequest.objects.filter(action_key="anima_ritual").count(), 1)

    def test_a_request_waiting_blocks_a_second_one(self) -> None:
        self.ask()

        told = self.ask()

        self.assertIn("You already have a ritual waiting for an answer in this scene.", told)

    def test_you_cannot_take_yourself_as_the_partner(self) -> None:
        told = self.telnet(self.mara, "ritual anima Mara")

        self.assertIn("Name someone else to take part in your ritual.", told)

    def test_the_ritual_with_nobody_named_restores_no_anima_and_earns_no_resonance(self) -> None:
        with force_check_outcome(self.success):
            told = self.telnet(self.mara, "ritual anima")

        self.assertIn("Name someone else to take part in your ritual.", told)
        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 2)
        self.assertEqual(self.balance(), 0)
        self.assertFalse(AnimaRitualPerformance.objects.exists())
        self.assertEqual(social_fatigue(self.tobin), 0)


class AnNpcPartner(_RitualWithAPartner):
    """Hobb is a story NPC on the NPC shelf; nobody plays him unless the table has a GM."""

    def setUp(self) -> None:
        super().setUp()
        self.hobb.sheet_data.roster_entry.move_to_roster(RosterFactory(roster_type=RosterType.NPC))

    def test_with_no_gm_running_him_he_is_refused_and_nothing_happens(self) -> None:
        told = self.telnet(self.mara, "ritual anima Hobb")

        self.assertIn("Nobody is playing that character.", told)
        self.assertFalse(SceneActionRequest.objects.filter(action_key="anima_ritual").exists())
        self.assertFalse(AnimaRitualPerformance.objects.exists())
        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 2)

    def test_with_a_gm_in_the_scene_he_takes_part_at_once(self) -> None:
        SceneParticipationFactory(scene=self.scene, account=AccountFactory(), is_gm=True)

        with force_check_outcome(self.success):
            self.telnet(self.mara, "ritual anima Hobb")

        request = SceneActionRequest.objects.get(action_key="anima_ritual")
        self.assertEqual(request.status, ActionRequestStatus.RESOLVED)
        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 8)
        performance = AnimaRitualPerformance.objects.get()
        self.assertEqual(performance.target_character, self.hobb.sheet_data)
        # A story NPC is not asked: both parts are granted at once, 3 to each pick.
        self.assertEqual(performance.endorsement, AnimaRitualEndorsement.NOT_ASKED)
        self.assertEqual(self.balance(), 3)
        self.assertEqual(self.balance(self.resonance), 3)
        self.assertTold(
            self.mara,
            "Your ritual feeds on Hobb. You recover 6 anima. Your Hollow grows by 3."
            " Your Ruin grows by 3.",
        )


class ACelestialRitualEasesItsPartner(_RitualWithAPartner):
    AFFINITY = "Celestial"
    SETTING = -5

    def test_tobin_reads_that_it_will_ease_his_fatigue_and_it_does(self) -> None:
        set_social_fatigue(self.tobin, 7)

        self.ask()
        self.assertTold(self.tobin, "It will ease your fatigue.")
        self.agree()

        self.assertTold(
            self.mara, "Your ritual lifts Tobin. You recover 6 anima. Your Hollow grows by 3."
        )
        self.assertTold(self.tobin, "Mara's ritual leaves you lighter.")
        self.assertEqual(social_fatigue(self.tobin), 2)


class ARitualSetToDoNothingToItsPartner(_RitualWithAPartner):
    AFFINITY = "Celestial"
    SETTING = 0

    def test_tobin_reads_no_effect_sentence_and_his_fatigue_stays(self) -> None:
        set_social_fatigue(self.tobin, 7)

        self.ask()
        self.assertNotTold(self.tobin, "fatigue")
        self.agree()

        self.assertTold(
            self.mara,
            "Your ritual with Tobin is done. You recover 6 anima. Your Hollow grows by 3.",
        )
        self.assertNotTold(self.tobin, "wearier")
        self.assertNotTold(self.tobin, "lighter")
        self.assertEqual(social_fatigue(self.tobin), 7)
        self.assertEqual(self.balance(), 3)


class AskingThroughTheWeb(_RitualWithAPartner):
    def _persona(self, character):
        return character.sheet_data.primary_persona

    def _post(self, **extra):
        return self.api(self.account_of(self.mara)).post(
            ACTION_REQUESTS,
            {
                "scene": self.scene.pk,
                "initiator_persona": self._persona(self.mara).pk,
                "target_persona": self._persona(self.tobin).pk,
                "action_key": "anima_ritual",
                **extra,
            },
            format="json",
        )

    def test_the_scene_action_create_opens_the_request_and_the_prompt_carries_the_sentence(
        self,
    ) -> None:
        created = self._post()

        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        self.assertEqual(created.json()["ritual_partner_effect"], "It will add to your fatigue.")
        pending = self.api(self.account_of(self.tobin)).get(ACTION_REQUESTS)
        rows = [r for r in pending.json()["results"] if r["action_key"] == "anima_ritual"]
        self.assertEqual(rows[0]["ritual_partner_effect"], "It will add to your fatigue.")

        with force_check_outcome(self.success):
            responded = self.api(self.account_of(self.tobin)).post(
                f"{ACTION_REQUESTS}{created.json()['id']}/respond/",
                {"decision": "accept"},
                format="json",
            )

        self.assertEqual(responded.status_code, status.HTTP_200_OK, responded.content)
        self.assertEqual(social_fatigue(self.tobin), 10)
        self.assertEqual(self.balance(), 3)

    def test_a_ritual_already_performed_in_the_scene_is_refused_with_a_400(self) -> None:
        self.ask()
        self.agree()

        refused = self._post()

        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.content)
        self.assertIn("already performed", str(refused.json()))

    def test_the_client_cannot_name_a_ritual_it_does_not_own(self) -> None:
        stranger = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION, service_function_path="", flow=None
        )
        RitualCheckConfigFactory(ritual=stranger, check_type=CheckTypeFactory())

        created = self._post(ritual_id=stranger.pk)

        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        request = SceneActionRequest.objects.get(pk=created.json()["id"])
        self.assertEqual(request.snapshot_ritual, self.ritual)


ENDORSEMENTS = "/api/magic/anima-ritual-endorsements/"
NOT_WAITING = "That ritual is not waiting for your answer."


class _AnAskedPartner(_RitualWithAPartner):
    """Mara's ritual has run on Tobin and her Ruin (the outward part, 3) waits on his answer."""

    def setUp(self) -> None:
        super().setUp()
        self.ask()
        self.agree()
        self.assertEqual(self.balance(self.resonance), 0)

    def ruin_grants(self) -> int:
        return ResonanceGrant.objects.filter(
            source=GainSource.ANIMA_RITUAL, resonance=self.resonance
        ).count()


class TobinEndorses(_AnAskedPartner):
    def test_endorsing_grows_marras_ruin_once_and_tells_her_so(self) -> None:
        told = self.telnet(self.tobin, "ritual endorse Mara")

        self.assertIn("You endorse Mara's ritual for Ruin.", told)
        self.assertTold(self.mara, "Tobin felt it. Your Ruin grows by 3.")
        self.assertEqual(self.balance(self.resonance), 3)
        self.assertEqual(self.ruin_grants(), 1)
        performance = AnimaRitualPerformance.objects.get()
        self.assertEqual(performance.endorsement, AnimaRitualEndorsement.ENDORSED)
        self.assertEqual(performance.outward_amount_pending, 0)

    def test_answering_again_or_by_someone_else_grants_nothing_more(self) -> None:
        self.telnet(self.tobin, "ritual endorse Mara")

        again = self.telnet(self.tobin, "ritual endorse Mara")
        stranger = self.telnet(self.hobb, "ritual endorse Mara")

        self.assertIn("No ritual from Mara is waiting for your answer.", again)
        self.assertIn("No ritual from Mara is waiting for your answer.", stranger)
        self.assertEqual(self.balance(self.resonance), 3)
        self.assertEqual(self.ruin_grants(), 1)

    def test_naming_nobody_who_performed_one_is_told_none_is_waiting(self) -> None:
        told = self.telnet(self.tobin, "ritual endorse Hobb")

        self.assertIn("No ritual from Hobb is waiting for your answer.", told)
        self.assertEqual(self.balance(self.resonance), 0)


class TobinWithholds(_AnAskedPartner):
    def test_withholding_grants_nothing_and_closes_the_question(self) -> None:
        told = self.telnet(self.tobin, "ritual withhold Mara")

        self.assertIn("You do not endorse Mara's ritual for Ruin.", told)
        self.assertTold(self.mara, "Tobin did not feel it.")
        self.assertEqual(self.balance(self.resonance), 0)
        self.assertEqual(self.ruin_grants(), 0)
        self.assertEqual(
            AnimaRitualPerformance.objects.get().endorsement, AnimaRitualEndorsement.WITHHELD
        )

        later = self.telnet(self.tobin, "ritual endorse Mara")

        self.assertIn("No ritual from Mara is waiting for your answer.", later)
        self.assertEqual(self.balance(self.resonance), 0)


class TheSceneFinishesUnanswered(_AnAskedPartner):
    def test_the_question_lapses_and_a_late_endorse_grants_nothing(self) -> None:
        self.scene.finish_scene()

        self.assertEqual(
            AnimaRitualPerformance.objects.get().endorsement, AnimaRitualEndorsement.LAPSED
        )
        late = self.telnet(self.tobin, "ritual endorse Mara")

        self.assertIn("No ritual from Mara is waiting for your answer.", late)
        self.assertEqual(self.balance(self.resonance), 0)
        self.assertEqual(self.ruin_grants(), 0)


class AnsweringOnTheWeb(_AnAskedPartner):
    def _rows(self, character, **query) -> list[dict]:
        listed = self.api(self.account_of(character)).get(
            ENDORSEMENTS, {"scene": self.scene.pk, **query}
        )
        self.assertEqual(listed.status_code, status.HTTP_200_OK, listed.content)
        return listed.json()["results"]

    def _answer(self, character, performance_id: int, *, endorse: bool):
        return self.api(self.account_of(character)).post(
            f"{ENDORSEMENTS}{performance_id}/answer/", {"endorse": endorse}, format="json"
        )

    def test_the_list_holds_only_the_partners_own_pending_ritual(self) -> None:
        performance = AnimaRitualPerformance.objects.get()

        rows = self._rows(self.tobin)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], performance.pk)
        self.assertEqual(rows[0]["performer_name"], "Mara")
        self.assertEqual(
            rows[0]["prompt"], "Mara's ritual reached for your ruin. Did it take hold of you?"
        )
        self.assertEqual(rows[0]["partner_line"], "It will add to your fatigue.")
        self.assertEqual(self._rows(self.mara), [])
        self.assertEqual(self._rows(self.hobb), [])
        self.assertEqual(self._rows(self.tobin, scene=self.scene.pk + 1), [])

    def test_only_the_partner_may_answer_and_only_once(self) -> None:
        performance_id = AnimaRitualPerformance.objects.get().pk

        stranger = self._answer(self.hobb, performance_id, endorse=True)
        performer = self._answer(self.mara, performance_id, endorse=True)

        self.assertEqual(stranger.status_code, status.HTTP_403_FORBIDDEN, stranger.content)
        self.assertEqual(performer.status_code, status.HTTP_403_FORBIDDEN, performer.content)
        self.assertEqual(self.balance(self.resonance), 0)

        answered = self._answer(self.tobin, performance_id, endorse=True)
        again = self._answer(self.tobin, performance_id, endorse=True)

        self.assertEqual(answered.status_code, status.HTTP_200_OK, answered.content)
        self.assertEqual(answered.json()["detail"], "You endorse Mara's ritual for Ruin.")
        self.assertEqual(again.status_code, status.HTTP_400_BAD_REQUEST, again.content)
        self.assertEqual(again.json()["detail"], NOT_WAITING)
        self.assertEqual(self.balance(self.resonance), 3)
        self.assertEqual(self.ruin_grants(), 1)
        self.assertEqual(self._rows(self.tobin), [])

    def test_withholding_on_the_web_grants_nothing(self) -> None:
        performance_id = AnimaRitualPerformance.objects.get().pk

        answered = self._answer(self.tobin, performance_id, endorse=False)

        self.assertEqual(answered.status_code, status.HTTP_200_OK, answered.content)
        self.assertEqual(self.balance(self.resonance), 0)
        self.assertEqual(
            AnimaRitualPerformance.objects.get().endorsement, AnimaRitualEndorsement.WITHHELD
        )
