"""SINGLE_THRESHOLD projects resolve in the tick that completes them (#4325).

Before the fix ``scan_active_projects`` parked every non-tiered project in RESOLVING and
nothing ever called ``resolve_project`` for it, so a funded building never got built and a
finished investigation never revealed its clue. These tests run the real cron tick.
"""

import datetime

from django.test import TestCase
from django.utils import timezone

from world.buildings.factories import (
    BuildingFactory,
    BuildingKindFactory,
    BuildingRenovationDetailsFactory,
)
from world.buildings.renovation_services import complete_building_renovation
from world.clues.factories import ClueFactory
from world.clues.research import (
    contribute_research,
    resolve_research,
    start_research_project,
)
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.factories import ProjectFactory
from world.projects.services import register_kind_handler, scan_active_projects
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


def _expire(project) -> None:
    project.time_limit = timezone.now() - datetime.timedelta(seconds=1)
    project.save(update_fields=["time_limit"])


class SingleThresholdResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.success = CheckOutcomeFactory(name="Success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="Failure", success_level=-1)
        cls.roster = RosterEntryFactory()
        cls.persona = PersonaFactory(character_sheet=cls.roster.character_sheet)

    def setUp(self) -> None:
        # Other apps' tests clear the shared registry; re-register what we exercise.
        register_kind_handler(ProjectKind.RESEARCH, resolve_research)
        register_kind_handler(
            ProjectKind.BUILDING_RENOVATION, complete_building_renovation, success_only=True
        )

    def _research(self, *, progress_rolls: int):
        entry = CodexEntryFactory(learn_threshold=5)
        project = start_research_project(
            ClueFactory(target_codex_entry=entry), self.persona, threshold_target=5
        )
        for _ in range(progress_rolls):
            contribute_research(project, self.persona, CheckOutcomeFactory(success_level=3))
        return project, entry

    def _renovation(self, *, progress: int):
        building = BuildingFactory()
        target_kind = BuildingKindFactory(name="Occult Manor", is_occult=True)
        project = ProjectFactory(
            kind=ProjectKind.BUILDING_RENOVATION,
            status=ProjectStatus.ACTIVE,
            threshold_target=100,
            current_progress=progress,
        )
        BuildingRenovationDetailsFactory(
            project=project, building=building, target_kind=target_kind
        )
        return project, building, target_kind

    def test_funded_research_completes_and_reveals_the_clue(self) -> None:
        project, entry = self._research(progress_rolls=2)  # 6 >= 5

        scan_active_projects()

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(project.outcome_tier, self.success)
        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=self.roster, entry=entry)
        self.assertEqual(knowledge.status, CodexKnowledgeStatus.KNOWN)

    def test_expired_unfunded_research_fails_and_reveals_nothing(self) -> None:
        project, entry = self._research(progress_rolls=1)  # 3 < 5
        _expire(project)

        scan_active_projects()

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.FAILED)
        self.assertEqual(project.outcome_tier, self.failure)
        self.assertFalse(
            CharacterCodexKnowledge.objects.filter(roster_entry=self.roster, entry=entry).exists()
        )

    def test_funded_building_project_applies_its_effect(self) -> None:
        project, building, target_kind = self._renovation(progress=100)

        scan_active_projects()

        project.refresh_from_db()
        building.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(building.kind, target_kind)

    def test_expired_unfunded_building_project_fails_without_success_effect(self) -> None:
        project, building, target_kind = self._renovation(progress=10)
        original_kind = building.kind
        _expire(project)

        scan_active_projects()

        project.refresh_from_db()
        building.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.FAILED)
        self.assertEqual(building.kind, original_kind)
        self.assertNotEqual(building.kind, target_kind)

    def test_project_already_stranded_in_resolving_is_recovered(self) -> None:
        project, building, target_kind = self._renovation(progress=100)
        project.status = ProjectStatus.RESOLVING
        project.save(update_fields=["status"])

        scan_active_projects()

        project.refresh_from_db()
        building.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.COMPLETED)
        self.assertEqual(building.kind, target_kind)

    def test_stranded_unfunded_project_recovers_as_failed(self) -> None:
        project, building, _ = self._renovation(progress=10)
        original_kind = building.kind
        project.status = ProjectStatus.RESOLVING
        project.save(update_fields=["status"])

        scan_active_projects()

        project.refresh_from_db()
        building.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.FAILED)
        self.assertEqual(building.kind, original_kind)

    def test_kind_without_a_handler_is_left_resolving_and_does_not_crash(self) -> None:
        project = ProjectFactory(
            kind=ProjectKind.TEST_KIND, status=ProjectStatus.ACTIVE, current_progress=100
        )

        scan_active_projects()
        scan_active_projects()  # the recovery pass tolerates it on a later tick too

        project.refresh_from_db()
        self.assertEqual(project.status, ProjectStatus.RESOLVING)
