"""Tests for the #2665 weakness-reading rider (``world.covenants.weakness``).

Not ``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances
(``DbHolder``, not deepcopyable) via ``CharacterSheetFactory``/
``CombatEncounterFactory``, same rationale as ``test_insight.py``.
"""

from __future__ import annotations

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier, SelectionType
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
)
from world.combat.models import PendingSelection
from world.conditions.services import has_condition
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleFactory,
    SubroleCovenantRoleFactory,
    WeaknessPoolEntryFactory,
)
from world.covenants.weakness import maybe_create_weakness_selection, resolve_weakness_selection
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory


class WeaknessRiderTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        self.caster_sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.caster_sheet,
        )
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=self.technique, function=TechniqueFunction.PERCEPTION)
        self.role = CovenantRoleFactory(reveals_weakness=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.caster_sheet,
            covenant_role=self.role,
            engaged=True,
        )
        self.template = CreatureTemplateFactory(tier=OpponentTier.BOSS)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            creature_template=self.template,
        )

    def test_fires_with_flagged_engaged_role_and_boss_target_and_pool(self) -> None:
        entry = WeaknessPoolEntryFactory(creature_template=self.template)

        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )

        assert fired is True
        self.participant.refresh_from_db()
        assert self.participant.weakness_reading_used is True
        selection = PendingSelection.objects.get(participant=self.participant)
        assert selection.selection_type == SelectionType.WEAKNESS
        assert selection.target_opponent == self.opponent
        assert len(selection.options_json) == 1
        assert selection.options_json[0]["id"] == entry.name

    def test_second_cast_same_encounter_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)

        first = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )
        second = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )

        assert first is True
        assert second is False

    def test_no_perception_tag_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)
        plain_technique = TechniqueFactory()

        fired = maybe_create_weakness_selection(
            self.caster_sheet, plain_technique, self.participant, self.opponent
        )

        assert fired is False
        self.participant.refresh_from_db()
        assert self.participant.weakness_reading_used is False

    def test_no_engaged_weakness_role_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)
        unflagged_sheet = CharacterSheetFactory()
        unflagged_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=unflagged_sheet,
        )

        fired = maybe_create_weakness_selection(
            unflagged_sheet, self.technique, unflagged_participant, self.opponent
        )

        assert fired is False

    def test_non_boss_target_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)
        mook_opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.MOOK,
        )

        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, mook_opponent
        )

        assert fired is False

    def test_no_creature_template_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)
        boss_no_template = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            creature_template=None,
        )

        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, boss_no_template
        )

        assert fired is False

    def test_no_pool_entries_returns_false(self) -> None:
        """BOSS with template but no WeaknessPoolEntry rows → no fire."""
        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )

        assert fired is False
        self.participant.refresh_from_db()
        assert self.participant.weakness_reading_used is False

    def test_inactive_entries_excluded(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template, is_active=False)

        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )

        assert fired is False

    def test_sub_role_rides_parent_flag(self) -> None:
        """A sub-role whose parent reveals_weakness but the sub-role itself does not."""
        WeaknessPoolEntryFactory(creature_template=self.template)
        parent = CovenantRoleFactory(reveals_weakness=True)
        sub_role = SubroleCovenantRoleFactory(parent_role=parent, reveals_weakness=False)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant_role=sub_role,
            engaged=True,
        )

        fired = maybe_create_weakness_selection(sheet, self.technique, participant, self.opponent)

        assert fired is True

    def test_none_target_returns_false(self) -> None:
        WeaknessPoolEntryFactory(creature_template=self.template)

        fired = maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, None
        )

        assert fired is False


class ResolveWeaknessSelectionTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        self.caster_sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.caster_sheet,
        )
        self.template = CreatureTemplateFactory(tier=OpponentTier.BOSS)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            creature_template=self.template,
        )
        self.entry = WeaknessPoolEntryFactory(creature_template=self.template)
        # Create a pending selection via the rider
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=self.technique, function=TechniqueFunction.PERCEPTION)
        self.role = CovenantRoleFactory(reveals_weakness=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.caster_sheet,
            covenant_role=self.role,
            engaged=True,
        )
        maybe_create_weakness_selection(
            self.caster_sheet, self.technique, self.participant, self.opponent
        )
        self.selection = PendingSelection.objects.get(participant=self.participant)

    def test_resolves_and_applies_condition(self) -> None:
        resolved = resolve_weakness_selection(self.selection, self.entry.name)

        assert resolved is True
        self.selection.refresh_from_db()
        assert self.selection.is_resolved
        assert self.selection.selected_option_id == self.entry.name
        assert has_condition(self.opponent.objectdb, self.entry.condition)

    def test_idempotent(self) -> None:
        resolve_weakness_selection(self.selection, self.entry.name)

        second = resolve_weakness_selection(self.selection, self.entry.name)

        assert second is False

    def test_invalid_option_id_returns_false(self) -> None:
        resolved = resolve_weakness_selection(self.selection, "Nonexistent Weakness")

        assert resolved is False
        self.selection.refresh_from_db()
        assert not self.selection.is_resolved

    def test_completed_encounter_rejects(self) -> None:
        self.encounter.outcome = "victory"
        self.encounter.save()

        resolved = resolve_weakness_selection(self.selection, self.entry.name)

        assert resolved is False
