"""Journeys for Dig deep and Rally naming a resonance, and a GM kindling by hand (#5124).

Mira and Tomas fight on "The Road". Mira holds Fury and Mercy. Staff authored the strength
rows (the strongest doubles a Dig deep or Rally surge), the Dug deep and Rallied surge
tunings (a Success band of 5 for Dig deep, 4 for Rally) and what a Rally's roll kindles: a
Success kindles strength 1, a Great Success strength 2, a Partial Success nothing.

Hand-worked numbers. Dig deep: a Success band of 5 is 5 unkindled and 10 with a strength
whose ``dig_deep_scale_percent`` is 100 (scale 1.0 + 1.0). Rally: a Success band of 4 is 4,
and 8 when the named resonance was already kindled at that strength.
"""

from __future__ import annotations

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from integration_tests.test_dig_deep_journeys import _DigDeepField
from world.checks.test_helpers import force_check_outcome
from world.combat.constants import SurgeTriggerKind
from world.combat.factories import SocialManeuverConfigFactory
from world.conditions.factories import ConditionTemplateFactory
from world.fatigue.services import get_or_create_fatigue_pool
from world.magic.constants import KindlingSource
from world.magic.factories import (
    CharacterResonanceFactory,
    KindledStrengthTierFactory,
    RallyKindlingStrengthFactory,
    ResonanceFactory,
    kindle_resonance,
)
from world.magic.models import Kindling
from world.magic.services.kindling import kindled_resonances_now
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneGMParticipationFactory
from world.traits.factories import CheckOutcomeFactory

DIG_DEEP_SUCCESS = 5
RALLY_SUCCESS = 4


class _KindledField(_DigDeepField):
    def setUp(self) -> None:
        super().setUp()
        self.fury = ResonanceFactory(name="Fury")
        self.mercy = ResonanceFactory(name="Mercy")
        for held in (self.fury, self.mercy):
            CharacterResonanceFactory(character_sheet=self.mira.sheet_data, resonance=held)
        self.mira.sheet_data.__dict__.pop("cached_resonances", None)
        self.faint = KindledStrengthTierFactory(rank=1, name="Faint", dig_deep_scale_percent=0)
        self.blazing = KindledStrengthTierFactory(
            rank=2, name="Blazing", dig_deep_scale_percent=100
        )

    def mira_strength(self, resonance) -> int | None:
        for entry in kindled_resonances_now(self.mira.sheet_data):
            if entry.resonance == resonance:
                return entry.tier.rank if entry.tier is not None else None
        return None

    def cause_of_last_surge(self) -> str:
        return self.records(SurgeTriggerKind.DUG_DEEP).latest("pk").cause


class DiggingDeepNamingAResonance(_KindledField):
    def test_a_kindled_resonance_raises_the_surge_and_is_named_in_its_cause(self) -> None:
        kindle_resonance(self.mira.sheet_data, self.fury, self.blazing)

        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            told = self.telnet(self.mira, "combat digdeep fury")

        self.assertEqual(self.intensity(self.mira), 2 * DIG_DEEP_SUCCESS)
        self.assertIn("Your Fury is kindled, so the surge is larger.", told)
        self.assertTold(self.mira, f"surge +{DIG_DEEP_SUCCESS}")
        self.assertIn("Fury", self.cause_of_last_surge())

    def test_an_unkindled_or_unnamed_resonance_surges_as_it_always_did(self) -> None:
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            self.telnet(self.mira, "combat digdeep mercy")

        self.assertEqual(self.intensity(self.mira), DIG_DEEP_SUCCESS)
        self.assertNotIn("Mercy", self.cause_of_last_surge())

    def test_a_resonance_she_does_not_hold_is_refused_and_costs_nothing(self) -> None:
        ResonanceFactory(name="Wonder")

        told = self.dig_deep_naming("wonder")

        self.assertIn("You do not hold that resonance.", told)
        self.assertEqual(get_or_create_fatigue_pool(self.mira.sheet_data).mental_current, 0)
        self.assertEqual(self.intensity_or_zero(self.mira), 0)

    def test_the_web_action_takes_the_resonance_by_id(self) -> None:
        kindle_resonance(self.mira.sheet_data, self.fury, self.blazing)

        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            result = self.web(self.mira, "combat_dig_deep", resonance_id=self.fury.pk)

        self.assertTrue(result.detail.success, result.detail.message)
        self.assertEqual(self.intensity(self.mira), 2 * DIG_DEEP_SUCCESS)

    def dig_deep_naming(self, name: str) -> str:
        with self.captureOnCommitCallbacks(execute=True), force_check_outcome(self.success):
            return self.telnet(self.mira, f"combat digdeep {name}")


