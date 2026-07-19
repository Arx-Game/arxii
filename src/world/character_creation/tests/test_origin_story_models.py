"""Tests for OriginTemplate / OriginTemplateSlot content models (#2478)."""

from django.db import IntegrityError
from django.test import TestCase

from world.character_creation.models import (
    Beginnings,
    OriginTemplate,
    OriginTemplateSlot,
    StartingArea,
)


class OriginTemplateModelTest(TestCase):
    """OriginTemplate content model — mirrors GlimpseTag pattern."""

    def setUp(self) -> None:
        self.area = StartingArea.objects.create(name="Test Area")
        self.beginning = Beginnings.objects.create(name="Test Beginning", starting_area=self.area)

    def test_create_template(self) -> None:
        """A template can be created with a beginning FK and frame narrative."""
        template = OriginTemplate.objects.create(
            beginning=self.beginning,
            name="Escape from Salvation",
            frame_narrative="Your story begins with escape from Salvation...",
        )
        assert template.is_active is True
        assert template.sort_order == 0
        assert str(template) == "Escape from Salvation"

    def test_natural_key(self) -> None:
        """Natural key is (beginning, name), no slug. FK is flattened —
        Beginning's own natural key (starting_area name, beginning name) is
        spread into the tuple, so the full key is (area, beginning, name)."""
        template = OriginTemplate.objects.create(
            beginning=self.beginning,
            name="Escape",
            frame_narrative="...",
        )
        assert template.natural_key() == ("Test Area", "Test Beginning", "Escape")

    def test_multiple_templates_per_beginning(self) -> None:
        """Multiple templates allowed per beginning (Decision 1)."""
        OriginTemplate.objects.create(beginning=self.beginning, name="Escape", frame_narrative="A")
        OriginTemplate.objects.create(beginning=self.beginning, name="Capture", frame_narrative="B")
        assert OriginTemplate.objects.filter(beginning=self.beginning).count() == 2

    def test_unique_name_per_beginning(self) -> None:
        """Template name is unique within a beginning."""
        OriginTemplate.objects.create(beginning=self.beginning, name="Escape", frame_narrative="A")
        with self.assertRaises(IntegrityError):
            OriginTemplate.objects.create(
                beginning=self.beginning, name="Escape", frame_narrative="B"
            )


class OriginTemplateSlotModelTest(TestCase):
    """OriginTemplateSlot content model — authored slot prompts."""

    def setUp(self) -> None:
        self.area = StartingArea.objects.create(name="Test Area 2")
        self.beginning = Beginnings.objects.create(name="Test Beginning 2", starting_area=self.area)
        self.template = OriginTemplate.objects.create(
            beginning=self.beginning, name="Escape", frame_narrative="..."
        )

    def test_create_slot(self) -> None:
        """A slot prompt can be created on a template."""
        slot = OriginTemplateSlot.objects.create(
            template=self.template,
            name="Who helped you escape?",
            prompt="Name the person who aided your flight.",
            example="My sister Mira cut the lock while the guards slept.",
        )
        assert slot.is_required is True
        assert slot.sort_order == 0
        assert "Who helped" in str(slot)

    def test_natural_key(self) -> None:
        """Natural key is (template, name), no slug. FK is flattened —
        OriginTemplate's own natural key (area, beginning, template name) is
        spread into the tuple, so the full key is (area, beginning, template, slot)."""
        slot = OriginTemplateSlot.objects.create(
            template=self.template, name="Who helped?", prompt="..."
        )
        assert slot.natural_key() == (
            "Test Area 2",
            "Test Beginning 2",
            "Escape",
            "Who helped?",
        )

    def test_unique_name_per_template(self) -> None:
        """Slot name unique within a template."""
        OriginTemplateSlot.objects.create(template=self.template, name="Who helped?", prompt="A")
        with self.assertRaises(IntegrityError):
            OriginTemplateSlot.objects.create(
                template=self.template, name="Who helped?", prompt="B"
            )


class CharacterOriginSlotModelTest(TestCase):
    """CharacterOriginSlot instance data — mirrors CharacterGlimpseTag."""

    def setUp(self) -> None:
        from world.character_sheets.services import create_character_with_sheet

        self.area = StartingArea.objects.create(name="Test Area 3")
        self.beginning = Beginnings.objects.create(name="Test Beginning 3", starting_area=self.area)
        self.template = OriginTemplate.objects.create(
            beginning=self.beginning, name="Escape", frame_narrative="..."
        )
        self.slot = OriginTemplateSlot.objects.create(
            template=self.template, name="Who helped?", prompt="..."
        )
        self.character, self.sheet, _primary = create_character_with_sheet(
            character_key="testchar",
            primary_persona_name="Testchar",
        )

    def test_create_slot_answer(self) -> None:
        """A character's slot answer can be created."""
        from world.character_creation.models import CharacterOriginSlot

        answer = CharacterOriginSlot.objects.create(
            sheet=self.sheet, slot=self.slot, value="My sister Mira."
        )
        assert answer.value == "My sister Mira."
        assert answer.sheet == self.sheet

    def test_unique_slot_per_sheet(self) -> None:
        """One answer per (sheet, slot)."""
        from world.character_creation.models import CharacterOriginSlot

        CharacterOriginSlot.objects.create(sheet=self.sheet, slot=self.slot, value="First")
        with self.assertRaises(IntegrityError):
            CharacterOriginSlot.objects.create(sheet=self.sheet, slot=self.slot, value="Second")

    def test_sheet_default_origin_state(self) -> None:
        """CharacterSheet defaults to NOT_STARTED origin state."""
        assert self.sheet.origin_story_state == "not_started"
