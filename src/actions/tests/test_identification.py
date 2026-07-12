"""IdentifyAction (#1107 slice 5, Task 3) — the identify command's wrapper over
``attempt_identification``.

Action-seam journeys: success/botch/failure result messaging (roller-only), the
prerequisite gate (co-located + presenting a fake-name persona), guess parsing, and the
REST-dispatch ``target_persona_id`` resolution shape (the #2163 gotcha).
"""

from __future__ import annotations

from django.test import TestCase

from actions.constants import TargetKind
from actions.definitions.identification import IdentifyAction
from actions.registry import get_action
from evennia_extensions.factories import RoomProfileFactory
from world.checks.test_helpers import force_check_outcome
from world.npc_services.factories import FunctionaryFactory, NPCRoleFactory
from world.npc_services.models import Functionary
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import SceneFactory
from world.scenes.interaction_services import get_active_scene
from world.scenes.models import Interaction, PersonaDiscovery
from world.scenes.services import create_mask
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.investigation_checks import seed_investigation_check_content
from world.traits.factories import CheckOutcomeFactory


class IdentifyActionTestCase(TestCase):
    def setUp(self) -> None:
        seed_check_resolution_tables()
        seed_investigation_check_content()

        room_profile = RoomProfileFactory()
        self.room = room_profile.objectdb

        viewer_roster = RosterEntryFactory()
        self.viewer = viewer_roster.character_sheet.character
        self.viewer.move_to(self.room, quiet=True)

        target_roster = RosterEntryFactory()
        self.target = target_roster.character_sheet.character
        self.target_sheet = target_roster.character_sheet
        self.target.move_to(self.room, quiet=True)
        self.mask = create_mask(self.target_sheet, name="Nobody in Particular")

        self.action = IdentifyAction()


class RegistrationTests(IdentifyActionTestCase):
    def test_registered_with_persona_target_kind(self) -> None:
        action = get_action("identify")
        assert isinstance(action, IdentifyAction)
        assert action.target_kind == TargetKind.PERSONA

    def test_get_player_actions_never_lists_identify(self) -> None:
        # #1107 Task 3 review (Critical finding): identify must NOT be surfaced by
        # get_player_actions — every generic-panel consumer of that list
        # (ActionPanel.tsx, PersonaContextMenu.tsx's targetedActions) dispatches through
        # the CONSENT pipeline (createActionRequest), which identify (a no-consent
        # private perception roll, ADR-0024) must never enter: it has no ActionTemplate
        # and no CUSTOM_ACTION_RESOLVERS entry, so an accepted consent request would
        # crash, and the masked target would wrongly get an accept/deny veto over the
        # roll. identify's only web path is now a dedicated PersonaContextMenu
        # "Identify" item that dispatches REGISTRY REST directly
        # (useDispatchPlayerAction), never this listing. Superseded the old
        # `_identification_actions` adapter this test used to assert the presence of.
        from actions.constants import ActionBackend
        from actions.player_interface import get_player_actions

        actions = get_player_actions(self.viewer)
        identify_entries = [
            a
            for a in actions
            if a.backend == ActionBackend.REGISTRY and a.ref.registry_key == "identify"
        ]
        self.assertEqual(identify_entries, [])


class PrerequisiteTests(IdentifyActionTestCase):
    def test_undisguised_target_fails_prerequisite_cleanly(self) -> None:
        stranger_roster = RosterEntryFactory()
        stranger = stranger_roster.character_sheet.character
        stranger.move_to(self.room, quiet=True)

        result = self.action.run(actor=self.viewer, target=stranger)

        self.assertFalse(result.success)
        self.assertIn("no mask to see through", result.message)
        self.assertFalse(PersonaDiscovery.objects.exists())

    def test_target_not_present_fails_prerequisite(self) -> None:
        other_room = RoomProfileFactory().objectdb
        self.target.move_to(other_room, quiet=True)

        result = self.action.run(actor=self.viewer, target=self.target)

        self.assertFalse(result.success)
        self.assertIn("aren't here", result.message)

    def test_no_target_fails_prerequisite(self) -> None:
        result = self.action.run(actor=self.viewer)

        self.assertFalse(result.success)
        self.assertIn("Identify whom", result.message)


class OutcomeMessagingTests(IdentifyActionTestCase):
    def test_success_writes_discovery_and_messages_roller_only(self) -> None:
        success = CheckOutcomeFactory(name="IdentifyAction Success", success_level=2)
        with force_check_outcome(success):
            result = self.action.run(actor=self.viewer, target=self.target)

        self.assertTrue(result.success)
        self.assertIn(self.target_sheet.primary_persona.name, result.message)
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

    def test_botch_reveals_a_functionary_never_a_pc(self) -> None:
        role = NPCRoleFactory(name="Gate Clerk")
        functionary = FunctionaryFactory(role=role, name_override="Old Marta")
        botch = CheckOutcomeFactory(name="IdentifyAction Botch", success_level=-2)

        with force_check_outcome(botch):
            result = self.action.run(actor=self.viewer, target=self.target)

        self.assertFalse(result.success)
        self.assertIn(functionary.display_name, result.message)
        self.assertNotIn(self.target_sheet.primary_persona.name, result.message)
        self.assertNotIn(self.mask.name, result.message)
        self.assertFalse(PersonaDiscovery.objects.exists())

    def test_failure_and_no_functionary_botch_share_the_same_message(self) -> None:
        # Oracle rule, echoed at the action seam: a plain failure and a botch-with-no-NPC-to-
        # blame both degrade to the identical FAILURE/AUTO_FAIL player_message. Exercises the
        # actual botch-with-no-functionary-to-blame branch of _roll_outcome_result (no
        # Functionary exists in this TestCase's setUp) — #1107 Task 3 review, Minor finding 4:
        # this test previously only ran a plain FAILURE (success_level=-1), never a real botch,
        # so it never touched the "no functionary" degrade path its name promised.
        self.assertFalse(Functionary.objects.exists())

        failure = CheckOutcomeFactory(name="IdentifyAction Failure", success_level=-1)
        with force_check_outcome(failure):
            failure_result = self.action.run(actor=self.viewer, target=self.target)

        botch_without_functionary = CheckOutcomeFactory(
            name="IdentifyAction Botch No Functionary", success_level=-2
        )
        with force_check_outcome(botch_without_functionary):
            botch_result = self.action.run(actor=self.viewer, target=self.target)

        self.assertFalse(failure_result.success)
        self.assertFalse(botch_result.success)
        self.assertTrue(failure_result.message)
        self.assertEqual(failure_result.message, botch_result.message)
        self.assertFalse(PersonaDiscovery.objects.exists())


