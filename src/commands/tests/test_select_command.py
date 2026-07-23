"""Tests for the select command (#2665)."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.combat.constants import OpponentTier, SelectionType
from world.combat.factories import (
    CombatEncounterFactory,
    CombatOpponentFactory,
    CombatParticipantFactory,
    CreatureTemplateFactory,
    PendingSelectionFactory,
)
from world.combat.models import PendingSelection
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantRoleFactory,
    WeaknessPoolEntryFactory,
)
from world.covenants.weakness import maybe_create_weakness_selection, resolve_weakness_selection
from world.magic.constants import TechniqueFunction
from world.magic.factories import TechniqueFactory, TechniqueFunctionTagFactory


class CmdSelectTests(TestCase):
    """Tests for the generic select command."""

    def setUp(self) -> None:
        self.encounter = CombatEncounterFactory(round_number=1)
        self.sheet = CharacterSheetFactory()
        self.participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=self.sheet,
        )
        self.template = CreatureTemplateFactory(tier=OpponentTier.BOSS)
        self.opponent = CombatOpponentFactory(
            encounter=self.encounter,
            tier=OpponentTier.BOSS,
            creature_template=self.template,
        )
        self.entry = WeaknessPoolEntryFactory(creature_template=self.template)
        # Set up the rider to create a pending selection
        self.technique = TechniqueFactory()
        TechniqueFunctionTagFactory(technique=self.technique, function=TechniqueFunction.PERCEPTION)
        self.role = CovenantRoleFactory(reveals_weakness=True)
        CharacterCovenantRoleFactory(
            character_sheet=self.sheet,
            covenant_role=self.role,
            engaged=True,
        )
        maybe_create_weakness_selection(self.sheet, self.technique, self.participant, self.opponent)

    def test_bare_select_lists_pending_selections(self) -> None:
        """Bare `select` lists the caller's unresolved PendingSelections."""
        selections = PendingSelection.objects.filter(
            participant__character_sheet=self.sheet,
            resolved_at__isnull=True,
        )
        assert selections.count() == 1
        sel = selections.first()
        assert sel.selection_type == SelectionType.WEAKNESS
        assert sel.options_json[0]["id"] == self.entry.name

    def test_select_resolves_by_name(self) -> None:
        """Resolving by name applies the condition."""
        sel = PendingSelection.objects.get(participant=self.participant)

        resolved = resolve_weakness_selection(sel, self.entry.name)

        assert resolved is True
        sel.refresh_from_db()
        assert sel.is_resolved
        assert sel.selected_option_id == self.entry.name

    def test_select_resolves_by_ordinal(self) -> None:
        """Resolving by ordinal number works."""
        sel = PendingSelection.objects.get(participant=self.participant)

        # The ordinal is 1 (first option)
        ordinal = 1
        chosen_id = sel.options_json[ordinal - 1]["id"]
        resolved = resolve_weakness_selection(sel, chosen_id)

        assert resolved is True

    def test_cannot_resolve_other_players_selection(self) -> None:
        """A selection belonging to another player cannot be resolved by this player."""
        other_sheet = CharacterSheetFactory()
        other_participant = CombatParticipantFactory(
            encounter=self.encounter,
            character_sheet=other_sheet,
        )
        # Create a selection for the other player
        PendingSelectionFactory(
            participant=other_participant,
            encounter=self.encounter,
        )

        # This player's selections should not include the other player's
        my_selections = PendingSelection.objects.filter(
            participant__character_sheet=self.sheet,
            resolved_at__isnull=True,
        )
        other_selections = PendingSelection.objects.filter(
            participant__character_sheet=other_sheet,
            resolved_at__isnull=True,
        )
        assert my_selections.count() == 1
        assert other_selections.count() == 1
        assert my_selections.first() != other_selections.first()

    def test_select_invalid_option(self) -> None:
        """Invalid option id → no resolution."""
        sel = PendingSelection.objects.get(participant=self.participant)

        resolved = resolve_weakness_selection(sel, "Nonexistent Weakness")

        assert resolved is False
        sel.refresh_from_db()
        assert not sel.is_resolved
