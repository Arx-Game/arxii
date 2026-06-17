"""RESEARCH project kind (#1146) — contribute (floored), setback, resolve-grants-target."""

from django.test import TestCase

from world.clues.factories import ClueFactory
from world.clues.research import (
    apply_research_setback,
    apply_research_setbacks,
    contribute_research,
    resolve_research,
    start_research_project,
)
from world.codex.constants import CodexKnowledgeStatus
from world.codex.factories import CodexEntryFactory
from world.codex.models import CharacterCodexKnowledge
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.services import (
    get_kind_handler,
    register_kind_handler,
    resolve_project,
    scan_active_projects,
)
from world.roster.factories import RosterEntryFactory
from world.scenes.factories import PersonaFactory
from world.traits.factories import CheckOutcomeFactory


def _contributor():
    """A roster entry + a persona on its character sheet (so grants resolve back)."""
    roster = RosterEntryFactory()
    persona = PersonaFactory(character_sheet=roster.character_sheet)
    return roster, persona


class StartResearchProjectTests(TestCase):
    def test_creates_active_research_project_with_details(self) -> None:
        _, persona = _contributor()
        clue = ClueFactory()

        project = start_research_project(clue, persona, threshold_target=5)

        assert project.kind == ProjectKind.RESEARCH
        assert project.status == ProjectStatus.ACTIVE
        assert project.threshold_target == 5
        assert project.research_details.clue == clue


class ContributeResearchTests(TestCase):
    def test_success_adds_floored_progress(self) -> None:
        _, persona = _contributor()
        project = start_research_project(ClueFactory(), persona, threshold_target=20)

        added = contribute_research(project, persona, CheckOutcomeFactory(success_level=3))

        assert added == 3
        project.refresh_from_db()
        assert project.current_progress == 3

    def test_failure_adds_nothing_and_never_detracts(self) -> None:
        _, persona = _contributor()
        project = start_research_project(ClueFactory(), persona, threshold_target=20)
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))  # +3

        added = contribute_research(project, persona, CheckOutcomeFactory(success_level=-3))

        assert added == 0
        project.refresh_from_db()
        assert project.current_progress == 3  # the failed roll left it untouched


class ResearchSetbackTests(TestCase):
    def test_setback_floors_at_zero(self) -> None:
        _, persona = _contributor()
        project = start_research_project(ClueFactory(), persona, threshold_target=20)
        contribute_research(project, persona, CheckOutcomeFactory(success_level=2))  # +2

        removed = apply_research_setback(project, 5)

        assert removed == 2  # never below the floor
        project.refresh_from_db()
        assert project.current_progress == 0

    def test_weekly_sweep_sets_back_active_research(self) -> None:
        _, persona = _contributor()
        project = start_research_project(ClueFactory(), persona, threshold_target=20)
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))  # +3

        count = apply_research_setbacks(amount=1)

        assert count == 1
        project.refresh_from_db()
        assert project.current_progress == 2


class ResolveResearchTests(TestCase):
    def test_success_grants_codex_known_to_contributors(self) -> None:
        roster, persona = _contributor()
        entry = CodexEntryFactory(learn_threshold=5)
        project = start_research_project(ClueFactory(target_codex_entry=entry), persona)
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))

        resolve_research(project, CheckOutcomeFactory(success_level=3))

        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN

    def test_failure_grants_nothing(self) -> None:
        roster, persona = _contributor()
        entry = CodexEntryFactory(learn_threshold=5)
        project = start_research_project(ClueFactory(target_codex_entry=entry), persona)
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))

        resolve_research(project, CheckOutcomeFactory(success_level=-3))

        assert not CharacterCodexKnowledge.objects.filter(roster_entry=roster, entry=entry).exists()


class ResearchHandlerRegistrationTests(TestCase):
    def setUp(self) -> None:
        # CluesConfig.ready() registers this at startup, but other apps' tests clear the
        # shared kind-handler registry (projects' clear_kind_handlers) and run before
        # world.clues in a CI shard. Re-register so these tests verify the RESEARCH
        # wiring without depending on app-ready surviving cross-app test pollution.
        register_kind_handler(ProjectKind.RESEARCH, resolve_research)

    def test_research_handler_resolves_to_resolve_research(self) -> None:
        assert get_kind_handler(ProjectKind.RESEARCH) is resolve_research

    def test_end_to_end_scan_then_resolve_grants_the_target(self) -> None:
        roster, persona = _contributor()
        entry = CodexEntryFactory(learn_threshold=5)
        project = start_research_project(
            ClueFactory(target_codex_entry=entry), persona, threshold_target=5
        )
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))
        contribute_research(project, persona, CheckOutcomeFactory(success_level=3))  # 6 >= 5

        assert scan_active_projects() >= 1  # completion-ready → RESOLVING
        project.refresh_from_db()
        resolve_project(project, outcome_tier=CheckOutcomeFactory(success_level=3))

        project.refresh_from_db()
        assert project.status == ProjectStatus.COMPLETED
        knowledge = CharacterCodexKnowledge.objects.get(roster_entry=roster, entry=entry)
        assert knowledge.status == CodexKnowledgeStatus.KNOWN
