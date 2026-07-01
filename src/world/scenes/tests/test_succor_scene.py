from unittest.mock import MagicMock, patch

from django.test import TestCase

from world.mechanics.constants import ResolutionType
from world.scenes.constants import RoundStatus, SceneRoundMode, SceneRoundParticipantStatus
from world.scenes.factories import SceneRoundFactory, SceneRoundParticipantFactory
from world.scenes.models import SceneActionDeclaration
from world.scenes.round_context import SceneRoundContext
from world.scenes.round_services import (
    _resolve_scene_declarations,
    declare_succor_scene,
    resolve_scene_round,
)


class DeclareSuccorSceneTests(TestCase):
    def test_declare_succor_scene_writes_declaration(self):
        scene_round = SceneRoundFactory(status=RoundStatus.DECLARING, mode=SceneRoundMode.STRICT)
        succorer = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        declaration = declare_succor_scene(succorer, ally)
        self.assertEqual(declaration.succor_target_id, ally.pk)
        self.assertIsNone(declaration.succor_resolution)


class SceneGetCoverForTests(TestCase):
    def test_no_succor_declared_returns_no_cover(self):
        scene_round = SceneRoundFactory(status=RoundStatus.RESOLVING)
        target = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ctx = SceneRoundContext(scene_round)
        result = ctx.get_cover_for(target.character_sheet, damage_type=None)
        self.assertEqual(result, 1.0)


class ResolveSceneRoundWithPendingSuccorTests(TestCase):
    """Regression coverage for Bug 1 (#1744 review): a pending Succor declaration has
    challenge_instance=None (it is identified by succor_target instead), so it must
    never be fed into the generic challenge-resolution sweep — that sweep
    unconditionally dereferences req.challenge_instance.location, which previously
    raised AttributeError and crashed the whole @transaction.atomic round resolution
    any time a Succor declaration was pending."""

    def test_resolve_scene_round_does_not_crash_with_pending_succor(self):
        scene_round = SceneRoundFactory(
            status=RoundStatus.DECLARING, round_number=1, mode=SceneRoundMode.STRICT
        )
        succorer = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        declare_succor_scene(succorer, ally)

        # Previously: AttributeError: 'NoneType' object has no attribute 'location'.
        resolve_scene_round(scene_round)

        # start_reason defaults to OPT_IN (not DANGER), so a clean resolution advances
        # straight back into DECLARING for the next round — confirms the whole
        # function ran to completion rather than merely swallowing an exception.
        scene_round.refresh_from_db()
        self.assertEqual(scene_round.status, RoundStatus.DECLARING)
        self.assertEqual(scene_round.round_number, 2)

    def test_maybe_resolve_scene_round_does_not_crash_with_pending_succor(self):
        """Same as above but through the production quorum-gated entry point — both
        participants are placed in the room and declare, so scene_round_is_complete's
        presence-gated quorum is genuinely met and resolution actually fires."""
        from evennia_extensions.factories import ObjectDBFactory
        from world.character_sheets.factories import CharacterSheetFactory
        from world.scenes.round_services import maybe_resolve_scene_round

        room = ObjectDBFactory(db_typeclass_path="typeclasses.rooms.Room")
        scene_round = SceneRoundFactory(
            room=room,
            status=RoundStatus.DECLARING,
            round_number=1,
            mode=SceneRoundMode.STRICT,
            advance_quorum_pct=100,
        )

        succorer_sheet = CharacterSheetFactory()
        succorer_sheet.character.db_location = room
        succorer_sheet.character.save(update_fields=["db_location"])
        ally_sheet = CharacterSheetFactory()
        ally_sheet.character.db_location = room
        ally_sheet.character.save(update_fields=["db_location"])

        succorer = SceneRoundParticipantFactory(
            scene_round=scene_round,
            character_sheet=succorer_sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        ally = SceneRoundParticipantFactory(
            scene_round=scene_round,
            character_sheet=ally_sheet,
            status=SceneRoundParticipantStatus.ACTIVE,
        )
        declare_succor_scene(succorer, ally)
        declare_succor_scene(ally, succorer)

        # Both present+can_act participants have declared -> quorum met -> resolves.
        # Previously: AttributeError: 'NoneType' object has no attribute 'location'.
        maybe_resolve_scene_round(scene_round)

        # start_reason defaults to OPT_IN, so resolution advances back to DECLARING
        # for the next round (round_number += 1) — confirms resolve_scene_round ran
        # to completion (rather than scene_round_is_complete silently no-op'ing).
        scene_round.refresh_from_db()
        self.assertEqual(scene_round.status, RoundStatus.DECLARING)
        self.assertEqual(scene_round.round_number, 2)


class SceneSuccorCoverCachingSurvivesResolutionSweepTests(TestCase):
    """Regression coverage for Bug 2 (#1744 review): the round's declaration sweep
    previously deleted ALL SceneActionDeclaration rows (including Succor rows) before
    get_cover_for's cache could ever be read on the END tick, so cover would always
    silently fall back to the 1.0 no-cover default. Proves a NON-default resolved
    value survives the sweep, distinguishing this from a trivial 1.0 == 1.0 check."""

    def test_get_cover_for_caches_nondefault_value_across_the_declaration_sweep(self):
        scene_round = SceneRoundFactory(
            status=RoundStatus.DECLARING, round_number=1, mode=SceneRoundMode.STRICT
        )
        succorer = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        target = SceneRoundParticipantFactory(
            scene_round=scene_round, status=SceneRoundParticipantStatus.ACTIVE
        )
        declare_succor_scene(succorer, target)

        # A "partial block" graded outcome (success_level == 0, not DESTROY) maps to a
        # 0.5 multiplier via apply_succor_outcome — a value that is neither the
        # SceneActionDeclaration.succor_resolution field default (None) nor the
        # no-cover fallback (1.0), so caching it proves a real resolution happened.
        fake_result = MagicMock()
        fake_result.check_result = MagicMock(success_level=0)
        fake_result.resolution_type = ResolutionType.PERSONAL

        def _fake_dispatch(*args, **kwargs):
            kwargs["outcome_fn"](fake_result)
            return fake_result

        ctx = SceneRoundContext(scene_round)
        with patch(
            "world.mechanics.reactions.dispatch_capability_reaction",
            side_effect=_fake_dispatch,
        ) as mocked_dispatch:
            first = ctx.get_cover_for(target.character_sheet, damage_type=None)

        self.assertEqual(first, 0.5)
        declaration = SceneActionDeclaration.objects.get(
            scene_round=scene_round,
            round_number=scene_round.round_number,
            succor_target=target,
        )
        self.assertEqual(declaration.succor_resolution, 0.5)

        # Simulate the round's declaration-resolution sweep — the exact crash/deletion
        # site both bugs lived in. The Succor row (and its cached resolution) must
        # survive it.
        _resolve_scene_declarations(scene_round)

        declaration.refresh_from_db()
        self.assertEqual(declaration.succor_resolution, 0.5)

        # A second get_cover_for call must return the cached value from the
        # still-present row WITHOUT re-dispatching the capability reaction.
        second = ctx.get_cover_for(target.character_sheet, damage_type=None)
        self.assertEqual(second, 0.5)
        mocked_dispatch.assert_called_once()
