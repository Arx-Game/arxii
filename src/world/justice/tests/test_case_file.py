"""Case file (#1825) — produce filed frame evidence and physically examine it.

Filed frame evidence goes off-grid into the case file. An investigator with local
authority (a member of an organization under the enforcing society) may PRODUCE it —
re-materializing the item for scrutiny — and any holder may EXAMINE it: a Scrutinize
Evidence check against the framer's tamper craft. Only piloted characters do this;
nothing automated examines evidence. Unless someone contests the frame, it stands on
the framer's roll.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.clues.constants import ClueResolution, ClueTargetKind
from world.clues.models import CharacterClue, Clue
from world.justice.case_file import (
    examine_evidence,
    has_local_authority,
    produce_case_evidence,
)
from world.justice.constants import EvidenceState
from world.justice.evidence import EvidenceError
from world.justice.factories import CrimeEvidenceFactory, CrimeKindFactory
from world.justice.models import CrimeEvidence
from world.justice.services import record_accusation_crime
from world.justice.tests.utils import set_character_location
from world.roster.factories import RosterEntryFactory
from world.secrets.factories import SecretFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.security_checks import seed_security_check_content
from world.societies.factories import (
    OrganizationFactory,
    OrganizationMembershipFactory,
    SocietyFactory,
)
from world.traits.factories import CheckOutcomeFactory


class CaseFileFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_security_check_content()
        cls.success = CheckOutcomeFactory(name="case_success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="case_failure", success_level=-1)

        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.office_room = RoomProfileFactory(area=cls.kingdom)

        # The investigator: a member of a crown organization, standing in the office.
        cls.investigator_entry = RosterEntryFactory()
        cls.investigator_sheet = cls.investigator_entry.character_sheet
        cls.investigator = set_character_location(
            cls.investigator_sheet.character, cls.office_room.objectdb
        )
        crown_org = OrganizationFactory(society=cls.crown)
        OrganizationMembershipFactory(
            persona=cls.investigator_sheet.primary_persona, organization=crown_org
        )

        # A filed frame: off-grid evidence + the claim + the counter-clue.
        cls.evidence = CrimeEvidenceFactory(state=EvidenceState.OFF_GRID, tamper_quality=12)
        cls.subject = CharacterSheetFactory()
        cls.secret = SecretFactory(subject_sheet=cls.subject)
        record_accusation_crime(
            secret=cls.secret,
            crime_kind=CrimeKindFactory(slug="theft", name="Theft"),
            real_deed=cls.evidence.deed,
        )
        cls.counter_clue = Clue.objects.create(
            target_kind=ClueTargetKind.SECRET,
            target_secret=cls.secret,
            name="Whispers That Don't Add Up",
            description="PLACEHOLDER",
            resolution_mode=ClueResolution.RESEARCH,
        )


class HasLocalAuthorityTests(CaseFileFixture):
    def test_member_of_enforcing_society_org_has_authority(self):
        assert has_local_authority(self.investigator_sheet, self.office_room.objectdb)

    def test_unaffiliated_sheet_has_none(self):
        outsider = RosterEntryFactory().character_sheet
        assert not has_local_authority(outsider, self.office_room.objectdb)


class ProduceCaseEvidenceTests(CaseFileFixture):
    def test_authority_produces_the_evidence_for_examination(self):
        produced = produce_case_evidence(self.investigator, self.secret)
        assert produced.pk == self.evidence.pk
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.PRODUCED
        assert evidence.item_instance is not None
        assert evidence.item_instance.holder_character_sheet == self.investigator_sheet

    def test_no_authority_no_production(self):
        outsider_entry = RosterEntryFactory()
        outsider = set_character_location(
            outsider_entry.character_sheet.character, self.office_room.objectdb
        )
        with self.assertRaises(EvidenceError):
            produce_case_evidence(outsider, self.secret)

    def test_only_off_grid_evidence_can_be_produced(self):
        self.evidence.state = EvidenceState.DISPOSED
        self.evidence.save(update_fields=["state"])
        with self.assertRaises(EvidenceError):
            produce_case_evidence(self.investigator, self.secret)


class ExamineEvidenceTests(CaseFileFixture):
    def _produced(self):
        produce_case_evidence(self.investigator, self.secret)
        return CrimeEvidence.objects.get(pk=self.evidence.pk)

    def test_successful_examine_beats_the_tamper_roll_and_grants_the_lead(self):
        evidence = self._produced()
        with force_check_outcome(self.success) as capture:
            result = examine_evidence(self.investigator, evidence)
        assert result.success
        assert capture.target_difficulty == 12
        assert CharacterClue.objects.filter(
            roster_entry=self.investigator_entry, clue=self.counter_clue
        ).exists()

    def test_failed_examine_grants_nothing(self):
        evidence = self._produced()
        with force_check_outcome(self.failure):
            result = examine_evidence(self.investigator, evidence)
        assert not result.success
        assert not CharacterClue.objects.filter(
            roster_entry=self.investigator_entry, clue=self.counter_clue
        ).exists()

    def test_examine_requires_holding_the_evidence(self):
        evidence = self._produced()
        bystander = RosterEntryFactory().character_sheet.character
        with self.assertRaises(EvidenceError):
            examine_evidence(bystander, evidence)
