"""Journeys for the Anima ritual with a partner (#5181).

Mara asks Tobin to take part in her Anima ritual in a live scene. Tobin is told what is asked
and what it will do to his fatigue before he agrees; Hobb stands there and sees none of it. Mara's
ritual rolls its own check (pinned to a Success), restores her anima and earns the resonance the
ritual names; the affinity of that resonance decides whether Tobin's fatigue is taken (Abyssal),
eased (Celestial) or left alone (Primal).

Numbers are worked out by hand, not read from the code. The Success award is 6 resonance and the
anima budget for a Success is 6, so Mara's anima goes from 2 to 8 and she earns 6 in the ritual's
resonance (the earn rates are left at 100). The affinity sets 10 fatigue taken for Abyssal and 5
eased for Celestial; Tobin starts at 0 and 7.
"""

from __future__ import annotations

from django.test import override_settings
from rest_framework import status

from actions.constants import ActionCategory
from evennia_extensions.factories import RoomProfileFactory
from integration_tests.harness import JourneyCase
from world.checks.factories import CheckTypeFactory
from world.checks.services import difficulty_points
from world.checks.test_helpers import force_check_outcome
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import GainSource, RitualExecutionKind
from world.magic.factories import (
    AnimaRitualResonanceAwardFactory,
    CharacterAnimaFactory,
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
from world.scenes.action_constants import ActionRequestStatus
from world.scenes.action_models import SceneActionRequest
from world.scenes.factories import SceneFactory
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
        # The ritual's resonance earns only for a character who already holds it.
        CharacterResonanceFactory(character_sheet=self.mara.sheet_data, resonance=self.resonance)
        self.check_type = CheckTypeFactory()
        self.ritual = RitualFactory(
            execution_kind=RitualExecutionKind.SCENE_ACTION,
            service_function_path="",
            flow=None,
            author_account=self.account_of(self.mara),
            # Mara has no magical profile here; the solo ritual is closed to such a character
            # unless the rite is a hedge rite (#3001).
            hedge_accessible=True,
        )
        RitualCheckConfigFactory(
            ritual=self.ritual,
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

    def balance(self) -> int:
        row = CharacterResonance.objects.filter(
            character_sheet=self.mara.sheet_data, resonance=self.resonance
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
        self.assertTold(self.mara, "Your ritual feeds on Tobin. Your Ruin grows by 6.")
        self.assertTold(self.tobin, "Mara's ritual leaves you wearier.")
        self.assertEqual(social_fatigue(self.tobin), 10)
        self.assertEqual(self.balance(), 6)
        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 8)
        performance = AnimaRitualPerformance.objects.get()
        self.assertEqual(performance.target_character, self.tobin.sheet_data)
        grant = ResonanceGrant.objects.get(source=GainSource.ANIMA_RITUAL)
        self.assertEqual((grant.character_sheet, grant.amount), (self.mara.sheet_data, 6))
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

    def test_the_solo_telnet_ritual_still_restores_anima_and_earns_no_resonance(self) -> None:
        # The solo ritual needs the performer to be a scene participant, as it always did.
        from world.scenes.factories import SceneParticipationFactory

        SceneParticipationFactory(scene=self.scene, account=self.account_of(self.mara))
        with force_check_outcome(self.success):
            self.telnet(self.mara, "ritual anima")

        self.assertEqual(CharacterAnima.objects.get(character=self.mara.sheet_data).current, 8)
        self.assertEqual(self.balance(), 0)
        self.assertIsNone(AnimaRitualPerformance.objects.get().target_character)
        self.assertEqual(social_fatigue(self.tobin), 0)


class ACelestialRitualEasesItsPartner(_RitualWithAPartner):
    AFFINITY = "Celestial"
    SETTING = -5

    def test_tobin_reads_that_it_will_ease_his_fatigue_and_it_does(self) -> None:
        set_social_fatigue(self.tobin, 7)

        self.ask()
        self.assertTold(self.tobin, "It will ease your fatigue.")
        self.agree()

        self.assertTold(self.mara, "Your ritual lifts Tobin. Your Ruin grows by 6.")
        self.assertTold(self.tobin, "Mara's ritual leaves you lighter.")
        self.assertEqual(social_fatigue(self.tobin), 2)


class APrimalRitualDoesNothingToItsPartner(_RitualWithAPartner):
    AFFINITY = "Primal"
    SETTING = 0

    def test_tobin_reads_no_effect_sentence_and_his_fatigue_stays(self) -> None:
        set_social_fatigue(self.tobin, 7)

        self.ask()
        self.assertNotTold(self.tobin, "fatigue")
        self.agree()

        self.assertTold(self.mara, "Your ritual with Tobin is done. Your Ruin grows by 6.")
        self.assertNotTold(self.tobin, "wearier")
        self.assertNotTold(self.tobin, "lighter")
        self.assertEqual(social_fatigue(self.tobin), 7)
        self.assertEqual(self.balance(), 6)


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
        self.assertEqual(self.balance(), 6)

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
