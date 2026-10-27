"""Surge beats in the round payload carry the roll for owner, GM and staff only (#4737)."""

from unittest.mock import patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.combat.constants import ParticipantStatus, SurgeTriggerKind
from world.combat.escalation import apply_dramatic_surge
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    EscalationCurveFactory,
    SurgeDegreeBandFactory,
    SurgeTuningFactory,
)
from world.combat.models import SurgeTuning
from world.combat.surge_rolls import apply_rolled_surge
from world.conditions.factories import ConditionTemplateFactory
from world.conditions.types import ApplyConditionResult
from world.mechanics.constants import EngagementType
from world.mechanics.services import begin_engagement
from world.roster.factories import RosterTenureFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneFactory, SceneParticipationFactory
from world.traits.factories import CheckOutcomeFactory

GENERIC_KEYS = {"id", "narration"}
OWNER_KEYS = {"trigger_kind", "amount", "participant"}
ROLL_KEYS = {"outcome", "potency", "control_change", "condition", "roll"}
ROLL_LINE = "Composure check vs taunt potency 14. Partial. Intensity +5, control -1. Goaded."


def _player(username: str, db_key: str) -> tuple[object, object]:
    account = AccountFactory(username=username)
    character = CharacterFactory(db_key=db_key)
    sheet = CharacterSheetFactory(character=character)
    RosterTenureFactory(
        roster_entry__character_sheet__character=character, player_data__account=account
    )
    return account, sheet


