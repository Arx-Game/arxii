"""Tests for slot-aware read-merge-write dispatch of focused + passive actions.

The frontend dispatches the focused action and each passive technique as SEPARATE
``/dispatch/`` calls — every one a ``{backend: COMBAT, technique_id, action_slot}``
``ActionRef``.  ``CombatRoundContext._record_combat_declaration`` must read-merge them
onto a single ``CombatRoundAction`` row by ``action_slot`` (raw wire strings:
``"focused"``, ``"passive-physical"``, ``"passive-social"``, ``"passive-mental"``)
instead of overwriting the row on every call.

These exercise the real dispatch path: a real ``PlayerAction`` carrying a real
``ActionRef`` (with ``action_slot`` set), driven through
``get_active_round_context(sheet).record_declaration(...)`` exactly as
``actions.player_interface`` drives it on the live dispatch path.
"""

import django.test

from actions.constants import ActionBackend
from actions.factories import ActionTemplateFactory
from actions.player_interface import dispatch_player_action
from actions.round_context import get_active_round_context
from actions.types import ActionRef, PlayerAction
from world.combat.constants import ActionCategory, EncounterStatus, ParticipantStatus
from world.combat.factories import CombatEncounterFactory, CombatParticipantFactory
from world.combat.models import CombatRoundAction
from world.fatigue.constants import EffortLevel
from world.magic.factories import (
    CharacterTechniqueFactory,
    EffectTypeFactory,
    TechniqueFactory,
)
from world.vitals.models import CharacterVitals


def _make_declaring_encounter_with_vitals() -> tuple:
    """Create a DECLARING encounter, ACTIVE participant, and ALIVE CharacterVitals."""
    encounter = CombatEncounterFactory(
        status=EncounterStatus.DECLARING,
        round_number=1,
    )
    participant = CombatParticipantFactory(
        encounter=encounter,
        status=ParticipantStatus.ACTIVE,
    )
    CharacterVitals.objects.create(
        character_sheet=participant.character_sheet,
        health=100,
        max_health=100,
    )
    return encounter, participant


def _make_no_target_technique(category: str) -> object:
    """A condition-free, base_power-less technique in ``category``.

    No damage profile and no condition rows means ``declare_action`` requires no
    focused target — so the technique can land in any slot freely.
    """
    technique = TechniqueFactory(damage_profile=False, action_category=category)
    technique.effect_type = EffectTypeFactory(base_power=None)
    technique.save()
    return technique


def _make_combat_player_action(technique: object, action_slot: str) -> PlayerAction:
    """Build a COMBAT PlayerAction whose ref names ``action_slot`` (raw wire string)."""
    ref = ActionRef(
        backend=ActionBackend.COMBAT,
        technique_id=technique.pk,  # type: ignore[attr-defined]
        action_slot=action_slot,
    )
    return PlayerAction(
        backend=ActionBackend.COMBAT,
        display_name="Test Combat Action",
        ref=ref,
    )


