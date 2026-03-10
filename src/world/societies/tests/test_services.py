"""Tests for societies legend service functions."""

from django.test import TestCase

from world.character_sheets.factories import GuiseFactory
from world.societies.factories import LegendSourceTypeFactory
from world.societies.models import CharacterLegendSummary
from world.societies.services import (
    create_legend_event,
    create_solo_deed,
    get_character_legend_total,
    get_guise_legend_total,
    spread_deed,
    spread_event,
)


class CreateSoloDeedTests(TestCase):
    """Tests for create_solo_deed service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise = GuiseFactory()
        cls.source_type = LegendSourceTypeFactory(name="Combat")

    def test_creates_deed(self) -> None:
        """Verifies all fields set correctly and event is None."""
        deed = create_solo_deed(
            guise=self.guise,
            title="Slew the Dragon",
            source_type=self.source_type,
            base_value=50,
        )
        self.assertEqual(deed.guise, self.guise)
        self.assertEqual(deed.title, "Slew the Dragon")
        self.assertEqual(deed.source_type, self.source_type)
        self.assertEqual(deed.base_value, 50)
        self.assertIsNone(deed.event)
        self.assertTrue(deed.is_active)

    def test_deed_with_optional_fields(self) -> None:
        """Verifies description, scene, and story are set."""
        deed = create_solo_deed(
            guise=self.guise,
            title="Found the Artifact",
            source_type=self.source_type,
            base_value=30,
            description="A legendary discovery in the deep caves.",
        )
        self.assertEqual(deed.description, "A legendary discovery in the deep caves.")
        self.assertIsNone(deed.scene)
        self.assertIsNone(deed.story)

    def test_refreshes_materialized_view(self) -> None:
        """CharacterLegendSummary shows correct total after creation."""
        create_solo_deed(
            guise=self.guise,
            title="Brave Act",
            source_type=self.source_type,
            base_value=25,
        )
        summary = CharacterLegendSummary.objects.get(character=self.guise.character)
        self.assertEqual(summary.personal_legend, 25)


class CreateLegendEventTests(TestCase):
    """Tests for create_legend_event service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.guise_a = GuiseFactory()
        cls.guise_b = GuiseFactory()
        cls.source_type = LegendSourceTypeFactory(name="Story")

    def test_creates_event_and_deeds(self) -> None:
        """Event created with correct number of deeds linked to it."""
        event, deeds = create_legend_event(
            title="Battle of the Pass",
            source_type=self.source_type,
            base_value=40,
            guises=[self.guise_a, self.guise_b],
        )
        self.assertEqual(event.title, "Battle of the Pass")
        self.assertEqual(event.base_value, 40)
        self.assertEqual(len(deeds), 2)
        for deed in deeds:
            self.assertEqual(deed.event_id, event.pk)

    def test_deeds_linked_to_correct_guises(self) -> None:
        """Each deed has the right guise."""
        _event, deeds = create_legend_event(
            title="Ritual of Light",
            source_type=self.source_type,
            base_value=20,
            guises=[self.guise_a, self.guise_b],
        )
        guise_ids = {deed.guise_id for deed in deeds}
        self.assertEqual(guise_ids, {self.guise_a.pk, self.guise_b.pk})

    def test_refreshes_materialized_view(self) -> None:
        """Totals correct after creation."""
        create_legend_event(
            title="Joint Discovery",
            source_type=self.source_type,
            base_value=30,
            guises=[self.guise_a, self.guise_b],
        )
        summary_a = CharacterLegendSummary.objects.get(character=self.guise_a.character)
        summary_b = CharacterLegendSummary.objects.get(character=self.guise_b.character)
        self.assertEqual(summary_a.personal_legend, 30)
        self.assertEqual(summary_b.personal_legend, 30)


