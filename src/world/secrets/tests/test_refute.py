"""Refute-at-the-hub (#1825) — the consentless defense of an accusation's subject.

Anyone holding knowledge of an ACCUSATION secret may attack its credibility at a social
hub: a check against a level-scaled difficulty; success applies **compensating** reputation
calls (a partial reversal — nullification via investigation is the full clear) and records
the rebuttal (one attempt per refuter). No consent gate — defending the accused is open;
only turning it back on the *author* (denounce) is consent-gated (the Tom/Bob/Fred rule).
"""

from django.test import TestCase, tag

from world.character_sheets.factories import CharacterSheetFactory
from world.secrets.constants import SecretProvenance
from world.secrets.factories import SecretFactory, SecretVictimFactory
from world.secrets.services import expose_secret, reverse_secret_exposure
from world.societies.factories import (
    OrganizationFactory,
    PhilosophicalArchetypeFactory,
    SocietyFactory,
)
from world.societies.models import OrganizationReputation, SocietyReputation


class ReverseSecretExposureTests(TestCase):
    """The compensating-bump seam nullification and refutation share."""

    @classmethod
    def setUpTestData(cls):
        cls.subject = CharacterSheetFactory()
        cls.persona = cls.subject.primary_persona
        cls.society = SocietyFactory(mercy=3)
        cls.archetype = PhilosophicalArchetypeFactory(mercy_delta=1)  # dot product: +3
        cls.organization = OrganizationFactory()

    def _exposed_secret(self):
        secret = SecretFactory(subject_sheet=self.subject)
        secret.archetypes.add(self.archetype)
        SecretVictimFactory(secret=secret, organization=self.organization, severity=6)
        expose_secret(secret, societies=[self.society])
        return secret

    def _society_value(self):
        row = SocietyReputation.objects.filter(persona=self.persona, society=self.society).first()
        return row.value if row else 0

    def _org_value(self):
        row = OrganizationReputation.objects.filter(
            persona=self.persona, organization=self.organization
        ).first()
        return row.value if row else 0

    def test_full_reversal_restores_both_channels(self):
        secret = self._exposed_secret()
        assert self._society_value() == 3
        assert self._org_value() == -6
        reverse_secret_exposure(secret)
        assert self._society_value() == 0
        assert self._org_value() == 0

    def test_partial_reversal_scales_by_the_fraction(self):
        secret = self._exposed_secret()
        reverse_secret_exposure(secret, numerator=1, denominator=2)
        # +3 diffuse hit compensated by -(3//2)=1; -6 org hit compensated by +(6//2)=3.
        assert self._society_value() == 2
        assert self._org_value() == -3

    def test_unexposed_secret_reverses_nothing(self):
        secret = SecretFactory(subject_sheet=self.subject)
        secret.archetypes.add(self.archetype)
        reverse_secret_exposure(secret)
        assert self._society_value() == 0
        assert self._org_value() == 0


@tag("postgres")  # hub/region resolution walks the AreaClosure materialized view
class RefuteAccusationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from evennia_extensions.factories import RoomProfileFactory
        from world.areas.constants import AreaLevel
        from world.areas.factories import AreaFactory
        from world.character_creation.factories import RealmFactory
        from world.roster.factories import RosterEntryFactory
        from world.secrets.services import grant_secret_knowledge
        from world.seeds.checks import seed_check_resolution_tables
        from world.seeds.social_checks import seed_social_check_content
        from world.traits.factories import CheckOutcomeFactory

        seed_check_resolution_tables()
        seed_social_check_content()
        cls.success = CheckOutcomeFactory(name="refute_success", success_level=1)
        cls.miss = CheckOutcomeFactory(name="refute_miss", success_level=-1)
        cls.realm = RealmFactory()
        cls.region = AreaFactory(level=AreaLevel.REGION, realm=cls.realm)
        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)

        cls.subject = CharacterSheetFactory()
        cls.society = SocietyFactory(mercy=3)
        cls.archetype = PhilosophicalArchetypeFactory(mercy_delta=1)
        cls.secret = SecretFactory(
            subject_sheet=cls.subject, provenance=SecretProvenance.ACCUSATION
        )
        cls.secret.archetypes.add(cls.archetype)
        expose_secret(cls.secret, societies=[cls.society])

        cls.refuter_entry = RosterEntryFactory()
        cls.refuter = cls.refuter_entry.character_sheet.character
        grant_secret_knowledge(roster_entry=cls.refuter_entry, secret=cls.secret)

    def _room(self):
        return self.hub.objectdb

    def _society_value(self):
        persona = self.subject.primary_persona
        row = SocietyReputation.objects.filter(persona=persona, society=self.society).first()
        return row.value if row else 0

    def test_successful_refute_partially_restores_and_records(self):
        from world.checks.test_helpers import force_check_outcome
        from world.secrets.gossip import refute_accusation
        from world.secrets.models import AccusationRebuttal

        assert self._society_value() == 3
        with force_check_outcome(self.success) as capture:
            result = refute_accusation(self.refuter, self.secret, room=self._room())
        assert result.success is True
        assert capture.target_difficulty is not None
        assert capture.target_difficulty > 0
        # PLACEHOLDER half reversal: +3 hit compensated by -(3//2)=1.
        assert self._society_value() == 2
        rebuttal = AccusationRebuttal.objects.get(secret=self.secret)
        assert rebuttal.refuter_sheet == self.refuter_entry.character_sheet
        assert rebuttal.succeeded is True

    def test_failed_refute_records_the_spent_attempt(self):
        from world.checks.test_helpers import force_check_outcome
        from world.secrets.gossip import refute_accusation
        from world.secrets.models import AccusationRebuttal

        with force_check_outcome(self.miss):
            result = refute_accusation(self.refuter, self.secret, room=self._room())
        assert result.success is False
        assert self._society_value() == 3
        assert AccusationRebuttal.objects.get(secret=self.secret).succeeded is False

    def test_one_attempt_per_refuter(self):
        from world.checks.test_helpers import force_check_outcome
        from world.secrets.gossip import GossipError, refute_accusation

        with force_check_outcome(self.success):
            refute_accusation(self.refuter, self.secret, room=self._room())
        with self.assertRaises(GossipError):
            refute_accusation(self.refuter, self.secret, room=self._room())

    def test_requires_knowledge_of_the_accusation(self):
        from world.roster.factories import RosterEntryFactory
        from world.secrets.gossip import GossipError, refute_accusation

        stranger = RosterEntryFactory().character_sheet.character
        with self.assertRaises(GossipError):
            refute_accusation(stranger, self.secret, room=self._room())

    def test_only_accusations_can_be_refuted(self):
        from world.secrets.gossip import GossipError, refute_accusation
        from world.secrets.services import grant_secret_knowledge

        plain = SecretFactory(subject_sheet=self.subject)
        grant_secret_knowledge(roster_entry=self.refuter_entry, secret=plain)
        with self.assertRaises(GossipError):
            refute_accusation(self.refuter, plain, room=self._room())
