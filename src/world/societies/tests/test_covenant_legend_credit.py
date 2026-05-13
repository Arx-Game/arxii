"""Tests for CovenantLegendCredit model."""

from django.db import IntegrityError, transaction
from django.test import TestCase

from world.covenants.constants import CovenantType
from world.covenants.factories import (
    CharacterCovenantRoleFactory,
    CovenantFactory,
    CovenantRoleFactory,
)
from world.scenes.factories import PersonaFactory
from world.societies.factories import (
    CovenantLegendCreditFactory,
    LegendEntryFactory,
    LegendSourceTypeFactory,
)
from world.societies.models import CovenantLegendCredit
from world.societies.services import create_solo_deed, credit_engaged_covenants


class CovenantLegendCreditModelTests(TestCase):
    def test_unique_entry_covenant(self) -> None:
        entry = LegendEntryFactory()
        covenant = CovenantFactory()
        CovenantLegendCreditFactory(entry=entry, covenant=covenant)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CovenantLegendCredit.objects.create(entry=entry, covenant=covenant)

    def test_cascade_on_entry_delete(self) -> None:
        entry = LegendEntryFactory()
        covenant = CovenantFactory()
        credit = CovenantLegendCreditFactory(entry=entry, covenant=covenant)
        entry.delete()

        self.assertFalse(CovenantLegendCredit.objects.filter(pk=credit.pk).exists())


class CovenantLegendFanoutTests(TestCase):
    def _make_engaged_persona(self, covenants: list) -> object:
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

    def test_credit_engaged_covenants_creates_rows(self) -> None:
        """Persona engaged with two covenants → two credit rows."""
        cov_durance = CovenantFactory(covenant_type=CovenantType.DURANCE)
        cov_battle = CovenantFactory(covenant_type=CovenantType.BATTLE)
        persona = self._make_engaged_persona([cov_durance, cov_battle])
        entry = LegendEntryFactory(persona=persona)

        result = credit_engaged_covenants(entry=entry)

        self.assertEqual(len(result), 2)
        self.assertEqual(CovenantLegendCredit.objects.filter(entry=entry).count(), 2)
        credited_covenants = {c.covenant_id for c in result}
        self.assertIn(cov_durance.pk, credited_covenants)
        self.assertIn(cov_battle.pk, credited_covenants)

    def test_no_engaged_covenants_creates_zero_credits(self) -> None:
        """Persona not engaged with any covenant → zero credit rows."""
        persona = PersonaFactory()
        entry = LegendEntryFactory(persona=persona)

        result = credit_engaged_covenants(entry=entry)

        self.assertEqual(len(result), 0)
        self.assertEqual(CovenantLegendCredit.objects.filter(entry=entry).count(), 0)

    def test_disengaged_membership_not_credited(self) -> None:
        """engaged=False covenant should NOT be credited."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        persona = PersonaFactory()
        sheet = persona.character_sheet
        role = CovenantRoleFactory(covenant_type=CovenantType.DURANCE)
        # membership with engaged=False (the factory default)
        CharacterCovenantRoleFactory(
            character_sheet=sheet,
            covenant=covenant,
            covenant_role=role,
            engaged=False,
        )
        sheet.character.covenant_roles.invalidate()
        entry = LegendEntryFactory(persona=persona)

        result = credit_engaged_covenants(entry=entry)

        self.assertEqual(len(result), 0)

    def test_credit_engaged_covenants_is_idempotent(self) -> None:
        """Calling credit_engaged_covenants twice → still only one row per covenant."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        persona = self._make_engaged_persona([covenant])
        entry = LegendEntryFactory(persona=persona)

        credit_engaged_covenants(entry=entry)
        result = credit_engaged_covenants(entry=entry)

        self.assertEqual(len(result), 1)
        self.assertEqual(CovenantLegendCredit.objects.filter(entry=entry).count(), 1)

    def test_solo_deed_path_also_credits(self) -> None:
        """create_solo_deed → covenant credit fans out automatically."""
        covenant = CovenantFactory(covenant_type=CovenantType.DURANCE)
        persona = self._make_engaged_persona([covenant])
        source_type = LegendSourceTypeFactory()

        entry = create_solo_deed(
            persona=persona,
            title="A Great Deed",
            source_type=source_type,
            base_value=10,
        )

        self.assertEqual(CovenantLegendCredit.objects.filter(entry=entry).count(), 1)
        self.assertEqual(CovenantLegendCredit.objects.get(entry=entry).covenant_id, covenant.pk)
