"""RESEARCH resolution for MISSION-target clues (#3429) — the investigation's grant step.

Completing a research project against a MISSION clue grants the mission to every
distinct contributor via ``staff_assign_mission``; a contributor who already holds an
ACTIVE instance of the target mission is skipped without error, and a failed
resolution grants nothing.
"""

from django.test import TestCase

from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import Clue
from world.clues.research import contribute_research, resolve_research, start_research_project
from world.missions.constants import MissionStatus
from world.missions.factories import MissionNodeFactory, MissionTemplateFactory
from world.missions.models import MissionInstance
from world.missions.services.run import staff_assign_mission
from world.roster.factories import RosterEntryFactory
from world.traits.factories import CheckOutcomeFactory


def _make_template_with_entry():
    """A MissionTemplate with an entry node (required by ``staff_assign_mission``)."""
    template = MissionTemplateFactory()
    MissionNodeFactory(template=template, key="entry", is_entry=True)
    return template


class ResearchMissionTargetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.success = CheckOutcomeFactory(name="research_success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="research_failure", success_level=-1)
        cls.contributor_entry = RosterEntryFactory()
        cls.contributor_persona = cls.contributor_entry.character_sheet.primary_persona
        cls.second_entry = RosterEntryFactory()
        cls.second_persona = cls.second_entry.character_sheet.primary_persona

    def _project_for(self, template, *, extra_contributors=()):
        clue = Clue.objects.create(
            target_kind=ClueTargetKind.MISSION,
            target_mission=template,
            name="A Lead Worth Chasing",
            description="PLACEHOLDER",
            resolution_mode=ClueResolution.RESEARCH,
        )
        project = start_research_project(clue, self.contributor_persona)
        contribute_research(project, self.contributor_persona, self.success)
        for persona in extra_contributors:
            contribute_research(project, persona, self.success)
        return project, clue

    def test_success_grants_active_mission_instance_to_each_distinct_contributor(self):
        template = _make_template_with_entry()
        project, _clue = self._project_for(template, extra_contributors=[self.second_persona])

        resolve_research(project, self.success)

        for entry in (self.contributor_entry, self.second_entry):
            character = entry.character_sheet.character
            assert MissionInstance.objects.filter(
                template=template,
                status=MissionStatus.ACTIVE,
                participants__character_id=character.pk,
                participants__is_contract_holder=True,
            ).exists()

    def test_already_holding_contributor_is_skipped_without_error(self):
        template = _make_template_with_entry()
        character = self.contributor_entry.character_sheet.character
        existing = staff_assign_mission(template, character, persona=self.contributor_persona)
        project, _clue = self._project_for(template)

        resolve_research(project, self.success)  # must not raise

        instances = list(
            MissionInstance.objects.filter(
                template=template,
                participants__character_id=character.pk,
            )
        )
        assert instances == [existing]

    def test_failure_grants_nothing(self):
        template = _make_template_with_entry()
        project, _clue = self._project_for(template)

        resolve_research(project, self.failure)

        assert not MissionInstance.objects.filter(template=template).exists()
