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
            character=cls.character.sheet_data, specialization=cls.gossip_spec, value=10
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
            character=seeker_sheet, specialization=self.gossip_spec, value=10
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


@tag("postgres")  # hub/region resolution walks the AreaClosure materialized view (PG-only)
class SmearGossipTests(TestCase):
    """gossip smear (#1825) — mint an L1 accusation and seed its heat in one move."""

    @classmethod
    def setUpTestData(cls):
        from world.seeds.security_checks import seed_security_check_content

        seed_check_resolution_tables()
        seed_social_check_content()
        seed_security_check_content()
        cls.regular = CheckOutcomeFactory(name="smear_regular", success_level=1)
        cls.miss = CheckOutcomeFactory(name="smear_miss", success_level=-1)
        cls.realm = RealmFactory()
        cls.region = AreaFactory(level=AreaLevel.REGION, realm=cls.realm)
        cls.hub = RoomProfileFactory(area=cls.region, is_social_hub=True)
        cls.smearer_entry = RosterEntryFactory()
        cls.smearer_sheet = cls.smearer_entry.character_sheet
        cls.smearer = cls.smearer_sheet.character
        gossip_spec = Specialization.objects.get(
            name="Gossip", parent_skill__trait__name="Persuasion"
        )
        CharacterSpecializationValueFactory(
            character=cls.smearer_sheet, specialization=gossip_spec, value=10
        )
        cls.target_sheet = CharacterSheetFactory()  # tenure-less — always frameable

    def _room(self):
        return self.hub.objectdb

    def test_successful_smear_mints_seeds_and_places_the_counter_clue(self):
        from world.clues.models import RoomClue
        from world.secrets.constants import (
            SMEAR_CLUE_BASE_DIFFICULTY,
            SMEAR_CLUE_DIFFICULTY_PER_LEVEL,
            SecretProvenance,
        )
        from world.secrets.gossip import plant_smear
        from world.secrets.models import Secret

        with force_check_outcome(self.regular):
            result = plant_smear(
                self.smearer, self.target_sheet, "They water the wine.", room=self._room()
            )
        assert result.success is True
        secret = Secret.objects.get(pk=result.surfaced_secret_id)
        assert secret.provenance == SecretProvenance.ACCUSATION
        assert secret.level == SecretLevel.UNCOMMON_KNOWLEDGE
        assert secret.subject_sheet == self.target_sheet
        row = SecretGossip.objects.get(secret=secret, region=self.region)
        assert row.heat >= 1
        placement = RoomClue.objects.get(clue__target_secret=secret)
        assert placement.room_profile == self.hub
        expected = SMEAR_CLUE_BASE_DIFFICULTY + 1 * SMEAR_CLUE_DIFFICULTY_PER_LEVEL
        assert placement.detect_difficulty == expected

    def test_failed_check_mints_nothing(self):
        from world.secrets.gossip import plant_smear
        from world.secrets.models import Secret

        with force_check_outcome(self.miss):
            result = plant_smear(
                self.smearer, self.target_sheet, "They water the wine.", room=self._room()
            )
        assert result.success is False
        assert not Secret.objects.filter(subject_sheet=self.target_sheet).exists()

    def test_consent_blocked_target_cannot_be_smeared(self):
        from world.consent.constants import ConsentMode
        from world.consent.factories import (
            SocialConsentCategoryFactory,
            SocialConsentCategoryRuleFactory,
            SocialConsentPreferenceFactory,
        )
        from world.roster.factories import RosterTenureFactory
        from world.secrets.gossip import plant_smear

        tenure = RosterTenureFactory()
        hostile = SocialConsentCategoryFactory(key="hostile", default_mode=ConsentMode.EVERYONE)
        pref = SocialConsentPreferenceFactory(tenure=tenure)
        SocialConsentCategoryRuleFactory(
            preference=pref, category=hostile, mode=ConsentMode.ALLOWLIST
        )
        with self.assertRaises(GossipError):
            plant_smear(
                self.smearer,
                tenure.roster_entry.character_sheet,
                "A locked-down target.",
                room=self._room(),
            )

    def test_cannot_smear_yourself(self):
        from world.secrets.gossip import plant_smear

        with self.assertRaises(GossipError):
            plant_smear(self.smearer, self.smearer_sheet, "I am terrible.", room=self._room())
