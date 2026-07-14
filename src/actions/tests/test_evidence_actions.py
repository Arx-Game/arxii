"""Evidence actions (#1825) — gather/dispose through the action seam.

REST-shape rule: these tests call ``.run()`` with plain int ``evidence_id`` kwargs
(never pre-resolved instances) to prove the web dispatch path works.
"""

from django.test import TestCase

from evennia_extensions.factories import RoomProfileFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.justice.constants import EvidenceState
from world.justice.factories import CrimeKindFactory
from world.justice.models import CrimeEvidence
from world.justice.services import tag_deed_crimes
from world.scenes.factories import SceneFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.security_checks import seed_security_check_content
from world.societies.factories import LegendEntryFactory
from world.traits.factories import CheckOutcomeFactory


class EvidenceActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_security_check_content()
        cls.success = CheckOutcomeFactory(name="ev_act_success", success_level=1)
        cls.room = RoomProfileFactory()
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.character.location = cls.room.objectdb
        cls.character.save()
        deed = LegendEntryFactory(scene=SceneFactory(location=cls.room.objectdb))
        tag_deed_crimes(deed, [CrimeKindFactory(slug="theft", name="Theft")])
        cls.evidence = CrimeEvidence.objects.get(deed=deed)

    def test_gather_action_with_plain_int_kwarg(self):
        from actions.definitions.evidence import GatherEvidenceAction

        with force_check_outcome(self.success):
            result = GatherEvidenceAction().run(self.character, evidence_id=self.evidence.pk)
        assert result.success
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.GATHERED

    def test_gather_action_unknown_id_fails_cleanly(self):
        from actions.definitions.evidence import GatherEvidenceAction

        result = GatherEvidenceAction().run(self.character, evidence_id=999999)
        assert not result.success

    def test_gather_action_guard_surfaces_user_message(self):
        from actions.definitions.evidence import GatherEvidenceAction

        elsewhere = RoomProfileFactory()
        self.character.location = elsewhere.objectdb
        self.character.save()
        result = GatherEvidenceAction().run(self.character, evidence_id=self.evidence.pk)
        assert not result.success
        assert "standing" in result.message

    def test_dispose_action_with_plain_int_kwarg(self):
        from actions.definitions.evidence import DisposeEvidenceAction, GatherEvidenceAction

        with force_check_outcome(self.success):
            GatherEvidenceAction().run(self.character, evidence_id=self.evidence.pk)
        with force_check_outcome(self.success):
            result = DisposeEvidenceAction().run(self.character, evidence_id=self.evidence.pk)
        assert result.success
        evidence = CrimeEvidence.objects.get(pk=self.evidence.pk)
        assert evidence.state == EvidenceState.DISPOSED

    def test_actions_are_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "gather_evidence" in ACTIONS_BY_KEY
        assert "dispose_evidence" in ACTIONS_BY_KEY
