"""Tests for ``create_action_interaction`` and label renderers (Phase 3)."""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import (
    ClashFactory,
    ClashRoundFactory,
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.interaction_services import (
    create_action_interaction,
    render_action_declaration_label,
    render_clash_contribution_label,
)
from world.combat.models import ClashContribution
from world.magic.factories import FuryTierFactory, TechniqueFactory
from world.scenes.constants import InteractionMode
from world.scenes.factories import SceneFactory


class CreateActionInteractionTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_creates_action_mode_interaction(self) -> None:
        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Test Cast at Pyromancer",
        )

        self.assertEqual(interaction.mode, InteractionMode.ACTION)
        self.assertEqual(interaction.content, "Test Cast at Pyromancer")
        self.assertEqual(interaction.scene_id, self.scene.pk)
        self.assertEqual(interaction.persona, self.participant.character_sheet.primary_persona)

    def test_action_interaction_created(self) -> None:
        """Encounter with a scene produces an Interaction linked to that scene."""
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)

        interaction = create_action_interaction(
            participant=participant,
            round_number=1,
            summary_label="Cast",
        )
        self.assertIsNotNone(interaction.scene_id)


class RenderActionDeclarationLabelTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_with_opponent_target(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter, name="Pyromancer")
        technique = TechniqueFactory(name="Frost Bolt")
        action = CombatRoundActionFactory(
            participant=self.participant,
            focused_action=technique,
            focused_opponent_target=opponent,
        )
        self.assertEqual(render_action_declaration_label(action), "Frost Bolt at Pyromancer")

    def test_without_target(self) -> None:
        technique = TechniqueFactory(name="Self Buff")
        action = CombatRoundActionFactory(
            participant=self.participant,
            focused_action=technique,
            focused_opponent_target=None,
            focused_ally_target=None,
        )
        self.assertEqual(render_action_declaration_label(action), "Self Buff")

    def test_passives_only(self) -> None:
        action = CombatRoundActionFactory(
            participant=self.participant,
            focused_action=None,
        )
        self.assertEqual(render_action_declaration_label(action), "passives only")


class RenderClashContributionLabelTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)
        self.opponent = CombatOpponentFactory(encounter=self.encounter, name="Pyromancer")

    def test_label_includes_technique_flavor_opponent(self) -> None:
        clash = ClashFactory(
            encounter=self.encounter,
            npc_opponent=self.opponent,
            initiator=self.participant.character_sheet,
        )
        clash_round = ClashRoundFactory(clash=clash, round_number=1)
        technique = TechniqueFactory(name="Inferno Bolt")
        from world.traits.factories import CheckOutcomeFactory

        contribution = ClashContribution.objects.create(
            clash_round=clash_round,
            character=self.participant.character_sheet,
            action_slot="FOCUSED",
            anima_committed=2,
            technique=technique,
            check_outcome=CheckOutcomeFactory(),
            progress_delta=3,
            was_overburn=False,
            was_audere=False,
            soulfray_severity_accrued=0,
        )

        label = render_clash_contribution_label(contribution)
        self.assertIn("Inferno Bolt", label)
        self.assertIn("Pyromancer", label)


class CreateActionInteractionLegacyTests(TestCase):
    def test_no_primary_persona_returns_none(self) -> None:
        """If the participant's character sheet has no PRIMARY persona, return None.

        Legacy fixture content predating ``create_character_with_sheet`` may
        lack a PRIMARY persona. Rather than raise, we skip Interaction
        creation — the action still resolves; it just won't have a pose-log
        link.
        """
        encounter = CombatEncounterFactory()
        participant = CombatParticipantFactory(encounter=encounter)
        # Strip the invariant.
        participant.character_sheet.personas.all().delete()
        # Invalidate the cached_property on the sheet.
        participant.character_sheet.__dict__.pop("primary_persona", None)

        result = create_action_interaction(
            participant=participant,
            round_number=1,
            summary_label="Cast",
        )
        self.assertIsNone(result)


class CreateActionInteractionFuryAuditTests(TestCase):
    """create_action_interaction forwards fury_committed to the Interaction row."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_fury_committed_recorded_on_interaction(self) -> None:
        """fury_committed is stored on the resulting Interaction.fury_committed FK."""
        fury_tier = FuryTierFactory()

        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Fury Strike",
            fury_committed=fury_tier,
        )

        self.assertIsNotNone(interaction)
        interaction.refresh_from_db()
        self.assertEqual(
            interaction.fury_committed_id,
            fury_tier.pk,
            "Interaction.fury_committed must be the passed FuryTier.",
        )

    def test_fury_committed_none_by_default(self) -> None:
        """fury_committed defaults to None — existing callers unaffected."""
        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Normal Strike",
        )

        self.assertIsNotNone(interaction)
        interaction.refresh_from_db()
        self.assertIsNone(
            interaction.fury_committed_id,
            "Interaction.fury_committed must be None when not passed.",
        )