@override_settings(SEED_SAMPLE_CONTENT=True)  # the curve factory gates on #2698
class SurgeBeatRollFieldTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.curve = EscalationCurveFactory(surge_narration="{character} surges.")
        cls.scene = SceneFactory()
        cls.encounter = CombatEncounterFactory(
            scene=cls.scene,
            escalation_curve=cls.curve,
            status=RoundStatus.DECLARING,
            round_number=1,
        )
        cls.owner_account, cls.owner_sheet = _player("surge_owner", "Surgeowner")
        cls.other_account, cls.other_sheet = _player("surge_other", "Surgeother")
        cls.staff_account = AccountFactory(username="surge_staff", is_staff=True)
        cls.gm_account = AccountFactory(username="surge_gm")
        SceneParticipationFactory(scene=cls.scene, account=cls.gm_account, is_gm=True)
        cls.owner_seat = CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.owner_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        CombatParticipantFactory(
            encounter=cls.encounter,
            character_sheet=cls.other_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        begin_engagement(cls.owner_sheet.character, EngagementType.COMBAT, source=cls.encounter)
        cls.tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
            check_type=CheckTypeFactory(name="Composure"),
        )
        cls.partial = CheckOutcomeFactory(name="Partial", success_level=0)
        cls.goaded = ConditionTemplateFactory(name="Goaded")
        SurgeDegreeBandFactory(
            tuning=cls.tuning,
            outcome=cls.partial,
            intensity=5,
            control_change=-1,
            condition=cls.goaded,
        )

    def _beats_seen_by(self, account: object) -> list[dict]:
        client = APIClient()
        client.force_authenticate(user=account)
        response = client.get(f"/api/combat/{self.encounter.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["surge_beats"]

    def _rolled_surge(self) -> None:
        beat = apply_rolled_surge(
            encounter=self.encounter,
            participant=self.owner_seat,
            trigger_kind=SurgeTriggerKind.TAUNT_RECEIVED,
            outcome=self.partial,
            potency=14,
        )
        self.assertIsNotNone(beat)

    def test_surge_beat_roll_visible_to_owner_staff_hidden_from_others(self) -> None:
        self._rolled_surge()

        for account in (self.owner_account, self.staff_account, self.gm_account):
            (beat,) = self._beats_seen_by(account)
            self.assertEqual(set(beat), GENERIC_KEYS | OWNER_KEYS | ROLL_KEYS)
            self.assertEqual(beat["outcome"], "Partial")
            self.assertEqual(beat["potency"], 14)
            self.assertEqual(beat["control_change"], -1)
            self.assertEqual(beat["condition"], "Goaded")
            self.assertEqual(beat["roll"], ROLL_LINE)
            self.assertEqual(beat["trigger_kind"], SurgeTriggerKind.TAUNT_RECEIVED)
            self.assertEqual(beat["amount"], 5)

        (beat,) = self._beats_seen_by(self.other_account)
        self.assertEqual(set(beat), GENERIC_KEYS)
        self.assertEqual(beat["narration"], "Surgeowner surges.")

    def _rallied_tuning(self) -> None:
        tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=CheckTypeFactory(name="Rally")
        )
        SurgeDegreeBandFactory(
            tuning=tuning, outcome=self.partial, intensity=4, control_change=0, condition=None
        )

    def _rallied_surge(self) -> None:
        beat = apply_rolled_surge(
            encounter=self.encounter,
            participant=self.owner_seat,
            trigger_kind=SurgeTriggerKind.RALLIED,
            outcome=self.partial,
            potency=None,
        )
        self.assertIsNotNone(beat)

    def test_a_band_without_a_condition_gives_a_null_condition_and_no_condition_text(self) -> None:
        self._rallied_tuning()
        self._rallied_surge()

        (beat,) = self._beats_seen_by(self.owner_account)
        self.assertIsNone(beat["condition"])
        self.assertIsNone(beat["potency"])
        self.assertEqual(beat["roll"], "Rally check. Partial. Intensity +4, control 0.")

    def test_a_condition_that_did_not_take_hold_is_not_named(self) -> None:
        refused = ApplyConditionResult(success=False, instance=None, message="resisted")
        with patch("world.conditions.services.apply_condition", return_value=refused):
            self._rolled_surge()

        (beat,) = self._beats_seen_by(self.owner_account)
        self.assertIsNone(beat["condition"])
        self.assertEqual(
            beat["roll"], "Composure check vs taunt potency 14. Partial. Intensity +5, control -1."
        )

    def test_the_condition_that_applied_is_shown_after_the_band_is_retuned(self) -> None:
        tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=CheckTypeFactory(name="Rally")
        )
        band = SurgeDegreeBandFactory(
            tuning=tuning, outcome=self.partial, intensity=4, condition=self.goaded
        )
        self._rallied_surge()
        band.condition = ConditionTemplateFactory(name="Furious")
        band.intensity = 9
        band.save()

        (beat,) = self._beats_seen_by(self.owner_account)
        self.assertEqual(beat["condition"], "Goaded")
        self.assertEqual(beat["roll"], "Rally check. Partial. Intensity +4, control 0. Goaded.")

    def test_a_control_only_surge_beat_has_no_power_surges_narration(self) -> None:
        tuning = SurgeTuningFactory(
            trigger_kind=SurgeTriggerKind.RALLIED, check_type=CheckTypeFactory(name="Rally")
        )
        SurgeDegreeBandFactory(tuning=tuning, outcome=self.partial, intensity=0, control_change=-2)
        self._rallied_surge()

        (other_beat,) = self._beats_seen_by(self.other_account)
        self.assertEqual(other_beat["narration"], "")
        (owner_beat,) = self._beats_seen_by(self.owner_account)
        self.assertEqual(owner_beat["roll"], "Rally check. Partial. Intensity +0, control -2.")

    def test_old_kind_surge_beat_unchanged(self) -> None:
        apply_dramatic_surge(
            encounter=self.encounter,
            participant=self.owner_seat,
            amount=3,
            trigger_kind=SurgeTriggerKind.HIGH_STAKES,
        )

        (owner_beat,) = self._beats_seen_by(self.owner_account)
        self.assertEqual(set(owner_beat), GENERIC_KEYS | OWNER_KEYS)
        self.assertEqual(owner_beat["amount"], 3)
        (staff_beat,) = self._beats_seen_by(self.staff_account)
        self.assertEqual(set(staff_beat), GENERIC_KEYS | OWNER_KEYS)
        (other_beat,) = self._beats_seen_by(self.other_account)
        self.assertEqual(set(other_beat), GENERIC_KEYS)

    def test_a_rolled_beat_whose_tuning_was_removed_keeps_the_stored_roll_fields(self) -> None:
        self._rallied_tuning()
        self._rallied_surge()
        SurgeTuning.objects.get(trigger_kind=SurgeTriggerKind.RALLIED).delete()

        (beat,) = self._beats_seen_by(self.owner_account)
        self.assertEqual(beat["outcome"], "Partial")
        self.assertIsNone(beat["potency"])
        self.assertEqual(beat["control_change"], 0)
        self.assertIsNone(beat["condition"])
        self.assertNotIn("roll", beat)
