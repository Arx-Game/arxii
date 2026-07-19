"""Tests for the origin-story write services (#2478)."""

from django.test import TestCase

from world.character_creation.constants import OriginStoryState
from world.character_creation.models import (
    Beginnings,
    CharacterOriginSlot,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)


class OriginStoryServiceTest(TestCase):
    """Service-layer single-write-path — mirrors glimpse services."""

    def setUp(self) -> None:
        from world.character_sheets.services import create_character_with_sheet

        self.area = StartingArea.objects.create(name="Service Test Area")
        self.beginning = Beginnings.objects.create(
            name="Service Test Beginning", starting_area=self.area
        )
        self.template = OriginTemplate.objects.create(
            beginning=self.beginning,
            name="Escape",
            frame_narrative="Your story begins with escape from Salvation.",
        )
        self.slot1 = OriginTemplateSlot.objects.create(
            template=self.template,
            name="Who helped?",
            prompt="Name the person who aided your flight.",
            sort_order=0,
        )
        self.slot2 = OriginTemplateSlot.objects.create(
            template=self.template,
            name="What was left behind?",
            prompt="What did you leave behind?",
            sort_order=1,
        )
        self.character, self.sheet, _primary = create_character_with_sheet(
            character_key="svctestchar",
            primary_persona_name="SvcTestChar",
        )

    def test_fresh_sheet_is_not_started(self) -> None:
        """A sheet with no slots is NOT_STARTED."""
        from world.character_creation.services import refresh_origin_story_state

        assert refresh_origin_story_state(self.sheet) == OriginStoryState.NOT_STARTED

    def test_slot_only_is_slots_only(self) -> None:
        """Filling a slot but no prose → SLOTS_ONLY."""
        from world.character_creation.services import (
            refresh_origin_story_state,
            set_origin_slot,
        )

        set_origin_slot(self.sheet, self.slot1, "Mira helped me.")
        assert refresh_origin_story_state(self.sheet) == OriginStoryState.SLOTS_ONLY

    def test_set_slot_upserts(self) -> None:
        """set_origin_slot replaces existing value (upsert)."""
        from world.character_creation.services import set_origin_slot

        set_origin_slot(self.sheet, self.slot1, "First answer.")
        set_origin_slot(self.sheet, self.slot1, "Second answer.")
        row = CharacterOriginSlot.objects.get(sheet=self.sheet, slot=self.slot1)
        assert row.value == "Second answer."

    def test_clear_slot(self) -> None:
        """clear_origin_slot deletes the row and recomputes state."""
        from world.character_creation.services import (
            clear_origin_slot,
            set_origin_slot,
        )

        set_origin_slot(self.sheet, self.slot1, "Mira.")
        assert self.sheet.origin_story_state == OriginStoryState.SLOTS_ONLY
        clear_origin_slot(self.sheet, self.slot1)
        assert not CharacterOriginSlot.objects.filter(sheet=self.sheet, slot=self.slot1).exists()
        assert self.sheet.origin_story_state == OriginStoryState.NOT_STARTED

    def test_assemble_prose(self) -> None:
        """assemble_origin_prose composes frame + slot answers."""
        from world.character_creation.services import (
            assemble_origin_prose,
            set_origin_slot,
        )

        set_origin_slot(self.sheet, self.slot1, "Mira cut the lock.")
        set_origin_slot(self.sheet, self.slot2, "My name and my past.")
        prose = assemble_origin_prose(self.sheet)
        assert "escape from Salvation" in prose
        assert "Mira cut the lock" in prose
        assert "My name and my past" in prose

    def test_assemble_prose_empty(self) -> None:
        """assemble_origin_prose returns empty string when no slots."""
        from world.character_creation.services import assemble_origin_prose

        assert assemble_origin_prose(self.sheet) == ""
