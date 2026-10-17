"""The reputation-gain lever (#4394) at the society and organization regard chokepoints."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.mechanics.constants import (
    REPUTATION_GAIN_CATEGORY_NAME,
    REPUTATION_GAIN_ORGANIZATION_TARGET_NAME,
    REPUTATION_GAIN_SOCIETY_TARGET_NAME,
    REPUTATION_GAIN_TARGET_NAME,
)
from world.mechanics.test_helpers import grant_lever
from world.societies.factories import OrganizationFactory, SocietyFactory
from world.societies.renown import bump_organization_reputation, bump_society_reputation


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
