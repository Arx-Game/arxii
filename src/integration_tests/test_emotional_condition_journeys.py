"""Journeys for emotional conditions feeding intensity (#4739, slice 3 of #4727).

Mira and Tomas fight a Bandit Captain on "The Road" in an escalating encounter. Staff have
authored Anger with one stage that adds 2 intensity a round. Mira is angry (a success left
her so; the condition is granted directly here, since how she became angry is not this
journey); Tomas is not.

- Each round opening (the staff GM's ``encounter begin``) tells Mira "Anger · Intensity +2"
  and raises her combat intensity by 2, one record a round; Tomas is told nothing and gains
  nothing.
- Staff rename Anger in the admin; the next round feeds her the same 2, now under the new
  name. Which conditions feed is read from the stage, never the name.
- The round payload gives Mira the beat's kind, amount and cause; Tomas gets no beat.
- The surge tuning admin page refuses a Failure band carrying Anger and accepts it on a
  Success band.
"""

from __future__ import annotations

from django.test import override_settings
from django.urls import reverse

from integration_tests.test_refused_admin_saves_journeys import RefusedAdminSaveCase
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeTuningFactory,
)
from world.combat.models import DramaticSurgeRecord, SurgeDegreeBand
from world.conditions.factories import (
    ConditionInstanceFactory,
    ConditionStageFactory,
    ConditionTemplateFactory,
)
from world.mechanics.engagement import CharacterEngagement
from world.scenes.constants import RoundStatus
from world.traits.factories import CheckOutcomeFactory
from world.vitals.models import CharacterVitals

ANGER_PER_ROUND = 2


