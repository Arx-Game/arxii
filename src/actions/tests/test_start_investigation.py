"""StartInvestigationAction (#1825) — the research-lab door into the clue loop.

The first player-facing start surface for RESEARCH projects: standing at an active LAB,
holding a RESEARCH-mode clue (or physical crime evidence whose deed anchors a frame),
open the collaborative investigation project that `project/check` contributions advance.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import Clue
from world.clues.services import acquire_clue
from world.projects.constants import ProjectKind, ProjectStatus
from world.projects.models import Project
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory


class StartInvestigationActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.lab_room = RoomProfileFactory()
        lab_kind = RoomFeatureKindFactory(
            name="Lab", service_strategy=RoomFeatureServiceStrategy.LAB
        )
        RoomFeatureInstanceFactory(room_profile=cls.lab_room, feature_kind=lab_kind, level=1)
        cls.entry = RosterEntryFactory()
        cls.character = cls.entry.character_sheet.character
        cls.character.location = cls.lab_room.objectdb
        cls.character.save()
        cls.secret = SecretFactory(subject_sheet=CharacterSheetFactory())
        cls.clue = Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=cls.secret,
            name="Whispers That Don't Add Up",
            description="PLACEHOLDER",
            resolution_mode=ClueResolution.RESEARCH,
        )

    def test_start_with_held_clue_creates_the_research_project(self):
        from actions.definitions.investigation import StartInvestigationAction

        acquire_clue(self.entry, self.clue)
        result = StartInvestigationAction().run(self.character, clue_id=self.clue.pk)
        assert result.success
        project = Project.objects.get(kind=ProjectKind.RESEARCH)
        assert project.status == ProjectStatus.ACTIVE
        assert project.research_details.clue == self.clue

    def test_requires_holding_the_clue(self):
        from actions.definitions.investigation import StartInvestigationAction

        result = StartInvestigationAction().run(self.character, clue_id=self.clue.pk)
        assert not result.success
        assert not Project.objects.filter(kind=ProjectKind.RESEARCH).exists()

    def test_requires_an_active_lab(self):
        from actions.definitions.investigation import StartInvestigationAction

        acquire_clue(self.entry, self.clue)
        elsewhere = RoomProfileFactory()
        self.character.location = elsewhere.objectdb
        self.character.save()
        result = StartInvestigationAction().run(self.character, clue_id=self.clue.pk)
        assert not result.success

    def test_duplicate_active_project_is_refused(self):
        from actions.definitions.investigation import StartInvestigationAction

        acquire_clue(self.entry, self.clue)
        StartInvestigationAction().run(self.character, clue_id=self.clue.pk)
        result = StartInvestigationAction().run(self.character, clue_id=self.clue.pk)
        assert not result.success
        assert Project.objects.filter(kind=ProjectKind.RESEARCH).count() == 1

    def test_automatic_clue_cannot_be_project_started(self):
        from actions.definitions.investigation import StartInvestigationAction

        auto_clue = Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=SecretFactory(subject_sheet=CharacterSheetFactory()),
            name="Obvious Thing",
            description="PLACEHOLDER",
            resolution_mode=ClueResolution.AUTOMATIC,
        )
        acquire_clue(self.entry, auto_clue)
        result = StartInvestigationAction().run(self.character, clue_id=auto_clue.pk)
        assert not result.success

    def test_holding_frame_evidence_opens_the_investigation_directly(self):
        from actions.definitions.investigation import StartInvestigationAction
        from world.items.factories import ItemInstanceFactory
        from world.justice.constants import EvidenceState
        from world.justice.factories import CrimeEvidenceFactory, CrimeKindFactory
        from world.justice.services import record_accusation_crime

        evidence = CrimeEvidenceFactory(state=EvidenceState.PRODUCED)
        item = ItemInstanceFactory(holder_character_sheet=self.entry.character_sheet)
        evidence.item_instance = item
        evidence.save(update_fields=["item_instance"])
        record_accusation_crime(
            secret=self.secret,
            crime_kind=CrimeKindFactory(slug="theft", name="Theft"),
            real_deed=evidence.deed,
        )
        result = StartInvestigationAction().run(self.character, evidence_id=evidence.pk)
        assert result.success
        project = Project.objects.get(kind=ProjectKind.RESEARCH)
        assert project.research_details.clue == self.clue
        # Holding the evidence granted the clue itself along the way.
        from world.clues.models import CharacterClue

        assert CharacterClue.objects.filter(roster_entry=self.entry, clue=self.clue).exists()
