import types

from django.test import TestCase

from actions.constants import ActionBackend
from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.factories import ChallengeApproachFactory, ChallengeInstanceFactory
from world.scenes.constants import RoundStatus, SceneRoundStartReason
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import SceneActionDeclaration
from world.scenes.round_context import SceneRoundContext, resolve_scene_round_context


class SceneRoundContextTests(TestCase):
    def test_active_participant_resolves_context(self):
        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=2)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        ctx = resolve_scene_round_context(sheet)
        assert ctx is not None
        assert ctx.round_id == (rnd.pk, 2)
        # OPT_IN + DECLARING is a social round that now gathers declarations.
        assert ctx.is_declaration_open is True

    def test_no_round_returns_none(self):
        sheet = CharacterSheetFactory()
        assert resolve_scene_round_context(sheet) is None

    def test_completed_round_returns_none(self):
        rnd = SceneRoundFactory(status=RoundStatus.COMPLETED)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        assert resolve_scene_round_context(sheet) is None


class DeclarationGatingTests(TestCase):
    def test_opt_in_declaring_round_is_declaration_open(self):
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.OPT_IN, status=RoundStatus.DECLARING
        )
        assert SceneRoundContext(rnd).is_declaration_open is True

    def test_gm_declaring_round_is_declaration_open(self):
        rnd = SceneRoundFactory(start_reason=SceneRoundStartReason.GM, status=RoundStatus.DECLARING)
        assert SceneRoundContext(rnd).is_declaration_open is True

    def test_danger_round_is_not_declaration_open(self):
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.DANGER, status=RoundStatus.DECLARING
        )
        assert SceneRoundContext(rnd).is_declaration_open is False

    def test_between_rounds_is_not_declaration_open(self):
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.OPT_IN, status=RoundStatus.BETWEEN_ROUNDS
        )
        assert SceneRoundContext(rnd).is_declaration_open is False


class RecordDeclarationTests(TestCase):
    def test_records_challenge_declaration(self):
        rnd = SceneRoundFactory(
            start_reason=SceneRoundStartReason.OPT_IN,
            status=RoundStatus.DECLARING,
            round_number=3,
        )
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        challenge_instance = ChallengeInstanceFactory()
        challenge_approach = ChallengeApproachFactory()
        player_action = types.SimpleNamespace(
            backend=ActionBackend.CHALLENGE,
            ref=types.SimpleNamespace(
                challenge_instance_id=challenge_instance.pk,
                approach_id=challenge_approach.pk,
            ),
        )

        SceneRoundContext(rnd).record_declaration(sheet, player_action, {})

        decls = SceneActionDeclaration.objects.filter(scene_round=rnd)
        assert decls.count() == 1
        decl = decls.get()
        assert decl.is_pass is False
        assert decl.round_number == 3
        assert decl.challenge_instance_id == challenge_instance.pk
        assert decl.challenge_approach_id == challenge_approach.pk


class SeamBranchTests(TestCase):
    def test_seam_returns_scene_context_when_no_combat(self):
        from actions.round_context import get_active_round_context

        rnd = SceneRoundFactory(status=RoundStatus.DECLARING, round_number=1)
        sheet = CharacterSheetFactory()
        SceneRoundParticipantFactory(scene_round=rnd, character_sheet=sheet)
        ctx = get_active_round_context(sheet)
        assert ctx is not None
        assert ctx.round_id == (rnd.pk, 1)