@override_settings(SEED_SAMPLE_CONTENT=True)  # the curve factory gates on #2698
class AngerFeedsHerIntensity(RefusedAdminSaveCase):
    # The curve's own pressure ticks start long after these rounds, so the only intensity
    # Mira gains is what Anger feeds her.
    CURVE_START_ROUND = 50

    def setUp(self) -> None:
        super().setUp()
        self.road = self.make_room("The Road")
        self.mira = self.make_player("Mira", room=self.road)
        self.tomas = self.make_player("Tomas", room=self.road)
        for player in (self.mira, self.tomas):
            CharacterVitals.objects.create(
                character_sheet=player.sheet_data, health=100, max_health=100, base_max_health=100
            )
        self.encounter = CombatEncounterFactory(
            status=RoundStatus.BETWEEN_ROUNDS,
            round_number=0,
            room=self.road,
            escalation_curve=EscalationCurveFactory(
                start_round=self.CURVE_START_ROUND, surge_narration="{character} surges."
            ),
        )
        for player in (self.mira, self.tomas):
            CombatParticipantFactory(
                encounter=self.encounter,
                character_sheet=player.sheet_data,
                status=ParticipantStatus.ACTIVE,
            )
        CombatOpponentFactory(encounter=self.encounter, name="Bandit Captain")
        self.anger = ConditionTemplateFactory(
            name="Anger", has_progression=True, default_duration_value=20
        )
        stage = ConditionStageFactory(
            condition=self.anger, stage_order=1, intensity_per_round=ANGER_PER_ROUND
        )
        ConditionInstanceFactory(
            target=self.mira, condition=self.anger, current_stage=stage, rounds_remaining=20
        )
        # The GM runs the fight from the road; staff may run any encounter.
        self.gm = self.make_player("Warden", room=self.road)
        gm_account = self.account_of(self.gm)
        gm_account.is_staff = True
        gm_account.save(update_fields=["is_staff"])
        self.watch(self.mira, self.tomas)

    def next_round(self) -> None:
        """The staff GM types ``encounter begin`` once the last round has resolved."""
        self.encounter.status = RoundStatus.BETWEEN_ROUNDS
        self.encounter.save(update_fields=["status"])
        # The private line is sent once the round-opening commits; a test's never does.
        with self.captureOnCommitCallbacks(execute=True):
            told = self.telnet(self.gm, "encounter begin")
        self.assertIn("Round begins.", told)
        self.encounter.refresh_from_db()

    def intensity(self, character) -> int:
        engagement = CharacterEngagement.objects.filter(character=character.sheet_data).first()
        return engagement.intensity_modifier if engagement is not None else 0

    def fed_records(self):
        return DramaticSurgeRecord.objects.filter(trigger_kind=SurgeTriggerKind.CONDITION_FED)

    def beats_seen_by(self, character) -> list[dict]:
        response = self.api(self.account_of(character)).get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["surge_beats"]

    def test_each_round_opening_feeds_her_two_and_tells_her(self) -> None:
        self.next_round()

        self.assertTold(self.mira, f"Anger · Intensity +{ANGER_PER_ROUND}")
        self.assertEqual(self.intensity(self.mira), ANGER_PER_ROUND)
        self.assertNotTold(self.tomas, "Intensity +")
        self.assertEqual(self.intensity(self.tomas), 0)

        self.next_round()

        self.assertEqual(self.intensity(self.mira), 2 * ANGER_PER_ROUND)
        self.assertEqual(
            sorted(self.fed_records().values_list("round_number", "amount")),
            [(1, ANGER_PER_ROUND), (2, ANGER_PER_ROUND)],
        )

    def test_renaming_anger_in_the_admin_changes_nothing(self) -> None:
        url = reverse("admin:arxii_conditiontemplate_change", args=[self.anger.pk])
        data = self.change_post(url)
        data["name"] = "Seething"

        saved = self.client.post(url, data)

        self.assertEqual(saved.status_code, 302, saved.context and saved.context.get("errors"))
        self.next_round()
        self.assertTold(self.mira, f"Seething · Intensity +{ANGER_PER_ROUND}")
        self.assertEqual(self.intensity(self.mira), ANGER_PER_ROUND)

    def test_the_round_payload_shows_the_beat_to_her_alone(self) -> None:
        self.next_round()

        (own,) = self.beats_seen_by(self.mira)
        self.assertEqual(own["trigger_kind"], SurgeTriggerKind.CONDITION_FED)
        self.assertEqual(own["amount"], ANGER_PER_ROUND)
        self.assertEqual(own["cause"], "Anger feeds Mira's intensity.")
        self.assertNotIn("outcome", own)
        # Tomas is not told of her feed at all: no beat, not even the generic line.
        self.assertEqual(self.beats_seen_by(self.tomas), [])
        self.assertNotTold(self.tomas, "Mira surges.")

    def test_the_tuning_admin_refuses_anger_on_a_failure_band(self) -> None:
        tuning = SurgeTuningFactory(trigger_kind=SurgeTriggerKind.RALLIED)
        failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        success = CheckOutcomeFactory(name="Success", success_level=1)
        url = reverse("admin:arxii_surgetuning_change", args=[tuning.pk])

        def with_band(outcome) -> dict:
            data = self.change_post(url)
            data.update(
                {
                    "bands-TOTAL_FORMS": "1",
                    "bands-0-id": "",
                    "bands-0-tuning": str(tuning.pk),
                    "bands-0-outcome": str(outcome.pk),
                    "bands-0-intensity": "3",
                    "bands-0-control_change": "0",
                    "bands-0-condition": str(self.anger.pk),
                }
            )
            return data

        refused = self.client.post(url, with_band(failure))

        self.assertEqual(refused.status_code, 200)
        self.assertContains(refused, "is a failed roll, so it cannot carry")
        self.assertFalse(SurgeDegreeBand.objects.filter(tuning=tuning).exists())

        accepted = self.client.post(url, with_band(success))

        self.assertEqual(accepted.status_code, 302)
        band = SurgeDegreeBand.objects.get(tuning=tuning)
        self.assertEqual(band.condition, self.anger)
