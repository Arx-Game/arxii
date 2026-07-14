"""SmearAction (#1825) — the one-move L1 smear through the action seam."""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.traits.factories import CheckOutcomeFactory


@tag("postgres")  # hub/region resolution walks the AreaClosure materialized view
class SmearActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_social_check_content()
        cls.regular = CheckOutcomeFactory(name="smear_act_regular", success_level=1)
        cls.realm = RealmFactory()
        cls.region = AreaFactory(level=AreaLevel.REGION, realm=cls.realm)
        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.smearer_entry = RosterEntryFactory()
        cls.smearer = cls.smearer_entry.character_sheet.character
        cls.smearer.location = cls.hub.objectdb
        cls.smearer.save()
        gossip_spec = Specialization.objects.get(
            name="Gossip", parent_skill__trait__name="Persuasion"
        )
        CharacterSpecializationValueFactory(
            character=cls.smearer, specialization=gossip_spec, value=10
        )
        cls.target_sheet = CharacterSheetFactory()

    def test_smear_action_mints_via_plain_int_persona_kwarg(self):
        from actions.definitions.accusations import SmearAction
        from world.secrets.constants import SecretProvenance
        from world.secrets.models import Secret

        target_persona = self.target_sheet.primary_persona
        with force_check_outcome(self.regular):
            result = SmearAction().run(
                self.smearer,
                target_persona_id=target_persona.pk,
                content="They water the wine.",
            )
        assert result.success
        secret = Secret.objects.get(subject_sheet=self.target_sheet)
        assert secret.provenance == SecretProvenance.ACCUSATION

    def test_smear_action_is_registered(self):
        from actions.registry import ACTIONS_BY_KEY

        assert "smear_accusation" in ACTIONS_BY_KEY
