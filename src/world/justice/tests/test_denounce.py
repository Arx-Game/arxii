"""Denounce the framer (#1825) — the consent-gated backfire.

Turning an unmasked frame back on its author is the one counter-play move that IS
consent-gated (the Tom/Bob/Fred rule): Fred — or anyone Bob's ``hostile`` category
admits — may expose the authorship secret at a hub, landing the framer's reputation
hit (the normal exposure engine) plus false-accusation pursuit heat scaled by the
original accusation's level. Tom, whom Bob never opted in for, cannot.
"""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.justice.constants import DEFAULT_HEAT_WEIGHT
from world.justice.denounce import DenounceError, denounce_framer
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.models import DenounceRecord, PersonaHeat
from world.justice.nullification import nullify_accusation
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.factories import SecretFactory
from world.secrets.services import grant_secret_knowledge


@tag("postgres")  # hub/region + society resolution walk the AreaClosure materialized view
class DenounceFramerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from world.societies.factories import SocietyFactory

        cls.realm = RealmFactory()
        cls.crown = SocietyFactory(realm=cls.realm)
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.region = AreaFactory(level=AreaLevel.REGION, parent=cls.kingdom, realm=cls.realm)
        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.false_accusation = CrimeKindFactory(slug="false-accusation", name="False Accusation")
        AreaLawFactory(
            area=cls.kingdom,
            crime_kind=cls.false_accusation,
            heat_weight=DEFAULT_HEAT_WEIGHT,
        )

        # Bob framed the subject at CAREFULLY_KEPT; the frame was nullified.
        cls.framer_tenure = RosterTenureFactory()
        cls.framer_sheet = cls.framer_tenure.roster_entry.character_sheet
        cls.subject = CharacterSheetFactory()
        cls.accusation = SecretFactory(
            subject_sheet=cls.subject,
            provenance=SecretProvenance.ACCUSATION,
            level=SecretLevel.CAREFULLY_KEPT,
            author_persona=cls.framer_sheet.primary_persona,
        )
        cls.hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)
        cls.record = nullify_accusation(cls.accusation)
        cls.authorship = cls.record.authorship_secret

        # Fred, who unmasked the framer.
        cls.denouncer_entry = RosterEntryFactory()
        cls.denouncer = cls.denouncer_entry.character_sheet.character
        grant_secret_knowledge(roster_entry=cls.denouncer_entry, secret=cls.authorship)

    def _room(self):
        return self.hub.objectdb

    def test_denounce_exposes_and_lands_level_scaled_heat(self):
        result = denounce_framer(self.denouncer, self.authorship, room=self._room())
        assert result.success
        assert self.crown in self.authorship.societies_exposed.all()
        heat = PersonaHeat.objects.get(persona=self.framer_sheet.primary_persona)
        assert heat.value == DEFAULT_HEAT_WEIGHT * int(SecretLevel.CAREFULLY_KEPT)
        assert DenounceRecord.objects.filter(
            authorship_secret=self.authorship,
            denouncer_sheet=self.denouncer_entry.character_sheet,
        ).exists()

    def test_consent_blocked_denouncer_is_refused(self):
        pref = SocialConsentPreferenceFactory(tenure=self.framer_tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=self.hostile, mode=ConsentMode.ALLOWLIST
        )
        with self.assertRaises(DenounceError):
            denounce_framer(self.denouncer, self.authorship, room=self._room())
        assert not PersonaHeat.objects.filter(persona=self.framer_sheet.primary_persona).exists()

    def test_requires_knowledge_of_the_authorship_secret(self):
        stranger = RosterEntryFactory().character_sheet.character
        with self.assertRaises(DenounceError):
            denounce_framer(stranger, self.authorship, room=self._room())

    def test_one_denounce_per_denouncer(self):
        denounce_framer(self.denouncer, self.authorship, room=self._room())
        with self.assertRaises(DenounceError):
            denounce_framer(self.denouncer, self.authorship, room=self._room())

    def test_only_nullification_authorship_secrets_can_be_denounced(self):
        plain = SecretFactory(subject_sheet=self.framer_sheet)
        grant_secret_knowledge(roster_entry=self.denouncer_entry, secret=plain)
        with self.assertRaises(DenounceError):
            denounce_framer(self.denouncer, plain, room=self._room())
