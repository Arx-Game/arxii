"""Collection difficulty from local order/crime (#696 item 1)."""

from unittest.mock import patch

from django.test import TestCase

from world.areas.factories import AreaFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.checks.factories import CheckTypeFactory
from world.checks.test_helpers import force_check_outcome
from world.currency.constants import IncomeStreamKind
from world.currency.models import OrgIncomeStream
from world.currency.services import (
    _collection_target_difficulty,
    accrue_income_stream,
    collect_org_income,
)
from world.locations.constants import KeyType, LocationParentType, StatKey
from world.locations.models import LocationValueModifier
from world.scenes.action_constants import DIFFICULTY_VALUES, DifficultyChoice
from world.societies.factories import OrganizationFactory
from world.traits.factories import CheckOutcomeFactory


def _write_stat_modifier(area, stat_key: str, value: int) -> None:
    """Author an area-level cascade row the way turf_services._sync_crime_modifier does."""
    LocationValueModifier.objects.create(
        parent_type=LocationParentType.AREA,
        area=area,
        room_profile=None,
        key_type=KeyType.STAT,
        stat_key=stat_key,
        value=value,
        change_per_day=0,
    )


class CollectionTargetDifficultyTests(TestCase):
    """Unit coverage of the module-private helper directly."""

    def test_no_area_streams_use_normal(self) -> None:
        streams = [OrgIncomeStream(area=None), OrgIncomeStream(area=None)]
        difficulty = _collection_target_difficulty(streams)
        self.assertEqual(difficulty, DIFFICULTY_VALUES[DifficultyChoice.NORMAL])

    def test_crime_raises_difficulty_worst_stop_wins(self) -> None:
        area_a = AreaFactory()
        area_b = AreaFactory()
        _write_stat_modifier(area_a, StatKey.CRIME, 20)
        _write_stat_modifier(area_b, StatKey.CRIME, 5)
        streams = [OrgIncomeStream(area=area_a), OrgIncomeStream(area=area_b)]
        difficulty = _collection_target_difficulty(streams)
        self.assertEqual(difficulty, DIFFICULTY_VALUES[DifficultyChoice.NORMAL] + 20)

    def test_order_lowers_difficulty_clamped_at_trivial(self) -> None:
        area = AreaFactory()
        _write_stat_modifier(area, StatKey.ORDER, 100)
        streams = [OrgIncomeStream(area=area)]
        difficulty = _collection_target_difficulty(streams)
        self.assertEqual(difficulty, DIFFICULTY_VALUES[DifficultyChoice.TRIVIAL])

    def test_clamped_at_harrowing(self) -> None:
        area = AreaFactory()
        _write_stat_modifier(area, StatKey.CRIME, 500)
        streams = [OrgIncomeStream(area=area)]
        difficulty = _collection_target_difficulty(streams)
        self.assertEqual(difficulty, DIFFICULTY_VALUES[DifficultyChoice.HARROWING])


class CollectOrgIncomeDifficultyWiringTests(TestCase):
    """collect_org_income wires the derived difficulty and the override seam through."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.org = OrganizationFactory()
        cls.character = CharacterSheetFactory().character
        CheckTypeFactory(name="Tax Collection")

    def setUp(self) -> None:
        self.area = AreaFactory()
        _write_stat_modifier(self.area, StatKey.CRIME, 20)
        self.stream = OrgIncomeStream.objects.create(
            organization=self.org,
            name="Land taxes",
            kind=IncomeStreamKind.DOMAIN_TAX,
            gross_amount=600,
            area=self.area,
        )
        accrue_income_stream(self.stream)

    def tearDown(self) -> None:
        OrgIncomeStream.objects.filter(organization=self.org).delete()

    def test_collect_org_income_passes_derived_difficulty(self) -> None:
        outcome = CheckOutcomeFactory(name="derived_diff_outcome", success_level=1)
        with force_check_outcome(outcome) as capture:
            collect_org_income(organization=self.org, character=self.character)
        self.assertEqual(capture.target_difficulty, DIFFICULTY_VALUES[DifficultyChoice.NORMAL] + 20)

    def test_success_level_override_skips_check(self) -> None:
        with patch("world.checks.services.perform_check_with_modifiers") as mocked_check:
            result = collect_org_income(
                organization=self.org,
                character=self.character,
                success_level_override=3,
            )
        mocked_check.assert_not_called()
        self.assertEqual(result.success_level, 3)