class GuessParsingTests(IdentifyActionTestCase):
    def test_guess_kwarg_reaches_the_service(self) -> None:
        failure = CheckOutcomeFactory(name="IdentifyAction Guess", success_level=-1)
        with force_check_outcome(failure) as capture:
            self.action.run(
                actor=self.viewer,
                target=self.target,
                guess=self.target_sheet.primary_persona.name,
            )
        # A correct guess eases target_difficulty below the unguessed baseline.
        with force_check_outcome(failure) as capture_unguessed:
            self.action.run(actor=self.viewer, target=self.target)

        self.assertLess(capture.target_difficulty, capture_unguessed.target_difficulty)

    def test_blank_guess_is_treated_as_no_guess(self) -> None:
        failure = CheckOutcomeFactory(name="IdentifyAction Blank Guess", success_level=-1)
        with force_check_outcome(failure) as capture_blank:
            self.action.run(actor=self.viewer, target=self.target, guess="   ")
        with force_check_outcome(failure) as capture_unguessed:
            self.action.run(actor=self.viewer, target=self.target)

        self.assertEqual(capture_blank.target_difficulty, capture_unguessed.target_difficulty)


class RestDispatchTargetResolutionTests(IdentifyActionTestCase):
    """The #2163 gotcha: REST dispatch sends ``target_persona_id`` (an int), not a resolved
    ``target`` ObjectDB. ``.run()`` must work when called that way, exactly like a real
    ``dispatch_player_action`` REGISTRY call would invoke it."""

    def test_run_resolves_target_from_raw_persona_id(self) -> None:
        presented_persona = self.mask
        success = CheckOutcomeFactory(name="IdentifyAction Persona Id", success_level=2)

        with force_check_outcome(success):
            result = self.action.run(actor=self.viewer, target_persona_id=presented_persona.pk)

        self.assertTrue(result.success)
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

    def test_run_with_unknown_persona_id_fails_cleanly(self) -> None:
        result = self.action.run(actor=self.viewer, target_persona_id=999999)

        self.assertFalse(result.success)
        self.assertIn("Identify whom", result.message)

    def test_run_resolves_target_from_raw_persona_id_under_the_target_kwarg(self) -> None:
        # #1107 Task 3 review, Minor finding 2: PersonaContextMenu's "Identify" item
        # dispatches `kwargs: { target: <persona pk> }` — the same shape
        # ChallengeAction's `_resolve_challenge_target` accepts (a raw persona pk under
        # `target`, not `target_persona_id`). `.run()` must resolve that shape too,
        # exactly like a real REST dispatch from the context menu would invoke it.
        presented_persona = self.mask
        success = CheckOutcomeFactory(name="IdentifyAction Target Kwarg Id", success_level=2)

        with force_check_outcome(success):
            result = self.action.run(actor=self.viewer, target=presented_persona.pk)

        self.assertTrue(result.success)
        self.assertEqual(PersonaDiscovery.objects.count(), 1)

    def test_run_with_unknown_persona_id_under_target_kwarg_fails_cleanly(self) -> None:
        result = self.action.run(actor=self.viewer, target=999999)

        self.assertFalse(result.success)
        self.assertIn("Identify whom", result.message)


class AttemptInteractionLoggingTests(IdentifyActionTestCase):
    def test_attempt_logs_an_outcome_blind_interaction_in_an_active_scene(self) -> None:
        SceneFactory(location=self.room, is_active=True)
        failure = CheckOutcomeFactory(name="IdentifyAction Attempt Log", success_level=-1)

        before = Interaction.objects.count()
        with force_check_outcome(failure):
            self.action.run(actor=self.viewer, target=self.target)

        self.assertEqual(Interaction.objects.count(), before + 1)
        interaction = Interaction.objects.latest("timestamp")
        self.assertNotIn(self.target_sheet.primary_persona.name, interaction.content)
        self.assertNotIn(self.mask.name, interaction.content)

    def test_no_active_scene_skips_logging_without_error(self) -> None:
        self.assertIsNone(get_active_scene(self.room))
        failure = CheckOutcomeFactory(name="IdentifyAction No Scene", success_level=-1)

        before = Interaction.objects.count()
        with force_check_outcome(failure):
            result = self.action.run(actor=self.viewer, target=self.target)

        self.assertFalse(result.success)
        self.assertEqual(Interaction.objects.count(), before)
