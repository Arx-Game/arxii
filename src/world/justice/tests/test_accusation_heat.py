"""Accusation → pursuit-heat bridge (#1825).

A player-authored criminal ACCUSATION (secrets #1825) bites the justice system,
not only reputation: an ``AccusationCrimeClaim`` links the false-scandal secret
to the crime it alleges, and ``accrue_accusation_heat`` lands heat on the
*subject* wherever the area's law criminalizes that crime — actorship is never
checked (false accusations are first-class, #1765). The tier is emergent: a wild
L2 names a crime with no real deed underneath; an L3 frame anchors a real deed
the subject did not commit.
"""

from django.test import TestCase

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import AccusationCrimeClaim, HeatSource, PersonaHeat
from world.justice.services import (
    accrue_accusation_heat,
    file_criminal_accusation,
    record_accusation_crime,
)
from world.secrets.constants import SecretLevel
from world.secrets.factories import SecretFactory
from world.secrets.models import Secret
from world.societies.factories import LegendEntryFactory, SocietyFactory


class AccusationHeatFixture:
    """A minimal one-kingdom jurisdiction where theft is criminal."""

    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.ward = AreaFactory(level=AreaLevel.WARD, parent=cls.kingdom)
        cls.theft = CrimeKindFactory(slug="theft", name="Theft")
        cls.kingdom_law = AreaLawFactory(
            area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT
        )


class RecordAccusationCrimeTests(AccusationHeatFixture, TestCase):
    def test_wild_claim_has_no_deed(self):
        secret = SecretFactory()
        claim = record_accusation_crime(secret=secret, crime_kind=self.theft)
        self.assertTrue(claim.is_wild)
        self.assertIsNone(claim.real_deed)

    def test_frame_claim_anchors_a_real_deed(self):
        secret = SecretFactory()
        deed = LegendEntryFactory()
        claim = record_accusation_crime(secret=secret, crime_kind=self.theft, real_deed=deed)
        self.assertFalse(claim.is_wild)
        self.assertEqual(claim.real_deed, deed)

    def test_record_is_idempotent_per_secret(self):
        # Re-recording updates the single claim rather than piling up rows.
        secret = SecretFactory()
        record_accusation_crime(secret=secret, crime_kind=self.theft)
        smuggling = CrimeKindFactory(slug="smuggling", name="Smuggling")
        record_accusation_crime(secret=secret, crime_kind=smuggling)
        self.assertEqual(AccusationCrimeClaim.objects.filter(secret=secret).count(), 1)
        self.assertEqual(secret.accusation_crime_claim.crime_kind, smuggling)


class AccrueAccusationHeatTests(AccusationHeatFixture, TestCase):
    def test_heat_lands_on_the_subject_where_the_crime_is_illegal(self):
        secret = SecretFactory()
        record_accusation_crime(secret=secret, crime_kind=self.theft)
        row = accrue_accusation_heat(secret=secret, area=self.ward)
        self.assertIsNotNone(row)
        self.assertEqual(row.persona, secret.subject_sheet.primary_persona)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT)
        self.assertEqual(row.society, self.crown)

    def test_no_claim_means_no_heat(self):
        secret = SecretFactory()
        self.assertIsNone(accrue_accusation_heat(secret=secret, area=self.ward))
        self.assertFalse(PersonaHeat.objects.exists())

    def test_wild_accusation_records_no_deed_on_the_heat_source(self):
        secret = SecretFactory()
        record_accusation_crime(secret=secret, crime_kind=self.theft)
        row = accrue_accusation_heat(secret=secret, area=self.ward)
        self.assertIsNone(HeatSource.objects.get(heat=row).deed)

    def test_frame_carries_the_real_deed_onto_the_heat_source(self):
        secret = SecretFactory()
        deed = LegendEntryFactory()
        record_accusation_crime(secret=secret, crime_kind=self.theft, real_deed=deed)
        row = accrue_accusation_heat(secret=secret, area=self.ward)
        self.assertEqual(HeatSource.objects.get(heat=row).deed, deed)

    def test_no_heat_where_the_crime_is_not_criminalized(self):
        # A wild accusation naming a crime the area's law doesn't recognize mints nothing.
        secret = SecretFactory()
        smuggling = CrimeKindFactory(slug="smuggling", name="Smuggling")
        record_accusation_crime(secret=secret, crime_kind=smuggling)
        self.assertIsNone(accrue_accusation_heat(secret=secret, area=self.ward))


class FileCriminalAccusationTests(AccusationHeatFixture, TestCase):
    def test_composes_mint_claim_and_heat_onto_the_framed_target(self):
        accuser = CharacterSheetFactory()
        target = CharacterSheetFactory()
        secret = file_criminal_accusation(
            accuser_persona=accuser.primary_persona,
            subject_sheet=target,
            content="They robbed the treasury.",
            crime_kind=self.theft,
            level=SecretLevel.WHISPERS,
            area=self.ward,
        )
        self.assertIsInstance(secret, Secret)
        self.assertEqual(secret.subject_sheet, target)
        self.assertEqual(secret.accusation_crime_claim.crime_kind, self.theft)
        # Heat lands on the framed target, never the accuser.
        row = PersonaHeat.objects.get(persona=target.primary_persona)
        self.assertEqual(row.value, DEFAULT_HEAT_WEIGHT)

    def test_without_area_records_the_claim_but_lands_no_heat(self):
        accuser = CharacterSheetFactory()
        target = CharacterSheetFactory()
        secret = file_criminal_accusation(
            accuser_persona=accuser.primary_persona,
            subject_sheet=target,
            content="They robbed the treasury.",
            crime_kind=self.theft,
        )
        self.assertTrue(AccusationCrimeClaim.objects.filter(secret=secret).exists())
        self.assertFalse(PersonaHeat.objects.exists())
