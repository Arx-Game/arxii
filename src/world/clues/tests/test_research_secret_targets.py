"""RESEARCH resolution for SECRET-target clues (#1825) — the investigation's grant step.

Completing a research project against a SECRET clue grants the secret's fact to every
contributor; when the secret is an ACCUSATION, completion additionally fires the
justice-side nullification (the counter-investigation's payoff).
"""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import Clue
from world.clues.research import contribute_research, resolve_research, start_research_project
from world.justice.models import AccusationNullification
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import SecretProvenance
from world.secrets.factories import SecretFactory
from world.secrets.models import SecretKnowledge
from world.traits.factories import CheckOutcomeFactory


class ResearchSecretTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.success = CheckOutcomeFactory(name="research_success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="research_failure", success_level=-1)
        cls.contributor_entry = RosterEntryFactory()
        cls.contributor_persona = cls.contributor_entry.character_sheet.primary_persona
        cls.subject = CharacterSheetFactory()

    def _project_for(self, secret):
        clue = Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=secret,
            name="Whispers That Don't Add Up",
            description="PLACEHOLDER",
            resolution_mode=ClueResolution.RESEARCH,
        )
        project = start_research_project(clue, self.contributor_persona)
        contribute_research(project, self.contributor_persona, self.success)
        return project

    def test_success_grants_the_secret_to_contributors(self):
        secret = SecretFactory(subject_sheet=self.subject)
        project = self._project_for(secret)
        resolve_research(project, self.success)
        assert SecretKnowledge.objects.filter(
            roster_entry=self.contributor_entry, secret=secret
        ).exists()

    def test_accusation_target_also_nullifies(self):
        secret = SecretFactory(subject_sheet=self.subject, provenance=SecretProvenance.ACCUSATION)
        project = self._project_for(secret)
        resolve_research(project, self.success)
        assert AccusationNullification.objects.filter(secret=secret).exists()

    def test_failure_grants_and_nullifies_nothing(self):
        secret = SecretFactory(subject_sheet=self.subject, provenance=SecretProvenance.ACCUSATION)
        project = self._project_for(secret)
        resolve_research(project, self.failure)
        assert not SecretKnowledge.objects.filter(secret=secret).exists()
        assert not AccusationNullification.objects.filter(secret=secret).exists()

    def test_plain_secret_target_does_not_touch_justice(self):
        secret = SecretFactory(subject_sheet=self.subject)
        project = self._project_for(secret)
        resolve_research(project, self.success)
        assert not AccusationNullification.objects.filter(secret=secret).exists()