class RallyingANamedResonance(_KindledField):
    def setUp(self) -> None:
        super().setUp()
        SocialManeuverConfigFactory(
            rally_success_condition=ConditionTemplateFactory(name="Heartened")
        )
        self.author_tuning(SurgeTriggerKind.RALLIED, "Rally", partial=1, success=RALLY_SUCCESS)
        self.great = CheckOutcomeFactory(name="Great Success", success_level=2)
        RallyKindlingStrengthFactory(outcome_tier=self.success, strength=1)
        RallyKindlingStrengthFactory(outcome_tier=self.great, strength=2)

    def rally(self, outcome, resonance: str = "Mercy") -> str:
        told = self.telnet(self.tomas, f"combat rally Mira={resonance}")
        self.resolve(outcome)
        return told

    def rows(self):
        return Kindling.objects.filter(character_sheet=self.mira.sheet_data)

    def tomas_sees(self, seat=None) -> list[dict]:
        """What Tomas's Rally picker reads for the ally at ``seat`` (Mira by default)."""
        seat = seat or self.mira_seat
        return self.rally_picker(self.tomas, seat).json()

    def rally_picker(self, viewer, seat):
        url = f"/api/combat/{self.encounter.pk}/rally-resonances/?ally={seat.pk}"
        return self.api(self.account_of(viewer)).get(url)

    def test_the_rallier_sees_the_allys_resonance_names_and_whether_each_is_kindled(self) -> None:
        kindle_resonance(self.mira.sheet_data, self.fury, self.blazing)

        # Names and a kindled flag only: never how strongly.
        self.assertEqual(
            self.tomas_sees(),
            [
                {"id": self.fury.pk, "name": "Fury", "kindled": True},
                {"id": self.mercy.pk, "name": "Mercy", "kindled": False},
            ],
        )
        self.assertEqual(self.tomas_sees(self.tomas_seat), [])

    def test_the_flag_follows_a_rally_that_kindles_it(self) -> None:
        self.rally(self.success)

        mercy = self.tomas_sees()[1]

        self.assertEqual((mercy["name"], mercy["kindled"]), ("Mercy", True))

    def test_someone_not_in_the_fight_is_refused_the_resonance_names(self) -> None:
        outsider = self.make_player("Odo", room=self.road)

        self.assertEqual(self.rally_picker(outsider, self.mira_seat).status_code, 403)

    def test_a_finished_fight_returns_no_resonances(self) -> None:
        kindle_resonance(self.mira.sheet_data, self.fury, self.blazing)
        self.assertEqual(len(self.tomas_sees()), 2)

        self.encounter.status = RoundStatus.COMPLETED
        self.encounter.save(update_fields=["status"])

        response = self.rally_picker(self.tomas, self.mira_seat)
        self.assertEqual((response.status_code, response.json()), (200, []))

    def test_the_polled_encounter_payload_evaluates_no_kindling(self) -> None:
        client = self.api(self.account_of(self.tomas))
        url = f"/api/combat/{self.encounter.pk}/"
        client.get(url)
        with CaptureQueriesContext(connection) as queries:
            body = client.get(url).json()

        kindling_reads = [q["sql"] for q in queries.captured_queries if "kindl" in q["sql"].lower()]
        self.assertEqual(kindling_reads, [])
        self.assertTrue(all("rally_resonances" not in p for p in body["participants"]))

    def test_a_rally_kindles_an_unkindled_resonance_for_the_fight(self) -> None:
        self.assertIsNone(self.mira_strength(self.mercy))

        self.rally(self.success)

        row = self.rows().get()
        self.assertEqual(
            (row.resonance, row.source, row.encounter, row.strength, row.kindled_by),
            (
                self.mercy,
                KindlingSource.RALLY,
                self.encounter,
                1,
                self.tomas.sheet_data,
            ),
        )
        self.assertEqual(self.mira_strength(self.mercy), 1)
        panel = self.api(self.account_of(self.mira)).get(
            "/api/magic/kindled-resonances/", {"character_sheet": self.mira.sheet_data.pk}
        )
        mercy = {r["name"]: r for r in panel.json()["results"]}["Mercy"]
        self.assertEqual(mercy["strength_name"], "Faint")
        self.assertEqual(mercy["reasons"], ["Tomas rallied you"])

    def test_the_web_rally_names_the_resonance_by_id_and_kindles_it_the_same_way(self) -> None:
        result = self.web(
            self.tomas,
            "combat_rally",
            ally_participant_id=self.mira_seat.pk,
            resonance_id=self.mercy.pk,
        )
        self.assertTrue(result.detail.success, result.detail.message)

        self.resolve(self.success)

        row = self.rows().get()
        self.assertEqual(
            (row.resonance, row.source, row.strength), (self.mercy, KindlingSource.RALLY, 1)
        )

    def test_the_strength_follows_how_well_the_rally_rolled(self) -> None:
        self.rally(self.great)

        self.assertEqual(self.rows().get().strength, 2)

    def test_a_rally_that_earns_no_strength_kindles_nothing(self) -> None:
        self.rally(self.partial)

        self.assertFalse(self.rows().exists())
        self.assertIsNone(self.mira_strength(self.mercy))

    def test_a_second_rally_keeps_one_row_at_the_stronger_strength(self) -> None:
        self.rally(self.success)
        self.close_round()
        self.rally(self.great)
        self.close_round()
        self.rally(self.success)

        self.assertEqual(self.rows().get().strength, 2)

    def test_a_rally_on_an_already_kindled_resonance_surges_more_and_writes_no_row(self) -> None:
        kindle_resonance(self.mira.sheet_data, self.mercy, self.blazing)

        self.rally(self.success)

        self.assertFalse(self.rows().exists())
        self.assertEqual(self.intensity(self.mira), 2 * RALLY_SUCCESS)
        cause = self.records(SurgeTriggerKind.RALLIED).get().cause
        self.assertIn("Mercy", cause)

    def test_an_unkindled_resonance_surges_the_plain_amount(self) -> None:
        self.rally(self.success)

        self.assertEqual(self.intensity(self.mira), RALLY_SUCCESS)

    def test_a_resonance_the_ally_does_not_hold_is_refused(self) -> None:
        ResonanceFactory(name="Wonder")

        told = self.telnet(self.tomas, "combat rally Mira=Wonder")

        self.assertIn("That is not one of their resonances.", told)

    def test_the_kindling_ends_with_the_fight(self) -> None:
        self.rally(self.success)
        self.assertEqual(self.mira_strength(self.mercy), 1)

        self.encounter.completed_at = timezone.now()
        self.encounter.save(update_fields=["completed_at"])

        self.assertIsNone(self.mira_strength(self.mercy))


