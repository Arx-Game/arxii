"""Nullification (#1825) — the investigation's payoff against a false accusation.

The accusation Secret STAYS (the claim was really made — resolved fork #1); nullification
(a) fully reverses the exposure's reputation damage, (b) zeroes the gossip heat,
(c) retracts the criminal claim (no further heat accrual; existing heat decays out), and
(d) makes the falseness a NEW discoverable fact: an ACTION_ANCHORED authorship secret
about the FRAMER, granted to no one, with its own (harder) hub counter-clue — the
author-unmask trail. Everything downstream (denounce/backfire) rides that second secret.
"""

from django.test import TestCase, tag

from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import AccusationCrimeClaim, AccusationNullification
from world.justice.nullification import nullify_accusation
from world.justice.services import (
    accrue_accusation_heat,
    record_accusation_crime,
)
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretProvenance
from world.secrets.factories import SecretFactory
from world.secrets.models import SecretGossip
from world.secrets.services import expose_secret
from world.societies.factories import (
    PhilosophicalArchetypeFactory,
    SocietyFactory,
)
from world.societies.models import SocietyReputation


@tag("postgres")  # unmask-clue hub placement walks the AreaClosure materialized view
class NullifyAccusationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory(mercy=3)
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.region = AreaFactory(level=AreaLevel.REGION, parent=cls.kingdom)
        cls.theft = CrimeKindFactory(slug="theft", name="Theft")
        AreaLawFactory(area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT)
        cls.subject = CharacterSheetFactory()
        cls.framer_entry = RosterEntryFactory()
        cls.framer_sheet = cls.framer_entry.character_sheet
        cls.archetype = PhilosophicalArchetypeFactory(mercy_delta=1)

    def _accusation(self, *, criminal: bool = True):
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACCUSATION,
            author_persona=self.framer_sheet.primary_persona,
        )
        secret.archetypes.add(self.archetype)
        expose_secret(secret, societies=[self.crown])
        SecretGossip.objects.create(secret=secret, region=self.region, heat=7)
        if criminal:
            record_accusation_crime(secret=secret, crime_kind=self.theft)
        return secret

    def _society_value(self):
        persona = self.subject.primary_persona
        row = SocietyReputation.objects.filter(persona=persona, society=self.crown).first()
        return row.value if row else 0

    def test_nullification_reverses_zeroes_and_retracts(self):
        secret = self._accusation()
        assert self._society_value() == 3
        record = nullify_accusation(secret)
        assert self._society_value() == 0
        gossip = SecretGossip.objects.get(secret=secret, region=self.region)
        assert gossip.heat == 0
        claim = AccusationCrimeClaim.objects.get(secret=secret)
        assert claim.retracted_at is not None
        assert record.secret == secret
        # A retracted claim accrues no further heat.
        assert accrue_accusation_heat(secret=secret, area=self.kingdom) is None

    def test_nullification_mints_the_authorship_secret_granted_to_no_one(self):
        from world.secrets.models import SecretKnowledge

        secret = self._accusation()
        record = nullify_accusation(secret)
        authorship = record.authorship_secret
        assert authorship is not None
        assert authorship.subject_sheet == self.framer_sheet
        assert authorship.provenance == SecretProvenance.ACTION_ANCHORED
        assert not SecretKnowledge.objects.filter(secret=authorship).exists()

    def test_nullification_is_idempotent(self):
        secret = self._accusation()
        first = nullify_accusation(secret)
        second = nullify_accusation(secret)
        assert first.pk == second.pk
        assert AccusationNullification.objects.filter(secret=secret).count() == 1
        # Reputation is compensated exactly once.
        assert self._society_value() == 0

    def test_anonymous_accusation_nullifies_without_authorship_secret(self):
        secret = SecretFactory(
            subject_sheet=self.subject,
            provenance=SecretProvenance.ACCUSATION,
            author_persona=None,
        )
        expose_secret(secret, societies=[self.crown])
        record = nullify_accusation(secret)
        assert record.authorship_secret is None

    def test_pure_smear_without_crime_claim_nullifies(self):
        secret = self._accusation(criminal=False)
        record = nullify_accusation(secret)
        assert record.pk is not None
        assert self._society_value() == 0