class SpreadDeedTests(TestCase):
    """Tests for spread_deed service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_type = LegendSourceTypeFactory(name="Exploration")
        cls.spreader = GuiseFactory()

    def test_creates_spread(self) -> None:
        """Spread created with correct value."""
        guise = GuiseFactory()
        deed = create_solo_deed(
            guise=guise,
            title="Explored the Ruins",
            source_type=self.source_type,
            base_value=10,
        )
        spread = spread_deed(
            deed=deed,
            spreader_guise=self.spreader,
            value_added=5,
        )
        self.assertEqual(spread.legend_entry, deed)
        self.assertEqual(spread.spreader_guise, self.spreader)
        self.assertEqual(spread.value_added, 5)

    def test_clamps_to_remaining_capacity(self) -> None:
        """Tries to add more than remaining, gets clamped."""
        guise = GuiseFactory()
        deed = create_solo_deed(
            guise=guise,
            title="Minor Feat",
            source_type=self.source_type,
            base_value=10,
        )
        # max_spread = 10 * 9 = 90
        # Try to add 100, should be clamped to 90
        spread = spread_deed(
            deed=deed,
            spreader_guise=self.spreader,
            value_added=100,
        )
        self.assertEqual(spread.value_added, 90)

    def test_returns_zero_spread_when_capped(self) -> None:
        """Fully capped deed gets 0 value spread."""
        guise = GuiseFactory()
        deed = create_solo_deed(
            guise=guise,
            title="Capped Deed",
            source_type=self.source_type,
            base_value=10,
        )
        # Fill capacity: 10 * 9 = 90
        spread_deed(
            deed=deed,
            spreader_guise=self.spreader,
            value_added=90,
        )
        # Now capacity is 0
        spread = spread_deed(
            deed=deed,
            spreader_guise=self.spreader,
            value_added=10,
        )
        self.assertEqual(spread.value_added, 0)

    def test_raises_on_inactive_deed(self) -> None:
        """Spreading an inactive deed raises ValueError."""
        guise = GuiseFactory()
        deed = create_solo_deed(
            guise=guise,
            title="Inactive Deed",
            source_type=self.source_type,
            base_value=10,
        )
        deed.is_active = False
        deed.save()
        with self.assertRaises(ValueError, msg="Cannot spread an inactive deed."):
            spread_deed(
                deed=deed,
                spreader_guise=self.spreader,
                value_added=5,
            )

    def test_refreshes_materialized_view(self) -> None:
        """Total includes spread after refresh."""
        guise = GuiseFactory()
        deed = create_solo_deed(
            guise=guise,
            title="Spread Test",
            source_type=self.source_type,
            base_value=10,
        )
        spread_deed(
            deed=deed,
            spreader_guise=self.spreader,
            value_added=5,
        )
        summary = CharacterLegendSummary.objects.get(character=guise.character)
        # base_value 10 + spread 5 = 15
        self.assertEqual(summary.personal_legend, 15)


class SpreadEventTests(TestCase):
    """Tests for spread_event service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_type = LegendSourceTypeFactory(name="Battle")
        cls.spreader = GuiseFactory()
        cls.guise_a = GuiseFactory()
        cls.guise_b = GuiseFactory()

    def test_spreads_all_deeds_in_event(self) -> None:
        """Creates spreads for every deed in the event."""
        event, _deeds = create_legend_event(
            title="Great Battle",
            source_type=self.source_type,
            base_value=20,
            guises=[self.guise_a, self.guise_b],
        )
        spreads = spread_event(
            event=event,
            spreader_guise=self.spreader,
            value_per_deed=10,
        )
        self.assertEqual(len(spreads), 2)
        for spread in spreads:
            self.assertEqual(spread.value_added, 10)

    def test_clamps_per_deed(self) -> None:
        """Each deed's spread is independently clamped."""
        event, deeds = create_legend_event(
            title="Small Skirmish",
            source_type=self.source_type,
            base_value=5,
            guises=[self.guise_a, self.guise_b],
        )
        # max_spread per deed = 5 * 9 = 45
        # First spread fills some capacity on one deed only
        spread_deed(
            deed=deeds[0],
            spreader_guise=self.spreader,
            value_added=40,
        )
        # Now spread event with 10 per deed:
        # deed[0] has 5 remaining, deed[1] has 45 remaining
        spreads = spread_event(
            event=event,
            spreader_guise=self.spreader,
            value_per_deed=10,
        )
        values = sorted(s.value_added for s in spreads)
        self.assertEqual(values, [5, 10])


class GetCharacterLegendTotalTests(TestCase):
    """Tests for get_character_legend_total service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_type = LegendSourceTypeFactory(name="Discovery")

    def test_returns_zero_for_no_deeds(self) -> None:
        """Character with no deeds returns 0."""
        guise = GuiseFactory()
        # Refresh views so there's no stale data
        from world.societies.models import refresh_legend_views

        refresh_legend_views()
        total = get_character_legend_total(guise.character)
        self.assertEqual(total, 0)

    def test_returns_correct_total(self) -> None:
        """Returns the correct legend total for a character."""
        guise = GuiseFactory()
        create_solo_deed(
            guise=guise,
            title="Deed A",
            source_type=self.source_type,
            base_value=10,
        )
        create_solo_deed(
            guise=guise,
            title="Deed B",
            source_type=self.source_type,
            base_value=20,
        )
        total = get_character_legend_total(guise.character)
        self.assertEqual(total, 30)

    def test_sums_across_guises(self) -> None:
        """Sums legend from multiple guises of the same character."""
        guise_a = GuiseFactory()
        character = guise_a.character
        guise_b = GuiseFactory(
            character=character,
            name="Alias",
            is_default=False,
            is_persistent=True,
        )
        create_solo_deed(
            guise=guise_a,
            title="Default Deed",
            source_type=self.source_type,
            base_value=15,
        )
        create_solo_deed(
            guise=guise_b,
            title="Alias Deed",
            source_type=self.source_type,
            base_value=25,
        )
        total = get_character_legend_total(character)
        self.assertEqual(total, 40)


class GetGuiseLegendTotalTests(TestCase):
    """Tests for get_guise_legend_total service function."""

    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.source_type = LegendSourceTypeFactory(name="Craft")

    def test_returns_zero_for_no_deeds(self) -> None:
        """Guise with no deeds returns 0."""
        guise = GuiseFactory()
        from world.societies.models import refresh_legend_views

        refresh_legend_views()
        total = get_guise_legend_total(guise)
        self.assertEqual(total, 0)

    def test_returns_correct_total(self) -> None:
        """Returns correct legend total for a guise."""
        guise = GuiseFactory()
        create_solo_deed(
            guise=guise,
            title="Craft Masterpiece",
            source_type=self.source_type,
            base_value=35,
        )
        total = get_guise_legend_total(guise)
        self.assertEqual(total, 35)