class AGmKindlingByHand(_KindledField):
    def setUp(self) -> None:
        super().setUp()
        from evennia_extensions.factories import RoomProfileFactory

        self.gm = self.make_player("Ysmay", room=self.road)
        self.scene = SceneFactory(location=RoomProfileFactory(objectdb=self.road), is_active=True)
        SceneGMParticipationFactory(scene=self.scene, account=self.account_of(self.gm))

    def test_a_gm_kindles_a_resonance_for_the_scene_and_it_shows_on_her_panel(self) -> None:
        told = self.telnet(self.gm, "stage kindle Mira=Fury:Blazing")

        self.assertIn("Mira's Fury is kindled, blazing, for this scene.", told)
        row = Kindling.objects.get()
        self.assertEqual(
            (row.source, row.scene, row.encounter, row.strength, row.kindled_by),
            (KindlingSource.GM, self.scene, None, 2, self.gm.sheet_data),
        )
        self.assertEqual(self.mira_strength(self.fury), 2)
        panel = self.api(self.account_of(self.mira)).get(
            "/api/magic/kindled-resonances/", {"character_sheet": self.mira.sheet_data.pk}
        )
        fury = {r["name"]: r for r in panel.json()["results"]}["Fury"]
        self.assertEqual(fury["strength_name"], "Blazing")
        self.assertEqual(fury["reasons"], ["The GM has kindled it"])

    def test_kindling_it_again_sets_the_new_strength_on_the_one_row(self) -> None:
        self.telnet(self.gm, "stage kindle Mira=Fury:2")
        self.telnet(self.gm, "stage kindle Mira=Fury:1")

        self.assertEqual(Kindling.objects.get().strength, 1)

    def test_it_ends_with_the_scene(self) -> None:
        self.telnet(self.gm, "stage kindle Mira=Fury")
        self.assertEqual(self.mira_strength(self.fury), 1)

        self.scene.delete()

        self.assertFalse(Kindling.objects.exists())

    def test_only_the_scenes_gm_may_kindle(self) -> None:
        told = self.telnet(self.tomas, "stage kindle Mira=Fury")

        self.assertIn("Only the scene's GM, owner, or staff may kindle a resonance.", told)
        self.assertFalse(Kindling.objects.exists())

    def test_a_resonance_the_character_does_not_hold_is_refused(self) -> None:
        ResonanceFactory(name="Wonder")

        told = self.telnet(self.gm, "stage kindle Mira=Wonder")

        self.assertIn("They do not hold that resonance.", told)
        self.assertFalse(Kindling.objects.exists())

    def test_the_web_stage_tab_lists_what_she_holds_and_kindles_by_id(self) -> None:
        listed = self.web(self.gm, "gm_list_kindling", target_id=self.mira.pk)

        self.assertEqual(
            listed.detail.data["strengths"],
            [{"rank": 1, "name": "Faint"}, {"rank": 2, "name": "Blazing"}],
        )
        self.assertEqual(
            listed.detail.data["resonances"],
            [{"id": self.fury.pk, "name": "Fury"}, {"id": self.mercy.pk, "name": "Mercy"}],
        )

        done = self.web(
            self.gm,
            "stage_kindle",
            target_id=self.mira.pk,
            resonance=str(self.mercy.pk),
            strength="2",
        )

        self.assertTrue(done.detail.success, done.detail.message)
        self.assertEqual(self.mira_strength(self.mercy), 2)
        again = self.web(self.gm, "gm_list_kindling", target_id=self.mira.pk)
        self.assertEqual(
            again.detail.data["kindled"],
            [{"resonance_id": self.mercy.pk, "strength": 2, "by_viewer": True}],
        )

    def test_the_stage_list_reads_only_characters_in_the_gms_room(self) -> None:
        elsewhere = self.make_player("Wren", room=self.make_room("The Ford"))
        CharacterResonanceFactory(character_sheet=elsewhere.sheet_data, resonance=self.fury)

        away = self.web(self.gm, "gm_list_kindling", target_id=elsewhere.pk)
        junk = self.web(self.gm, "gm_list_kindling", target_id="not-a-number")

        for refused in (away, junk):
            self.assertFalse(refused.detail.success)
            self.assertEqual(refused.detail.message, "Whose resonance? Name a character here.")
