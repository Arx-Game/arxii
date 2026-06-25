from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import (
    RoundStatus,
    SceneRoundMode,
    SceneRoundStartReason,
)
from world.scenes.models import SceneRound, SceneRoundParticipant
from world.scenes.round_services import ensure_round_for_acute_condition


class DangerRoundTests(TestCase):
    """Danger is no longer a separate round type: an acute peril ensures a STRICT
    SceneRound(start_reason=DANGER) and enrols everyone present (#1466)."""

    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

    def _char_in_room(self):
        sheet = CharacterSheetFactory()
        sheet.character.db_location = self.room
        sheet.character.save(update_fields=["db_location"])
        return sheet

    def test_creates_strict_danger_round_enrolling_present_characters(self):
        victim = self._char_in_room()
        bystander = self._char_in_room()
        ensure_round_for_acute_condition(victim)
        rnd = SceneRound.objects.get(room=self.room)
        assert rnd.start_reason == SceneRoundStartReason.DANGER
        # The behavioral heart of #1466: danger is an ordinary STRICT round, not forced OPEN.
        assert rnd.mode == SceneRoundMode.STRICT
        assert rnd.status == RoundStatus.DECLARING
        present = set(
            SceneRoundParticipant.objects.filter(scene_round=rnd).values_list(
                "character_sheet_id", flat=True
            )
        )
        assert victim.pk in present
        assert bystander.pk in present

    def test_idempotent_rides_existing_round(self):
        victim = self._char_in_room()
        ensure_round_for_acute_condition(victim)
        self._char_in_room()  # a late arrival
        ensure_round_for_acute_condition(victim)  # called again
        assert SceneRound.objects.filter(room=self.room).count() == 1

    def test_peril_rides_an_existing_social_round_without_changing_it(self):
        """One active round per room: a peril arising while a non-danger social round is
        active rides that round (no new round, mode preserved, not auto-ended)."""
        from world.scenes.factories import SceneRoundFactory

        social = SceneRoundFactory(
            room=self.room,
            status=RoundStatus.DECLARING,
            round_number=1,
            start_reason=SceneRoundStartReason.OPT_IN,
            mode=SceneRoundMode.POSE_ORDER,
        )
        victim = self._char_in_room()
        rnd = ensure_round_for_acute_condition(victim)
        assert rnd.pk == social.pk
        assert SceneRound.objects.filter(room=self.room).count() == 1
        rnd.refresh_from_db()
        assert rnd.start_reason == SceneRoundStartReason.OPT_IN  # unchanged
        assert rnd.mode == SceneRoundMode.POSE_ORDER  # unchanged
