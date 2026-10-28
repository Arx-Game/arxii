"""The social maneuver config singleton and the condition-fed surge record (#4739).

U-keep: a config accessor and a database constraint have no player path of their
own; the maneuvers and the per-round feed that read them have journeys.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.combat.constants import SurgeTriggerKind
from world.combat.factories import CombatParticipantFactory
from world.combat.models import DramaticSurgeRecord, SocialManeuverConfig
from world.combat.services.encounter.config import get_social_maneuver_config


class SocialManeuverConfigTests(TestCase):
    def test_get_creates_singleton_once(self) -> None:
        self.assertFalse(SocialManeuverConfig.objects.exists())
        first = get_social_maneuver_config()
        second = get_social_maneuver_config()
        self.assertEqual(first.pk, 1)
        self.assertIs(first, second)
        self.assertEqual(SocialManeuverConfig.objects.count(), 1)
        self.assertIsNone(first.taunt_check_type_id)
        self.assertIsNone(first.rally_success_condition_id)


class ConditionFedRecordConstraintTests(TestCase):
    def setUp(self) -> None:
        self.participant = CombatParticipantFactory()

    def _record(self, trigger_kind: str) -> DramaticSurgeRecord:
        return DramaticSurgeRecord.objects.create(
            encounter=self.participant.encounter,
            participant=self.participant,
            trigger_kind=trigger_kind,
            amount=3,
            round_number=2,
            repeat_round=2,
            outcome=None,
        )

    def test_condition_fed_record_without_outcome_is_allowed(self) -> None:
        record = self._record(SurgeTriggerKind.CONDITION_FED)
        self.assertIsNone(record.outcome_id)

    def test_rallied_record_without_outcome_is_refused(self) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._record(SurgeTriggerKind.RALLIED)