class TestPassiveDispatchReadMergeWrite(django.test.TestCase):
    """Focused + passives, dispatched separately, must coexist on one merged row."""

    def setUp(self) -> None:
        self.encounter, self.participant = _make_declaring_encounter_with_vitals()
        self.sheet = self.participant.character_sheet
        ctx = get_active_round_context(self.sheet)
        assert ctx is not None
        self.ctx = ctx

    def _dispatch(self, technique: object, action_slot: str) -> None:
        self.ctx.record_declaration(
            self.sheet,
            _make_combat_player_action(technique, action_slot),
            {"effort_level": EffortLevel.MEDIUM},
        )

    def _row(self) -> CombatRoundAction:
        rows = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        )
        self.assertEqual(rows.count(), 1, "expected exactly one merged CombatRoundAction row")
        row = rows.first()
        assert row is not None
        return row

    def test_focused_then_passives_coexist_on_one_row(self) -> None:
        """Dispatch focused (physical), then passive-social, then passive-mental.

        All three must land on ONE row — none clobbered by a later dispatch.
        """
        focused = _make_no_target_technique(ActionCategory.PHYSICAL)
        social = _make_no_target_technique(ActionCategory.SOCIAL)
        mental = _make_no_target_technique(ActionCategory.MENTAL)

        self._dispatch(focused, "focused")
        self._dispatch(social, "passive-social")
        self._dispatch(mental, "passive-mental")

        row = self._row()
        self.assertEqual(row.focused_action_id, focused.pk)
        self.assertEqual(row.social_passive_id, social.pk)
        self.assertEqual(row.mental_passive_id, mental.pk)

    def test_passive_before_focused_xor_enforced(self) -> None:
        """Passive-physical FIRST, then a physical-category focused → passive cleared.

        Proves backend XOR authority is independent of dispatch arrival order: the
        focused action wins and the colliding same-category passive is cleared, so
        ``_validate_passive_slot`` never raises.
        """
        passive = _make_no_target_technique(ActionCategory.PHYSICAL)
        focused = _make_no_target_technique(ActionCategory.PHYSICAL)

        self._dispatch(passive, "passive-physical")
        # Sanity: the passive landed first.
        self.assertEqual(self._row().physical_passive_id, passive.pk)

        self._dispatch(focused, "focused")

        row = self._row()
        self.assertEqual(row.focused_action_id, focused.pk)
        self.assertIsNone(row.physical_passive_id)


class TestPassiveDispatchEndToEnd(django.test.TestCase):
    """Drive the REAL ``dispatch_player_action`` entry point, not ``record_declaration``.

    The availability layer (`_combat_actions`) rebuilds each surfaced technique's
    ``ActionRef`` with ``technique_id`` only — dropping the client's ``action_slot``.
    ``_find_combat_player_action_for_ref`` then matches on ``technique_id`` and returns
    that slot-less ref, so without the fix every passive dispatch collapses to the
    FOCUSED slot (``ref.action_slot or FOCUSED``) and clobbers the focused action.

    This test reproduces that exact end-to-end path: it dispatches a focused technique
    then a passive-social technique through ``dispatch_player_action`` and asserts both
    land on the single merged ``CombatRoundAction`` row.
    """

    def setUp(self) -> None:
        # ObjectDB is not deepcopyable by setUpTestData; build per-test and flush the
        # SharedMemoryModel identity map (SQLite recycles PKs across the per-test rollback).
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

    def _surfaced_technique(self, category: str) -> object:
        """A combat-usable technique the character knows.

        It has an ``action_template`` (so ``_combat_actions`` surfaces it) and no
        damage profile / conditions (so no focused target is required), and is linked
        to the character sheet via ``CharacterTechnique`` so it is dispatchable.
        """
        technique = TechniqueFactory(damage_profile=False, action_category=category)
        technique.effect_type = EffectTypeFactory(base_power=None)
        technique.action_template = ActionTemplateFactory()
        technique.save()
        CharacterTechniqueFactory(character=self.sheet, technique=technique)
        return technique

    def _dispatch(self, technique: object, action_slot: str) -> None:
        ref = ActionRef(
            backend=ActionBackend.COMBAT,
            technique_id=technique.pk,
            action_slot=action_slot,
        )
        dispatch_player_action(self.character, ref, {"effort_level": EffortLevel.MEDIUM})

    def _row(self) -> CombatRoundAction:
        rows = CombatRoundAction.objects.filter(
            participant=self.participant,
            round_number=self.encounter.round_number,
        )
        self.assertEqual(rows.count(), 1, "expected exactly one merged CombatRoundAction row")
        row = rows.first()
        assert row is not None
        return row

    def test_focused_then_passive_coexist_through_real_dispatch(self) -> None:
        """Focused (physical) then passive-social via ``dispatch_player_action``.

        Both must land on one row: the passive must NOT overwrite the focused slot.
        """
        focused = self._surfaced_technique(ActionCategory.PHYSICAL)
        social = self._surfaced_technique(ActionCategory.SOCIAL)

        self._dispatch(focused, "focused")
        self._dispatch(social, "passive-social")

        row = self._row()
        self.assertEqual(row.focused_action_id, focused.pk)
        self.assertEqual(row.social_passive_id, social.pk)
