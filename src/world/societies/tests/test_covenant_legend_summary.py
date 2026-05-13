"""Tests for CovenantLegendSummary materialized view via get_covenant_legend_total."""

from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import refresh_legend_views
from world.societies.services import (
    create_legend_event,
    get_covenant_legend_total,
    spread_deed,
)


def _make_engaged_persona(covenants: list) -> object:
    """Create a Persona whose character is engaged with all given covenants."""
    persona = PersonaFactory()
    sheet = persona.character_sheet
    character = sheet.character
    for covenant in covenants:
        role = CovenantRoleFactory(covenant_type=covenant.covenant_type)
        membership = CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
            engaged=False,
        )
        membership.engaged = True
        membership.save()
    character.covenant_roles.invalidate()
    return persona


class CovenantLegendSummaryTests(TestCase):
    def test_total_grows_after_create_legend_event(self) -> None:
        """create_legend_event credits covenant → legend total reflects base_value."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        persona = _make_engaged_persona([covenant])
        source_type = LegendSourceTypeFactory()

        create_legend_event(
            title="A Great Battle",
            source_type=source_type,
            base_value=10,
            personas=[persona],
        )

        total = get_covenant_legend_total(covenant)
        self.assertEqual(total, 10)

    def test_total_includes_spreads(self) -> None:
        """Spreading a deed increases the covenant's legend total."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        persona = _make_engaged_persona([covenant])
        source_type = LegendSourceTypeFactory()
        spreader = PersonaFactory()

        _event, entries = create_legend_event(
            title="Heroic Stand",
            source_type=source_type,
            base_value=5,
            personas=[persona],
        )
        deed = entries[0]

        total_before = get_covenant_legend_total(covenant)
        self.assertEqual(total_before, 5)

        spread_deed(deed, spreader, value_added=3)
        # spread_deed calls refresh_legend_views internally
        total_after = get_covenant_legend_total(covenant)
        self.assertEqual(total_after, 8)

    def test_multiple_covenants_full_value_each(self) -> None:
        """Persona engaged with two covenants gets full value credited to each."""
        cov_durance = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_battle = CovenantFactory(covenant_type=CovenantType.BATTLE)
        persona = _make_engaged_persona([cov_durance, cov_battle])
        source_type = LegendSourceTypeFactory()

        create_legend_event(
            title="Epic Deed",
            source_type=source_type,
            base_value=10,
            personas=[persona],
        )

        durance_total = get_covenant_legend_total(cov_durance)
        battle_total = get_covenant_legend_total(cov_battle)
        self.assertEqual(durance_total, 10)
        self.assertEqual(battle_total, 10)

    def test_no_credits_returns_zero(self) -> None:
        """A covenant with no credited entries returns 0."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        # No entries created, no refresh needed
        refresh_legend_views()
        total = get_covenant_legend_total(covenant)
        self.assertEqual(total, 0)
