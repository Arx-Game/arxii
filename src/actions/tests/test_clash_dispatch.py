"""Dispatch tests for clash-contribution ActionRefs."""

from django.test import TestCase

from actions.player_interface import dispatch_player_action
from actions.types import ActionBackend, ActionRef
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ClashActionSlot, ClashStatus, EncounterStatus
from world.combat.factories import (
    ClashConfigFactory,
    ClashFactory,
    CombatEncounterFactory,
    CombatParticipantFactory,
)
from world.combat.models import ClashContributionDeclaration
from world.magic.factories import TechniqueFactory


class ClashContributionDispatchTests(TestCase):
    """The dispatch handler routes clash-bearing refs to declare_clash_contribution."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.config = ClashConfigFactory()

    def test_dispatch_writes_clash_contribution_declaration(self) -> None:
        encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(
            encounter=encounter,
            character_sheet=sheet,
        )
        clash = ClashFactory(encounter=encounter, status=ClashStatus.ACTIVE)
        technique = TechniqueFactory()

        # Clash ActionRef carries clash_id + clash_action_slot only.
        # technique_id lives in kwargs (the per-dispatch backend parameters),
        # not in the ref — ActionRef.__post_init__ disallows both being set
        # on a clash ref.
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            clash_id=clash.pk,
            clash_action_slot=ClashActionSlot.FOCUSED,
        )

        result = dispatch_player_action(
            character=participant.character_sheet.character,
            ref=ref,
            kwargs={
                "technique_id": technique.pk,
                "strain_commitment": 2,
            },
        )

        self.assertTrue(result.deferred)
        decl = ClashContributionDeclaration.objects.get(participant=participant, clash=clash)
        self.assertEqual(decl.technique_id, technique.pk)
        self.assertEqual(decl.strain_commitment, 2)
