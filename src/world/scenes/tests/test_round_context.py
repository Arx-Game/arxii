from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import RoundStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.round_context import resolve_scene_round_context


class SceneRoundContextTests(TestCase):
    def test_active_participant_resolves_context(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=2)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        ctx = resolve_scene_round_context(sheet)
        assert ctx is not None
        assert ctx.round_id == (rnd.pk, 2)
        assert ctx.is_declaration_open is True

    def test_no_round_returns_none(self):
        sheet = CharacterSheetFactory()
        assert resolve_scene_round_context(sheet) is None

    def test_completed_round_returns_none(self):
        rnd = SceneRoundFactory(status=RoundStatus.COMPLETED)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        assert resolve_scene_round_context(sheet) is None


class SeamBranchTests(TestCase):
    def test_seam_returns_scene_context_when_no_combat(self):
        from actions.round_context import get_active_round_context

        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        ctx = get_active_round_context(sheet)
        assert ctx is not None
        assert ctx.round_id == (rnd.pk, 1)
