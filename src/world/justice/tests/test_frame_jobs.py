"""Frame jobs (#1825) — perverting real crime evidence into an anchored L3 accusation.

The heavy tier only ever grows from a real crime: gather its evidence, take it to a
Workshop of Iniquity, and open a frame-job Project advanced with Forgery checks. On a
successful completion the evidence is perverted: the anchored L3 accusation files
(``real_deed`` = the actual crime), heat lands where the crime happened, the tamper roll
becomes the counter-investigation's difficulty, and the evidence goes off-grid into the
case file. Consent against a PC patsy is checked at start AND re-checked at completion.
"""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.constants import ConsentMode
from world.consent.factories import (
    SocialConsentCategoryFactory,
    SocialConsentCategoryRuleFactory,
    SocialConsentPreferenceFactory,
)
from world.justice.constants import DEFAULT_HEAT_WEIGHT, EvidenceState
from world.justice.evidence import EvidenceError
from world.justice.factories import AreaLawFactory, CrimeKindFactory
from world.justice.frame_jobs import resolve_frame_job, start_frame_job
from world.justice.models import AccusationCrimeClaim, CrimeEvidence, PersonaHeat
from world.justice.services import tag_deed_crimes
from world.projects.constants import ProjectKind, ProjectStatus
from world.room_features.constants import RoomFeatureServiceStrategy
from world.room_features.factories import RoomFeatureInstanceFactory, RoomFeatureKindFactory
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory
from world.secrets.constants import SecretLevel, SecretProvenance
from world.secrets.models import Secret
from world.societies.factories import LegendEntryFactory, SocietyFactory
from world.traits.factories import CheckOutcomeFactory


class FrameJobFixture(TestCase):
    """A crime with gathered evidence, a workshop, and a framer standing in it."""

    @classmethod
    def setUpTestData(cls):
        cls.crown = SocietyFactory()
        cls.kingdom = AreaFactory(level=AreaLevel.KINGDOM, dominant_society=cls.crown)
        cls.theft = CrimeKindFactory(slug="theft", name="Theft")
        AreaLawFactory(area=cls.kingdom, crime_kind=cls.theft, heat_weight=DEFAULT_HEAT_WEIGHT)

        # The crime: a scened deed, tagged, evidence generated at the scene.
        cls.crime_room = RoomProfileFactory(area=cls.kingdom)
        cls.deed = LegendEntryFactory(scene=SceneFactory(location=cls.crime_room.objectdb))
        tag_deed_crimes(cls.deed, [cls.theft])
        cls.evidence = CrimeEvidence.objects.get(deed=cls.deed)

        # The framer, holding the gathered evidence, standing in a workshop.
        cls.framer_entry = RosterEntryFactory()
        cls.framer_sheet = cls.framer_entry.character_sheet
        cls.framer = cls.framer_sheet.character
        cls.workshop_room = RoomProfileFactory(area=cls.kingdom)
        workshop_kind = RoomFeatureKindFactory(
            name="Workshop of Iniquity",
            service_strategy=RoomFeatureServiceStrategy.WORKSHOP_OF_INIQUITY,
        )
        RoomFeatureInstanceFactory(
            room_profile=cls.workshop_room, feature_kind=workshop_kind, level=1
        )
        cls.framer.location = cls.workshop_room.objectdb
        cls.framer.save()

        from world.items.factories import ItemInstanceFactory

        item = ItemInstanceFactory(holder_character_sheet=cls.framer_sheet)
        cls.evidence.item_instance = item
        cls.evidence.state = EvidenceState.GATHERED
        cls.evidence.save(update_fields=["item_instance", "state"])

        cls.patsy_sheet = CharacterSheetFactory()  # tenure-less — always frameable
        cls.success = CheckOutcomeFactory(name="frame_success", success_level=1)
        cls.failure = CheckOutcomeFactory(name="frame_failure", success_level=-1)

    def _start(self, **overrides):
        kwargs = {
            "evidence": self.evidence,
            "subject_sheet": self.patsy_sheet,
            "crime_kind": self.theft,
            "content": "They did the deed — the evidence says so.",
        }
        kwargs.update(overrides)
        return start_frame_job(self.framer, **kwargs)


