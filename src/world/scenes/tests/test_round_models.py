from django.test import TestCase

from world.scenes.constants import RoundStatus, SceneRoundParticipantStatus


class RoundEnumTests(TestCase):
    def test_round_status_values(self):
        assert RoundStatus.DECLARING == "declaring"
        assert RoundStatus.RESOLVING == "resolving"
        assert RoundStatus.BETWEEN_ROUNDS == "between_rounds"
        assert RoundStatus.COMPLETED == "completed"

    def test_participant_status_values(self):
        assert SceneRoundParticipantStatus.ACTIVE == "active"
        assert SceneRoundParticipantStatus.LEFT == "left"
