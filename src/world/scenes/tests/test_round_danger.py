from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus, SceneRoundStartReason
from world.scenes.models import SceneRound, SceneRoundParticipant
from world.scenes.round_services import auto_start_or_extend_danger_round


class DangerRoundTests(TestCase):
    def setUp(self):
        from evennia_extensions.factories import ObjectDBFactory

        self.room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")

    def _char_in_room(self):
        sheet = CharacterSheetFactory()
        sheet.character.db_location = self.room
        sheet.character.save(update_fields=["db_location"])
        return sheet

    def test_creates_danger_round_enrolling_present_characters(self):
        victim = self._char_in_room()
        bystander = self._char_in_room()
        auto_start_or_extend_danger_round(victim)
        rnd = SceneRound.objects.get(room=self.room)
        assert rnd.start_reason == SceneRoundStartReason.DANGER
        assert rnd.status == RoundStatus.DECLARING
        present = set(
            SceneRoundParticipant.objects.filter(scene_round=rnd).values_list(
                "character_sheet_id", flat=True
            )
        )
        assert victim.pk in present
        assert bystander.pk in present

    def test_idempotent_extends_existing_round(self):
        victim = self._char_in_room()
        auto_start_or_extend_danger_round(victim)
        self._char_in_room()  # a late arrival
        auto_start_or_extend_danger_round(victim)  # called again
        assert SceneRound.objects.filter(room=self.room).count() == 1