class StartFrameJobTests(FrameJobFixture):
    def test_start_creates_the_project_and_marks_tampering(self):
        project = self._start()
        assert project.kind == ProjectKind.FRAME_JOB
        assert project.status == ProjectStatus.ACTIVE
        details = project.frame_job_details
        assert details.evidence == self.evidence
        assert details.subject_sheet == self.patsy_sheet
        assert details.crime_kind == self.theft
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.TAMPERING

    def test_crime_kind_must_match_the_deed(self):
        smuggling = CrimeKindFactory(slug="smuggling", name="Smuggling")
        with self.assertRaises(EvidenceError):
            self._start(crime_kind=smuggling)

    def test_cannot_frame_the_actual_culprit(self):
        # Pinning the crime on the persona who actually did it isn't a frame.
        culprit_sheet = self.deed.persona.character_sheet
        with self.assertRaises(EvidenceError):
            self._start(subject_sheet=culprit_sheet)

    def test_cannot_frame_yourself(self):
        with self.assertRaises(EvidenceError):
            self._start(subject_sheet=self.framer_sheet)

    def test_requires_holding_gathered_evidence(self):
        self.evidence.state = EvidenceState.AT_SCENE
        self.evidence.save(update_fields=["state"])
        with self.assertRaises(EvidenceError):
            self._start()

    def test_requires_a_workshop_of_iniquity(self):
        self.framer.location = self.crime_room.objectdb
        self.framer.save()
        with self.assertRaises(EvidenceError):
            self._start()

    def test_consent_blocked_patsy_refuses_the_start(self):
        tenure = RosterTenureFactory()
        hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)
        pref = SocialConsentPreferenceFactory(tenure=tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=hostile, mode=ConsentMode.ALLOWLIST
        )
        with self.assertRaises(EvidenceError):
            self._start(subject_sheet=tenure.roster_entry.character_sheet)


@tag("postgres")  # completion places hub counter-clues (AreaClosure walk)
class ResolveFrameJobTests(FrameJobFixture):
    def test_successful_completion_files_the_anchored_frame(self):
        project = self._start()
        resolve_frame_job(project, self.success)

        secret = Secret.objects.get(subject_sheet=self.patsy_sheet)
        assert secret.provenance == SecretProvenance.ACCUSATION
        assert secret.level == SecretLevel.CAREFULLY_KEPT
        claim = AccusationCrimeClaim.objects.get(secret=secret)
        assert claim.real_deed == self.deed
        heat = PersonaHeat.objects.get(persona=self.patsy_sheet.primary_persona)
        assert heat.value == DEFAULT_HEAT_WEIGHT
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.OFF_GRID
        assert evidence.item_instance is None
        assert evidence.tamper_quality is not None
        assert evidence.tamper_quality > 0

    def test_failed_completion_restores_the_evidence(self):
        project = self._start()
        resolve_frame_job(project, self.failure)
        assert not Secret.objects.filter(subject_sheet=self.patsy_sheet).exists()
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.GATHERED
        assert evidence.item_instance is not None

    def test_consent_is_rechecked_at_completion(self):
        tenure = RosterTenureFactory()
        subject_sheet = tenure.roster_entry.character_sheet
        hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)
        project = self._start(subject_sheet=subject_sheet)
        # The patsy locks down between start and completion.
        pref = SocialConsentPreferenceFactory(tenure=tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=hostile, mode=ConsentMode.ALLOWLIST
        )
        resolve_frame_job(project, self.success)
        assert not Secret.objects.filter(subject_sheet=subject_sheet).exists()
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.GATHERED
