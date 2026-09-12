"""Resolved mechanical actions record whom they were about (#3787 Task 5).

A hit's ``InteractionTargetPersona`` row is what lets the narrative-play reader
tell a player "this blow was yours to answer". PC personas only -- an NPC
opponent has no ``Persona``, so a blow that lands on one records no target,
which is correct (there is no player behind an NPC), not a gap.

Concealed outcomes are the other half of the pin: ``broadcast_action_outcome``'s
lower attribution tiers (``_emit_tier``'s vague/effect_only poses, ADR-0170)
must record ZERO target rows, or naming a target beside an unattributed line
would reopen the attribution the tier exists to withhold.
"""

from __future__ import annotations

from django.test import TestCase

from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentActionFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.combat.interaction_services import (
    broadcast_action_outcome,
    create_action_interaction,
    create_npc_action_interaction,
    personas_for_participants,
    target_persona_for_round_action,
)
from world.magic.services.cast_observation import CastAudience
from world.scenes.constants import InteractionMode
from world.scenes.factories import PersonaFactory, SceneFactory
from world.scenes.models import Interaction
from world.scenes.place_models import InteractionReceiver


def _target_persona_ids(interaction: Interaction) -> list[int]:
    return list(
        interaction.interaction_targets.values_list("persona_id", flat=True).order_by("persona_id")
    )


class CreateActionInteractionTargetTests(TestCase):
    """``create_action_interaction`` (the PC-action ACTION row)."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_targeting_an_ally_records_that_allys_persona(self) -> None:
        ally = CombatParticipantFactory(encounter=self.encounter)
        ally_persona = ally.character_sheet.primary_persona

        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Aid at ally",
            target_personas=[ally_persona],
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [ally_persona.pk])

    def test_targeting_an_npc_opponent_records_no_target(self) -> None:
        """An NPC opponent has no Persona -- correct, not a gap (brief)."""
        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Frost Bolt at Pyromancer",
            target_personas=None,
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [])

    def test_no_target_personas_kwarg_is_unaffected(self) -> None:
        """Every pre-existing caller that never passes target_personas keeps working."""
        interaction = create_action_interaction(
            participant=self.participant,
            round_number=1,
            summary_label="Guard Stance",
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [])


class TargetPersonaForRoundActionTests(TestCase):
    """``target_persona_for_round_action`` -- the CombatRoundAction resolver helper."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.participant = CombatParticipantFactory(encounter=self.encounter)

    def test_ally_target_resolves_to_that_allys_persona(self) -> None:
        ally = CombatParticipantFactory(encounter=self.encounter)
        action = CombatRoundActionFactory(participant=self.participant, focused_ally_target=ally)

        self.assertEqual(
            target_persona_for_round_action(action), ally.character_sheet.primary_persona
        )

    def test_opponent_target_resolves_to_none(self) -> None:
        opponent = CombatOpponentFactory(encounter=self.encounter, name="Pyromancer")
        action = CombatRoundActionFactory(
            participant=self.participant, focused_opponent_target=opponent
        )

        self.assertIsNone(target_persona_for_round_action(action))

    def test_no_target_resolves_to_none(self) -> None:
        action = CombatRoundActionFactory(participant=self.participant)

        self.assertIsNone(target_persona_for_round_action(action))


class PersonasForParticipantsTests(TestCase):
    """``personas_for_participants`` -- the batched NPC-action target resolver."""

    def test_resolves_every_participants_primary_persona(self) -> None:
        encounter = CombatEncounterFactory()
        one = CombatParticipantFactory(encounter=encounter)
        two = CombatParticipantFactory(encounter=encounter)

        personas = personas_for_participants([one, two])

        self.assertCountEqual(
            [p.pk for p in personas],
            [one.character_sheet.primary_persona.pk, two.character_sheet.primary_persona.pk],
        )

    def test_empty_participants_returns_empty_list(self) -> None:
        self.assertEqual(personas_for_participants([]), [])


class CreateNpcActionInteractionTargetTests(TestCase):
    """``create_npc_action_interaction`` -- a resolved NPC action that strikes PC(s)."""

    def setUp(self) -> None:
        super().setUp()
        self.encounter = CombatEncounterFactory()
        self.opponent = CombatOpponentFactory(encounter=self.encounter, name="Pyromancer")

    def test_striking_a_pc_records_that_pcs_persona(self) -> None:
        victim = CombatParticipantFactory(encounter=self.encounter)
        victim_persona = victim.character_sheet.primary_persona
        opponent_action = CombatOpponentActionFactory(opponent=self.opponent)

        interaction = create_npc_action_interaction(
            opponent_action=opponent_action,
            target_label=str(victim),
            target_personas=[victim_persona],
        )

        self.assertEqual(_target_persona_ids(interaction), [victim_persona.pk])

    def test_striking_multiple_pcs_records_every_one(self) -> None:
        victim_one = CombatParticipantFactory(encounter=self.encounter)
        victim_two = CombatParticipantFactory(encounter=self.encounter)
        victim_one_persona = victim_one.character_sheet.primary_persona
        victim_two_persona = victim_two.character_sheet.primary_persona
        personas = sorted([victim_one_persona.pk, victim_two_persona.pk])
        opponent_action = CombatOpponentActionFactory(opponent=self.opponent)

        interaction = create_npc_action_interaction(
            opponent_action=opponent_action,
            target_label="the party",
            target_personas=[
                victim_one.character_sheet.primary_persona,
                victim_two.character_sheet.primary_persona,
            ],
        )

        self.assertEqual(_target_persona_ids(interaction), personas)

    def test_no_target_personas_records_nothing(self) -> None:
        opponent_action = CombatOpponentActionFactory(opponent=self.opponent)

        interaction = create_npc_action_interaction(opponent_action=opponent_action)

        self.assertEqual(_target_persona_ids(interaction), [])


