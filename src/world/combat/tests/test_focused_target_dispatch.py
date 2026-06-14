"""Tests for single-target focused-attack dispatch (#1001a).

The player dispatch carries the chosen focused target as ``focused_opponent_target_id``
(a ``CombatOpponent`` PK) or ``focused_ally_target_id`` (a ``CombatParticipant`` PK)
in the COMBAT dispatch ``kwargs``.  ``CombatRoundContext.record_declaration`` must
resolve those ids — scoped to the context's own encounter (forged-id safety) — into
model instances and persist them on the merged ``CombatRoundAction`` row, exactly as
``actions.player_interface`` drives the live path.

A pure-damage technique (``base_power``, no condition rows) REQUIRES a
``focused_opponent_target`` (``declare_action`` raises otherwise), so a successful
declaration of one proves the target threaded all the way through.
"""

import django.test

from actions.constants import ActionBackend
from actions.errors import ActionDispatchError
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.round_context import get_active_round_context
from actions.types import ActionRef, PlayerAction
from world.combat.constants import ActionCategory, EncounterStatus, ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
)
from world.combat.models import CombatRoundAction
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterTechniqueFactory,
    EffectTypeFactory,
    TechniqueFactory,
)
from world.vitals.models import CharacterVitals


def _damage_technique(category: str = ActionCategory.PHYSICAL) -> object:
    """A pure-damage technique: ``base_power`` set, no condition rows.

    ``declare_action`` requires a ``focused_opponent_target`` for these, so a
    successful focused declaration proves the dispatched target id threaded through.
    """
    technique = TechniqueFactory(damage_profile=False, action_category=category)
    technique.effect_type = EffectTypeFactory(base_power=10)
    technique.save()
    return technique


def _combat_player_action(technique: object) -> PlayerAction:
    ref = ActionRef(
        backend=ActionBackend.COMBAT,
        technique_id=technique.pk,  # type: ignore[attr-defined]
        action_slot="focused",
    )
    return PlayerAction(
        backend=ActionBackend.COMBAT,
        display_name="Test Focused Attack",
        ref=ref,
    )


class TestFocusedTargetRecordDeclaration(django.test.TestCase):
    """``record_declaration`` resolves focused target ids scoped to the encounter."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sheet = self.participant.character_sheet
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)
        ctx = get_active_round_context(self.sheet)
        assert ctx is not None
        self.ctx = ctx

    def _row(self) -> CombatRoundAction:
        row = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).first()
        assert row is not None
        return row

    def test_focused_opponent_target_id_persisted(self) -> None:
        """A damage technique with focused_opponent_target_id persists the opponent."""
        technique = _damage_technique()
        self.ctx.record_declaration(
            self.sheet,
            _combat_player_action(technique),
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.opponent.pk,
            },
        )
        row = self._row()
        self.assertEqual(row.focused_opponent_target_id, self.opponent.pk)

    def test_unknown_opponent_target_id_rejected(self) -> None:
        """An opponent id that does not resolve in this encounter is rejected."""
        technique = _damage_technique()
        with self.assertRaises(ActionDispatchError):
            self.ctx.record_declaration(
                self.sheet,
                _combat_player_action(technique),
                {
                    "effort_level": EffortLevel.MEDIUM,
                    "focused_opponent_target_id": 999_999,
                },
            )

    def test_opponent_target_id_from_other_encounter_rejected(self) -> None:
        """An opponent belonging to a different encounter must not be targetable."""
        other_encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        foreign_opponent = CombatOpponentFactory(encounter=other_encounter)
        technique = _damage_technique()
        with self.assertRaises(ActionDispatchError):
            self.ctx.record_declaration(
                self.sheet,
                _combat_player_action(technique),
                {
                    "effort_level": EffortLevel.MEDIUM,
                    "focused_opponent_target_id": foreign_opponent.pk,
                },
            )


class TestFocusedTargetEndToEnd(django.test.TestCase):
    """Drive the REAL ``dispatch_player_action`` entry point with a target id."""

    def setUp(self) -> None:
        from evennia.utils.idmapper import models as idmapper_models

        idmapper_models.flush_cache()

        self.encounter = CombatEncounterFactory(
            status=EncounterStatus.DECLARING,
            round_number=1,
        )
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            status=ParticipantStatus.ACTIVE,
        )
        self.sheet = self.participant.character_sheet
        self.character = self.sheet.character
        CharacterVitals.objects.create(
            character_sheet=self.sheet,
            health=100,
            max_health=100,
        )
        self.opponent = CombatOpponentFactory(encounter=self.encounter)

    def test_focused_opponent_target_threads_through_dispatch(self) -> None:
        """A targeted damage technique dispatched end-to-end persists the opponent."""
        technique = TechniqueFactory(damage_profile=False, action_category=ActionCategory.PHYSICAL)
        technique.effect_type = EffectTypeFactory(base_power=10)
        technique.action_template = ActionTemplateFactory()
        technique.save()
        CharacterTechniqueFactory(character=self.sheet, technique=technique)

        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
            action_slot="focused",
        )
        dispatch_player_action(
            self.character,
            ref,
            {
                "effort_level": EffortLevel.MEDIUM,
                "focused_opponent_target_id": self.opponent.pk,
            },
        )

        row = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        ).first()
        assert row is not None
        self.assertEqual(row.focused_opponent_target_id, self.opponent.pk)
