"""The reputation-gain lever (#4394) at the society and organization regard chokepoints."""

from django.test import TestCase

from world.character_creation.factories import RealmFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import (
    REPUTATION_GAIN_CATEGORY_NAME,
    REPUTATION_GAIN_ORGANIZATION_TARGET_NAME,
    REPUTATION_GAIN_SOCIETY_TARGET_NAME,
    REPUTATION_GAIN_TARGET_NAME,
)
from world.mechanics.test_helpers import grant_lever
from world.societies.constants import RenownReach
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.societies.models import SocietyReputation
from world.societies.renown import (
    bump_organization_reputation,
    bump_society_reputation,
    fire_renown_award,
)
from world.societies.tests.test_renown_phase_b import _make_archetype, _make_primary_persona


class ReputationGainLeverTests(TestCase):
    def setUp(self) -> None:
        self.sheet = CharacterSheetFactory()
        self.persona = self.sheet.primary_persona
        self.society = SocietyFactory()
        self.organization = OrganizationFactory()

    def test_without_a_lever_the_delta_lands_whole(self) -> None:
        assert bump_society_reputation(self.persona, self.society, 100) == 100
        assert bump_organization_reputation(self.persona, self.organization, 100) == 100

    def test_renowned_gains_more_with_everyone(self) -> None:
        grant_lever(self.sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME, 25)
        assert bump_society_reputation(self.persona, self.society, 100) == 125
        assert bump_organization_reputation(self.persona, self.organization, 100) == 125

    def test_a_leg_target_scales_one_leg_and_adds_to_the_general_one(self) -> None:
        grant_lever(self.sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME, 25)
        grant_lever(
            self.sheet,
            REPUTATION_GAIN_CATEGORY_NAME,
            REPUTATION_GAIN_SOCIETY_TARGET_NAME,
            -10,
        )
        assert bump_society_reputation(self.persona, self.society, 100) == 115
        assert bump_organization_reputation(self.persona, self.organization, 100) == 125

    def test_an_organization_leg_alone(self) -> None:
        grant_lever(
            self.sheet,
            REPUTATION_GAIN_CATEGORY_NAME,
            REPUTATION_GAIN_ORGANIZATION_TARGET_NAME,
            -50,
        )
        assert bump_society_reputation(self.persona, self.society, 100) == 100
        assert bump_organization_reputation(self.persona, self.organization, 100) == 50

    def test_a_sting_is_never_scaled(self) -> None:
        grant_lever(self.sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME, -50)
        assert bump_society_reputation(self.persona, self.society, -40) == -40

    def test_a_gain_scaled_to_nothing_writes_nothing(self) -> None:
        grant_lever(self.sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME, -100)
        assert bump_society_reputation(self.persona, self.society, 3) is None


class ReputationGainRecordedTests(TestCase):
    """An award records what each society actually moved by, and a starting seed is not a gain."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.realm = RealmFactory(name="Lever Realm")
        cls.honor = SocietyFactory(
            name="Honor Lever",
            realm=cls.realm,
            mercy=2,
            method=3,
            status=0,
            change=0,
            allegiance=0,
            power=0,
        )

    def test_the_deed_records_the_scaled_delta(self) -> None:
        heroic = _make_archetype(mercy_delta=2, method_delta=2)
        persona = _make_primary_persona()
        grant_lever(
            persona.character_sheet,
            REPUTATION_GAIN_CATEGORY_NAME,
            REPUTATION_GAIN_TARGET_NAME,
            50,
        )
        result = fire_renown_award(
            persona=persona,
            archetypes=[heroic],
            reach=RenownReach.WORLD,
            society_overrides={self.honor: 100},
        )
        assert result.reputation_deltas[self.honor.pk] == 150
        assert SocietyReputation.objects.get(persona=persona, society=self.honor).value == 150

    def test_a_write_may_opt_out_of_the_lever(self) -> None:
        sheet = CharacterSheetFactory()
        grant_lever(sheet, REPUTATION_GAIN_CATEGORY_NAME, REPUTATION_GAIN_TARGET_NAME, 50)
        assert (
            bump_society_reputation(sheet.primary_persona, self.honor, 100, scale_gain=False) == 100
        )