class BroadcastActionOutcomeTargetTests(TestCase):
    """``broadcast_action_outcome``'s OUTCOME row -- the reader's other anchor."""

    def setUp(self) -> None:
        super().setUp()
        self.scene = SceneFactory()
        self.encounter = CombatEncounterFactory(scene=self.scene)

    def test_hit_on_a_pc_records_that_pcs_persona(self) -> None:
        victim = CombatParticipantFactory(encounter=self.encounter)
        victim_persona = victim.character_sheet.primary_persona

        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Frost Bolt strikes Corvin for 24 damage.",
            target_personas=[victim_persona],
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [victim_persona.pk])

    def test_no_target_personas_records_nothing(self) -> None:
        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Corvin uses Guard Stance.",
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [])

    def test_battle_backed_location_less_encounter_still_records_a_target(self) -> None:
        """The genuine reachability conflict this task investigated (see task-5-report.md).

        A Battle-backed encounter's Scene is created with ``location=None``
        (``Battle.save()``, ``world/battles/models.py``). Routing target_personas
        through ``create_interaction``'s validated kwarg would raise
        ``UnreachableError`` here (the Narrator-writer has no location either, so
        the room-heard branch has nothing to test presence against) -- this test
        pins that ``broadcast_action_outcome`` does NOT do that, and a target is
        still recorded without touching ``persona_can_receive`` at all.
        """
        locationless_scene = SceneFactory(location=None)
        battle_encounter = CombatEncounterFactory(scene=locationless_scene, room=None)
        victim = CombatParticipantFactory(encounter=battle_encounter)
        victim_persona = victim.character_sheet.primary_persona

        interaction = broadcast_action_outcome(
            encounter=battle_encounter,
            narration="Ilyra's Frost Bolt strikes Corvin for 24 damage.",
            target_personas=[victim_persona],
        )

        assert interaction is not None
        self.assertEqual(_target_persona_ids(interaction), [victim_persona.pk])

    def test_concealed_lower_tiers_record_zero_target_rows(self) -> None:
        """ADR-0170 pin: a concealed outcome's vague/effect_only poses NEVER carry a target."""
        victim = CombatParticipantFactory(encounter=self.encounter)
        victim_persona = victim.character_sheet.primary_persona
        detector = PersonaFactory()
        marginal = PersonaFactory()
        oblivious = PersonaFactory()

        broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Whisper of Binding strikes Corvin for 24 damage.",
            audience=CastAudience(
                concealed=True,
                full=[detector],
                vague=[marginal],
                effect_only=[oblivious],
            ),
            unattributed_narration="Corvin is struck for 24 damage.",
            target_personas=[victim_persona],
        )

        outcomes = list(
            Interaction.objects.filter(scene=self.scene, mode=InteractionMode.OUTCOME).order_by(
                "pk"
            )
        )
        self.assertEqual(len(outcomes), 3, "one row per attribution tier")

        for outcome in outcomes:
            self.assertEqual(
                _target_persona_ids(outcome),
                [],
                "no OUTCOME row under a concealed audience may carry a target FK "
                "(ADR-0170) -- including the top (full-attribution) tier, since "
                "audience.full answers who could pin the CASTER, not who was hit",
            )

    def test_concealed_top_tier_receivers_are_untouched_by_the_target_skip(self) -> None:
        """Skipping target attachment under concealment must not also skip receivers."""
        victim = CombatParticipantFactory(encounter=self.encounter)
        victim_persona = victim.character_sheet.primary_persona
        detector = PersonaFactory()

        interaction = broadcast_action_outcome(
            encounter=self.encounter,
            narration="Ilyra's Whisper of Binding strikes Corvin for 24 damage.",
            audience=CastAudience(concealed=True, full=[detector], vague=[], effect_only=[]),
            target_personas=[victim_persona],
        )

        assert interaction is not None
        receiver_ids = list(
            InteractionReceiver.objects.filter(interaction=interaction).values_list(
                "persona_id", flat=True
            )
        )
        self.assertEqual(receiver_ids, [detector.pk])
        self.assertEqual(_target_persona_ids(interaction), [])
