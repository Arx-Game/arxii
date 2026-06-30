"""Gossip — the regional Level-1-secret spread mechanic (#1572)."""

from django.test import TestCase, tag

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import GOSSIP_PUBLIC_THRESHOLD, SecretLevel
from world.secrets.factories import SecretFactory
from world.secrets.gossip import (
    GossipError,
    gossip_decay_tick,
    plant_gossip,
    seek_gossip,
    suppress_gossip,
)
from world.secrets.models import SecretGossip, SecretKnowledge
from world.seeds.checks import seed_check_resolution_tables
from world.seeds.social_checks import seed_social_check_content
from world.skills.factories import CharacterSpecializationValueFactory
from world.skills.models import Specialization
from world.societies.factories import SocietyFactory
from world.traits.factories import CheckOutcomeFactory


class GossipDecayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region = AreaFactory(level=AreaLevel.REGION)
        cls.secret = SecretFactory(level=SecretLevel.UNCOMMON_KNOWLEDGE)

    def test_decay_drops_heat_by_one(self):
        row = SecretGossip.objects.create(secret=self.secret, region=self.region, heat=5)
        gossip_decay_tick()
        SecretGossip.flush_instance_cache()  # bulk F() update bypasses the identity map
        assert SecretGossip.objects.get(pk=row.pk).heat == 4

    def test_decay_floors_at_one(self):
        # Once gossiped, a secret lingers findable — only suppression reaches 0.
        row = SecretGossip.objects.create(secret=self.secret, region=self.region, heat=1)
        gossip_decay_tick()
        SecretGossip.flush_instance_cache()
        assert SecretGossip.objects.get(pk=row.pk).heat == 1


@tag("postgres")  # region resolution walks the AreaClosure materialized view (PG-only)
class GossipActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_social_check_content()
        cls.special = CheckOutcomeFactory(name="gossip_special", success_level=2)
        cls.regular = CheckOutcomeFactory(name="gossip_regular", success_level=1)
        cls.realm = RealmFactory()
        cls.region = AreaFactory(level=AreaLevel.REGION, realm=cls.realm)
        cls.society = SocietyFactory(realm=cls.realm)
        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.sheet = CharacterSheetFactory()
        cls.character = cls.sheet.character
        cls.gossip_spec = Specialization.objects.get(
            name="Gossip", parent_skill__trait__name="Persuasion"
        )
        CharacterSpecializationValueFactory(
            character=cls.character, specialization=cls.gossip_spec, value=10
        )
        # A self-secret (you may always spread gossip about yourself).
        cls.secret = SecretFactory(subject_sheet=cls.sheet, level=SecretLevel.UNCOMMON_KNOWLEDGE)

    def _room(self):
        return self.hub.objectdb

    def test_plant_special_success_adds_two_heat(self):
        with force_check_outcome(self.special):
            result = plant_gossip(self.character, self.secret, room=self._room())
        assert result.heat == 2
        assert SecretGossip.objects.get(secret=self.secret, region=self.region).heat == 2

    def test_plant_regular_success_adds_one_heat(self):
        with force_check_outcome(self.regular):
            result = plant_gossip(self.character, self.secret, room=self._room())
        assert result.heat == 1

    def test_plant_requires_gossip_skill(self):
        bare = CharacterSheetFactory()
        secret = SecretFactory(subject_sheet=bare, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        with self.assertRaises(GossipError):
            plant_gossip(bare.character, secret, room=self._room())

    def test_plant_requires_a_social_hub(self):
        non_hub = RoomProfileFactory(area=self.region, is_social_hub=False)
        with self.assertRaises(GossipError):
            plant_gossip(self.character, self.secret, room=non_hub.objectdb)

    def test_cannot_plant_a_secret_you_do_not_hold(self):
        # A secret about someone else, which the gossiper hasn't learned.
        other = CharacterSheetFactory()
        secret = SecretFactory(subject_sheet=other, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        with force_check_outcome(self.special), self.assertRaises(GossipError):
            plant_gossip(self.character, secret, room=self._room())

    def test_planting_past_the_threshold_goes_public_and_exposes_region_societies(self):
        SecretGossip.objects.create(
            secret=self.secret, region=self.region, heat=GOSSIP_PUBLIC_THRESHOLD - 1
        )
        with force_check_outcome(self.special):
            result = plant_gossip(self.character, self.secret, room=self._room())
        assert result.went_public is True
        assert self.society in self.secret.societies_exposed.all()

    def test_seek_surfaces_a_hot_secret_and_grants_the_fact(self):
        seeker_sheet = CharacterSheetFactory()
        seeker = seeker_sheet.character
        CharacterSpecializationValueFactory(
            character=seeker, specialization=self.gossip_spec, value=10
        )
        entry = RosterEntryFactory(character_sheet=seeker_sheet)
        target = CharacterSheetFactory()
        hot = SecretFactory(subject_sheet=target, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        SecretGossip.objects.create(secret=hot, region=self.region, heat=5)
        with force_check_outcome(self.regular):
            result = seek_gossip(seeker, room=self._room())
        assert result.success is True
        assert result.surfaced_secret_id == hot.pk
        held = SecretKnowledge.objects.get(roster_entry=entry, secret=hot)
        assert held.knows_category is False  # fact-only — never leaks deeper layers
        assert held.knows_consequences is False

    def test_suppress_lowers_heat(self):
        SecretGossip.objects.create(secret=self.secret, region=self.region, heat=5)
        with force_check_outcome(self.special):
            result = suppress_gossip(self.character, self.secret, room=self._room())
        assert result.heat == 3  # special suppress removes 2
