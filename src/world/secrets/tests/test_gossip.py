"""Gossip — Level-1-secret spread that climbs the area ladder on its heat (#1572, #4085).

The fixtures are one small tree with no Region anywhere:

    county > barony > ward_a > neighborhood_a1 (hub_a1), neighborhood_a2 (hub_a2)
                    > ward_b > neighborhood_b1 (hub_b1)

Nothing here walks the ``AreaClosure`` matview (reach is a parent walk), so the whole
module runs on the SQLite tier.
"""

from django.test import TestCase, override_settings

from evennia_extensions.factories import RoomProfileFactory
from world.areas.constants import AreaLevel
from world.areas.factories import AreaFactory
from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.test_helpers import force_check_outcome
from world.roster.factories import RosterEntryFactory
from world.secrets.constants import (
    GOSSIP_CLIMB_THRESHOLDS,
    GOSSIP_DECAY_FLOOR,
    GOSSIP_PUBLIC_THRESHOLD,
    SecretLevel,
)
from world.secrets.factories import SecretFactory
from world.secrets.gossip import (
    GossipError,
    climb_gossip,
    gossip_decay_tick,
    heat_for,
    plant_gossip,
    public_gossip_lines,
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


def build_tree(realm):
    """The module's tree; every area on the realm so a public rumor has societies to reach."""
    county = AreaFactory(name="County", level=AreaLevel.COUNTY, realm=realm)
    barony = AreaFactory(name="Barony", level=AreaLevel.BARONY, parent=county, realm=realm)
    ward_a = AreaFactory(name="Ward A", level=AreaLevel.WARD, parent=barony, realm=realm)
    ward_b = AreaFactory(name="Ward B", level=AreaLevel.WARD, parent=barony, realm=realm)
    a1 = AreaFactory(name="A1", level=AreaLevel.NEIGHBORHOOD, parent=ward_a, realm=realm)
    a2 = AreaFactory(name="A2", level=AreaLevel.NEIGHBORHOOD, parent=ward_a, realm=realm)
    b1 = AreaFactory(name="B1", level=AreaLevel.NEIGHBORHOOD, parent=ward_b, realm=realm)
    return {
        "county": county,
        "barony": barony,
        "ward_a": ward_a,
        "ward_b": ward_b,
        "a1": a1,
        "a2": a2,
        "b1": b1,
    }


class GossipDecayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.area = AreaFactory(level=AreaLevel.WARD)
        cls.secret = SecretFactory(level=SecretLevel.UNCOMMON_KNOWLEDGE)

    def test_decay_drops_heat_by_one(self):
        row = SecretGossip.objects.create(secret=self.secret, area=self.area, heat=5)
        gossip_decay_tick()
        SecretGossip.flush_instance_cache()  # bulk F() update bypasses the identity map
        assert SecretGossip.objects.get(pk=row.pk).heat == 4

    def test_decay_floors_at_one_and_never_lowers_the_reach(self):
        # Once gossiped, a secret lingers findable — only suppression reaches 0 (#4085: high
        # water mark — the reach stays where the heat once carried it).
        row = SecretGossip.objects.create(
            secret=self.secret, area=self.area, heat=GOSSIP_DECAY_FLOOR
        )
        gossip_decay_tick()
        SecretGossip.flush_instance_cache()
        fresh = SecretGossip.objects.get(pk=row.pk)
        assert fresh.heat == GOSSIP_DECAY_FLOOR
        assert fresh.area_id == self.area.pk


class ClimbTests(TestCase):
    """``climb_gossip``: one rung per threshold, merge at a shared ancestor, never down."""

    @classmethod
    def setUpTestData(cls):
        cls.tree = build_tree(RealmFactory())
        cls.secret = SecretFactory(level=SecretLevel.UNCOMMON_KNOWLEDGE)

    def test_climbs_as_many_rungs_as_the_heat_clears(self):
        row = SecretGossip.objects.create(
            secret=self.secret,
            area=self.tree["a1"],
            heat=GOSSIP_CLIMB_THRESHOLDS[AreaLevel.BARONY],
        )
        row = climb_gossip(row)
        assert row.area_id == self.tree["barony"].pk

    def test_stays_put_below_the_next_threshold(self):
        row = SecretGossip.objects.create(
            secret=self.secret,
            area=self.tree["a1"],
            heat=GOSSIP_CLIMB_THRESHOLDS[AreaLevel.WARD] - 1,
        )
        assert climb_gossip(row).area_id == self.tree["a1"].pk

    def test_two_plantings_merge_when_they_meet(self):
        ward_threshold = GOSSIP_CLIMB_THRESHOLDS[AreaLevel.WARD]
        already_there = SecretGossip.objects.create(
            secret=self.secret, area=self.tree["ward_a"], heat=1, went_public=False
        )
        climber = SecretGossip.objects.create(
            secret=self.secret, area=self.tree["a2"], heat=ward_threshold
        )
        merged = climb_gossip(climber)
        assert merged.pk == already_there.pk
        assert merged.heat == ward_threshold + 1
        assert not SecretGossip.objects.filter(pk=climber.pk).exists()
        assert SecretGossip.objects.filter(secret=self.secret).count() == 1

    def test_a_rooted_reach_never_climbs_further(self):
        row = SecretGossip.objects.create(secret=self.secret, area=self.tree["county"], heat=999)
        assert climb_gossip(row).area_id == self.tree["county"].pk


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_social/security_check_content gate on #2698
class GossipActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed_check_resolution_tables()
        seed_social_check_content()
        cls.special = CheckOutcomeFactory(name="gossip_special", success_level=2)
        cls.regular = CheckOutcomeFactory(name="gossip_regular", success_level=1)
        cls.realm = RealmFactory()
        cls.tree = build_tree(cls.realm)
        cls.society = SocietyFactory(realm=cls.realm)
        cls.hub_a1 = RoomProfileFactory(area=cls.tree["a1"], is_social_hub=True)
        cls.hub_a2 = RoomProfileFactory(area=cls.tree["a2"], is_social_hub=True)
        cls.hub_b1 = RoomProfileFactory(area=cls.tree["b1"], is_social_hub=True)
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

    def _seeker(self):
        seeker_sheet = CharacterSheetFactory()
        CharacterSpecializationValueFactory(
            character=seeker_sheet, specialization=self.gossip_spec, value=10
        )
        entry = RosterEntryFactory(character_sheet=seeker_sheet)
        return seeker_sheet.character, entry

    def test_plant_starts_the_rumor_at_the_hubs_own_area(self):
        with force_check_outcome(self.special):
            result = plant_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        assert result.heat == 2
        row = SecretGossip.objects.get(secret=self.secret)
        assert row.area_id == self.tree["a1"].pk

    def test_plant_regular_success_adds_one_heat(self):
        with force_check_outcome(self.regular):
            result = plant_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        assert result.heat == 1

    def test_the_tavern_rumor_climbs_to_the_ward_and_the_ward_hears_it(self):
        """Four regular plants at A1 carry the rumor to Ward A: A2's hub hears it, B1's does not."""
        for _ in range(GOSSIP_CLIMB_THRESHOLDS[AreaLevel.WARD]):
            with force_check_outcome(self.regular):
                plant_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        row = SecretGossip.objects.get(secret=self.secret)
        assert row.area_id == self.tree["ward_a"].pk
        assert heat_for(self.secret, room=self.hub_a2.objectdb) == row.heat
        assert heat_for(self.secret, room=self.hub_b1.objectdb) == 0

        heard, entry = self._seeker()
        with force_check_outcome(self.regular):
            result = seek_gossip(heard, room=self.hub_a2.objectdb)
        assert result.surfaced_secret_id == self.secret.pk
        assert SecretKnowledge.objects.filter(roster_entry=entry, secret=self.secret).exists()

        deaf, _ = self._seeker()
        with force_check_outcome(self.regular):
            assert seek_gossip(deaf, room=self.hub_b1.objectdb).success is False

    def test_a_later_plant_feeds_the_climbed_rumor_not_a_new_one(self):
        SecretGossip.objects.create(secret=self.secret, area=self.tree["ward_a"], heat=5)
        with force_check_outcome(self.regular):
            plant_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        rows = list(SecretGossip.objects.filter(secret=self.secret))
        assert len(rows) == 1
        assert rows[0].area_id == self.tree["ward_a"].pk
        assert rows[0].heat == 6

    def test_plant_requires_gossip_skill(self):
        bare = CharacterSheetFactory()
        secret = SecretFactory(subject_sheet=bare, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        with self.assertRaises(GossipError):
            plant_gossip(bare.character, secret, room=self.hub_a1.objectdb)

    def test_plant_requires_a_social_hub(self):
        non_hub = RoomProfileFactory(area=self.tree["a1"], is_social_hub=False)
        with self.assertRaises(GossipError):
            plant_gossip(self.character, self.secret, room=non_hub.objectdb)

    def test_plant_refuses_a_hub_that_is_on_no_map(self):
        adrift = RoomProfileFactory(area=None, is_social_hub=True)
        with self.assertRaises(GossipError):
            plant_gossip(self.character, self.secret, room=adrift.objectdb)

    def test_cannot_plant_a_secret_you_do_not_hold(self):
        other = CharacterSheetFactory()
        secret = SecretFactory(subject_sheet=other, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        with force_check_outcome(self.special), self.assertRaises(GossipError):
            plant_gossip(self.character, secret, room=self.hub_a1.objectdb)

    def test_planting_past_the_threshold_goes_public_and_exposes_the_reachs_societies(self):
        SecretGossip.objects.create(
            secret=self.secret, area=self.tree["a1"], heat=GOSSIP_PUBLIC_THRESHOLD - 1
        )
        with force_check_outcome(self.special):
            result = plant_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        assert result.went_public is True
        assert self.society in self.secret.societies_exposed.all()
        # Public heat is above every threshold in the tree: the rumor is county-wide now.
        assert SecretGossip.objects.get(secret=self.secret).area_id == self.tree["county"].pk
        assert public_gossip_lines(self.hub_b1.objectdb) != []

    def test_seek_surfaces_a_hot_secret_and_grants_the_fact(self):
        seeker, entry = self._seeker()
        target = CharacterSheetFactory()
        hot = SecretFactory(subject_sheet=target, level=SecretLevel.UNCOMMON_KNOWLEDGE)
        SecretGossip.objects.create(secret=hot, area=self.tree["barony"], heat=5)
        with force_check_outcome(self.regular):
            result = seek_gossip(seeker, room=self.hub_b1.objectdb)
        assert result.success is True
        assert result.surfaced_secret_id == hot.pk
        held = SecretKnowledge.objects.get(roster_entry=entry, secret=hot)
        assert held.knows_category is False  # fact-only — never leaks deeper layers
        assert held.knows_consequences is False

    def test_suppress_lowers_heat_on_the_rumor_reaching_the_hub(self):
        SecretGossip.objects.create(secret=self.secret, area=self.tree["ward_a"], heat=5)
        with force_check_outcome(self.special):
            result = suppress_gossip(self.character, self.secret, room=self.hub_a2.objectdb)
        assert result.heat == 3  # special suppress removes 2

    def test_suppressed_to_zero_is_unheard_everywhere_below(self):
        SecretGossip.objects.create(secret=self.secret, area=self.tree["ward_a"], heat=2)
        with force_check_outcome(self.special):
            result = suppress_gossip(self.character, self.secret, room=self.hub_a1.objectdb)
        assert result.heat == 0
        seeker, _ = self._seeker()
        with force_check_outcome(self.regular):
            assert seek_gossip(seeker, room=self.hub_a2.objectdb).success is False


@override_settings(SEED_SAMPLE_CONTENT=True)  # seed_social/security_check_content gate on #2698
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
        cls.tree = build_tree(cls.realm)
        cls.hub = RoomProfileFactory(area=cls.tree["a1"], is_social_hub=True)
        cls.other_hub = RoomProfileFactory(area=cls.tree["b1"], is_social_hub=True)
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

    def test_successful_smear_mints_seeds_and_places_the_counter_clue_in_its_reach(self):
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
        row = SecretGossip.objects.get(secret=secret)
        assert row.area_id == self.tree["a1"].pk
        assert row.heat >= 1
        # The trail lands in the hubs of the reach: A1's, and not B1's across the barony.
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
