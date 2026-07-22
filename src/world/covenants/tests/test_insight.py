"""Tests for the #2645 Insight rider (``world.covenants.insight``).

Not ``setUpTestData`` — factories here create Evennia ``ObjectDB`` instances
(``DbHolder``, not deepcopyable) via ``CharacterSheetFactory``/
``CombatEncounterFactory``, same rationale as ``test_perk_announce.py``.
"""

from __future__ import annotations

from unittest import mock

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import ParticipantStatus
from world.combat.factories import (
    CombatEncounterFactory,
    CombatParticipantFactory,
    CombatRoundActionFactory,
)
from world.conditions.services import has_condition
from world.covenants.constants import InsightTargetKind
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleFactory,
    InsightTableEntryFactory,
    SubroleCovenantRoleFactory,
)
from world.covenants.insight import maybe_produce_insight
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory


class InsightRiderTests(TestCase):
    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        self.caster_sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.caster_sheet,
        )
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=self.technique, function=TechniqueFunction.PERCEPTION)
        self.role = CovenantRoleFactory(grants_insight=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.caster_sheet,
            covenant_role=self.role,
            engaged=True,
        )

    def test_fires_with_flagged_engaged_role_and_perception_tag_and_unused(self) -> None:
        entry = InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)

        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        self.participant.refresh_from_db()
        assert self.participant.insight_used is True
        assert has_condition(self.caster_sheet.character, entry.condition)

    def test_second_cast_same_encounter_returns_false(self) -> None:
        InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)

        first = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)
        second = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert first is True
        assert second is False

    def test_no_perception_tag_returns_false(self) -> None:
        InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)
        plain_technique = TechniqueFactory()

        fired = maybe_produce_insight(self.caster_sheet, plain_technique, self.participant)

        assert fired is False
        self.participant.refresh_from_db()
        assert self.participant.insight_used is False

    def test_no_engaged_insight_role_returns_false(self) -> None:
        InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)
        unflagged_sheet = CharacterSheetFactory()
        unflagged_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=unflagged_sheet,
        )

        fired = maybe_produce_insight(unflagged_sheet, self.technique, unflagged_participant)

        assert fired is False

    def test_sub_role_rides_parent_grant(self) -> None:
        """A sub-role whose parent grants_insight but the sub-role itself does not."""
        InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)
        parent = CovenantRoleFactory(grants_insight=True)
        sub_role = SubroleCovenantRoleFactory(parent_role=parent, grants_insight=False)
        sheet = CharacterSheetFactory()
        participant = CombatParticipantFactory(encounter=self.encounter, character_sheet=sheet)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant_role=sub_role,
            engaged=True,
        )

        fired = maybe_produce_insight(sheet, self.technique, participant)

        assert fired is True

    def test_no_active_entries_returns_false_silently(self) -> None:
        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is False
        self.participant.refresh_from_db()
        assert self.participant.insight_used is False

    def test_weighted_draw_respects_is_active(self) -> None:
        inactive_entry = InsightTableEntryFactory(
            target_kind=InsightTargetKind.SELF,
            weight=1000,
            is_active=False,
        )
        active_entry = InsightTableEntryFactory(
            target_kind=InsightTargetKind.SELF,
            weight=1,
            is_active=True,
        )

        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert has_condition(self.caster_sheet.character, active_entry.condition)
        assert not has_condition(self.caster_sheet.character, inactive_entry.condition)

    def test_team_applies_to_all_pc_side_active_participants(self) -> None:
        entry = InsightTableEntryFactory(target_kind=InsightTargetKind.TEAM)
        ally_sheet = CharacterSheetFactory()
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
            status=ParticipantStatus.ACTIVE,
        )
        fled_sheet = CharacterSheetFactory()
        CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=fled_sheet,
            status=ParticipantStatus.FLED,
        )

        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert has_condition(self.caster_sheet.character, entry.condition)
        assert has_condition(ally_sheet.character, entry.condition)
        assert not has_condition(fled_sheet.character, entry.condition)

    def test_ally_target_applies_when_declared(self) -> None:
        entry = InsightTableEntryFactory(target_kind=InsightTargetKind.ALLY)
        ally_sheet = CharacterSheetFactory()
        ally_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=ally_sheet,
        )
        CombatRoundActionFactory(
            participant=self.participant,
            round_number=self.encounter.round_number,
            focused_ally_target=ally_participant,
        )

        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert has_condition(ally_sheet.character, entry.condition)
        assert not has_condition(self.caster_sheet.character, entry.condition)

    def test_ally_falls_back_to_caster_when_no_ally_declared(self) -> None:
        entry = InsightTableEntryFactory(target_kind=InsightTargetKind.ALLY)

        fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert has_condition(self.caster_sheet.character, entry.condition)

    def test_announce_reaches_telnet_unmocked(self) -> None:
        """Real ``ObjectDB.msg_contents`` runs unmocked; only the listener's own
        ``.msg()`` is patched — mirrors #2536 slice-1's non-mocked location test.
        """
        InsightTableEntryFactory(
            target_kind=InsightTargetKind.SELF,
            prose="{caster} shares a vision with {target}!",
        )
        listener = CharacterFactory(location=self.encounter.room)

        with mock.patch.object(listener, "msg") as mock_msg:
            fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert mock_msg.call_count >= 1

    def test_announce_reaches_web_broadcast(self) -> None:
        InsightTableEntryFactory(target_kind=InsightTargetKind.SELF)

        with mock.patch(
            "world.scenes.interaction_services._broadcast_to_location"
        ) as mock_broadcast:
            fired = maybe_produce_insight(self.caster_sheet, self.technique, self.participant)

        assert fired is True
        assert mock_broadcast.call_count == 1
