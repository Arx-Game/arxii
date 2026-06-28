"""Slice-4 end-to-end: Berserk rage blocks self-revert; RestoreSense unblocks it (#1111).

Proves the decoupled control invariant holds against the REAL Fury/Berserk +
RestoreSense system -- not a synthetic ``alters_behavior`` stand-in.

Tagged ``postgres`` because ``apply_condition(Berserk)`` hits the DISTINCT ON
path in ``conditions/services._build_bulk_context``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from evennia.objects.models import ObjectDB

from actions.constants import ResolutionPhase
from actions.definitions.forms import RevertFormAction, ShiftFormAction
from actions.definitions.social import RestoreSenseAction
from actions.types import PendingActionResolution, StepResult
from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckCategoryFactory, CheckTypeFactory
from world.conditions.services import apply_condition, has_condition
from world.forms.factories import (
    AlternateSelfFactory,
    CharacterFormFactory,
    CharacterFormStateFactory,
)
from world.forms.models import ActiveAlternateSelf, CharacterFormState, FormType
from world.magic.factories import (
    BerserkConditionTemplateFactory,
    RestoreToSenseActionTemplateFactory,
)
from world.scenes.constants import PersonaType
from world.scenes.factories import PersonaFactory


def _make_pending_resolution(*, success: bool = True) -> PendingActionResolution:
    """Minimal PendingActionResolution so the mocked check chain has a main_result."""
    check_result = MagicMock()
    check_result.success_level = 1 if success else -1
    check_result.outcome_name = "Success" if success else "Failure"
    check_result.outcome = None
    main_result = StepResult(step_label="main", check_result=check_result, consequence_id=None)
    return PendingActionResolution(
        template_id=1,
        character_id=1,
        target_difficulty=10,
        resolution_context_data={"character_id": 1, "challenge_instance_id": None},
        current_phase=ResolutionPhase.COMPLETE,
        main_result=main_result,
    )


@tag("postgres")
class AltSelfRageEndToEndTests(TestCase):
    """shift -> rage -> revert blocked -> calm-down -> revert unblocked."""

    @classmethod
    def setUpTestData(cls):
        cls.character: ObjectDB = CharacterFactory()
        cls.sheet = CharacterSheetFactory(character=cls.character)

        # True form + state so assume/revert have return anchors.
        cls.true_form = CharacterFormFactory(
            character=cls.character, name="True", form_type=FormType.TRUE
        )
        CharacterFormStateFactory(character=cls.character, active_form=cls.true_form)

        # Alternate persona to shift into.
        cls.alt_persona = PersonaFactory(
            character_sheet=cls.sheet,
            persona_type=PersonaType.ALTERNATE,
            name="the Beast",
        )
        cls.alt_self = AlternateSelfFactory(character=cls.sheet, persona=cls.alt_persona)

        # REAL Berserk condition + Restore-to-Sense calm-down action.
        cls.berserk = BerserkConditionTemplateFactory()
        cls.check_cat = CheckCategoryFactory(name="Social")
        cls.check_type = CheckTypeFactory(name="Willpower", category=cls.check_cat)
        RestoreToSenseActionTemplateFactory(check_type=cls.check_type)

    def setUp(self):
        self.accrue_patcher = patch("world.scenes.action_services.accrue")
        self.accrue_patcher.start()
        self.addCleanup(self.accrue_patcher.stop)

    @patch("actions.effects.conditions.perform_check")
    @patch("world.scenes.action_services.start_action_resolution")
    def test_revert_blocked_while_raging_unblocked_after_calm_down(
        self,
        mock_resolve: MagicMock,
        mock_check: MagicMock,
    ):
        """Full slice-4 lifecycle with the real Fury + RestoreSense system."""
        mock_check.return_value = MagicMock(success_level=1)
        mock_resolve.return_value = _make_pending_resolution(success=True)

        # 1. Shift into the alt-self -- NOT in_control-gated; succeeds.
        shift = ShiftFormAction().run(self.character, alternate_self_id=self.alt_self.pk)
        self.assertTrue(shift.success, shift.message)

        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.active_persona, self.alt_persona)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.alternate_self, self.alt_self)

        # 2. Apply the REAL Berserk condition (rage).
        result = apply_condition(
            self.character,
            self.berserk,
            severity=3,
            duration_rounds=3,
        )
        self.assertTrue(result.success, "apply_condition(Berserk) should succeed.")
        self.assertTrue(has_condition(self.character, self.berserk))
        self.assertFalse(self.character.sheet_data.in_control)

        # 3. Revert is BLOCKED while raging (the headline invariant).
        revert = RevertFormAction().run(self.character)
        self.assertFalse(revert.success, "revert_form must be blocked while raging.")
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertEqual(active.alternate_self, self.alt_self)

        # 4. Calm-down: RestoreSenseAction removes Berserk. Since #1603 a social
        # execute() returns an ActionResult wrapping the PendingActionResolution
        # in ``data["resolution"]``; assert the resolution completed (the calm-down
        # ran to done). We don't assert ``calm.success`` because the resolution's
        # main-check tier is a real roll here, and the behavioral guarantee we
        # care about is the Berserk removal below (driven by the live
        # ``RemoveConditionOnCheck`` effect, not the resolution tier).
        calm = RestoreSenseAction().run(self.character, target=self.character)
        self.assertEqual(calm.data["resolution"].current_phase, ResolutionPhase.COMPLETE)

        self.assertFalse(has_condition(self.character, self.berserk))
        # Assert on the ``sheet_data`` instance the action dispatched on. ``in_control``
        # is a plain property reading the character's ``CharacterConditionHandler``
        # cache, which ``remove_condition`` invalidated, so it re-derives fresh here
        # without any manual cache-pop.
        assert_sheet = self.character.sheet_data
        self.assertTrue(assert_sheet.in_control)

        # 5. Revert now SUCCEEDS (unblocked after the alters_behavior condition cleared).
        revert2 = RevertFormAction().run(self.character)
        self.assertTrue(revert2.success, revert2.message)

        state = CharacterFormState.objects.get(character=self.character)
        self.assertEqual(state.active_form, self.true_form)
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.active_persona, self.sheet.primary_persona)
        active = ActiveAlternateSelf.objects.get(character=self.sheet)
        self.assertIsNone(active.alternate_self)
