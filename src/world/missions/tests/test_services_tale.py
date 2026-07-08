"""Tests for save_run_tale — the tale service (#2047)."""

from __future__ import annotations

from django.test import TestCase

from evennia_extensions.factories import CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.missions.constants import TALE_MAX_LENGTH, MissionStatus
from world.missions.factories import (
    MissionDeedRecordFactory,
    MissionInstanceFactory,
    MissionNodeFactory,
    MissionOptionFactory,
    MissionParticipantFactory,
    MissionTemplateFactory,
)
from world.missions.models import MissionRunTale
from world.missions.services.play import NotParticipantError, SaveRunTaleError, save_run_tale


def _make_terminal_run(status: str = MissionStatus.RESOLVED):
    """Build an instance with a contract-holder participant on a terminal-status run."""
    template = MissionTemplateFactory()
    instance = MissionInstanceFactory(template=template, status=status)
    holder_char = CharacterFactory(db_key="TaleHolder")
    CharacterSheetFactory(character=holder_char)
    MissionParticipantFactory(instance=instance, character=holder_char, is_contract_holder=True)
    return instance, holder_char


class SaveRunTaleGuardTests(TestCase):
    """Guards: participant, terminal status, length cap, empty text."""

    def test_save_tale_on_resolved_run(self):
        instance, holder = _make_terminal_run(MissionStatus.RESOLVED)
        tale = save_run_tale(instance, holder, "It was a dark night.")
        self.assertEqual(tale.text, "It was a dark night.")
        self.assertEqual(MissionRunTale.objects.count(), 1)

    def test_save_tale_on_complete_run(self):
        instance, holder = _make_terminal_run(MissionStatus.COMPLETE)
        tale = save_run_tale(instance, holder, "We won.")
        self.assertEqual(tale.text, "We won.")

    def test_save_tale_on_abandoned_run(self):
        instance, holder = _make_terminal_run(MissionStatus.ABANDONED)
        tale = save_run_tale(instance, holder, "It fell apart.")
        self.assertEqual(tale.text, "It fell apart.")

    def test_active_run_rejects_tale(self):
        instance, holder = _make_terminal_run(MissionStatus.ACTIVE)
        with self.assertRaises(SaveRunTaleError):
            save_run_tale(instance, holder, "text")

    def test_non_participant_raises_not_participant(self):
        instance, _ = _make_terminal_run()
        outsider = CharacterFactory(db_key="Outsider")
        CharacterSheetFactory(character=outsider)
        with self.assertRaises(NotParticipantError):
            save_run_tale(instance, outsider, "text")

    def test_tale_upsert_replaces_text(self):
        instance, holder = _make_terminal_run()
        save_run_tale(instance, holder, "first")
        tale = save_run_tale(instance, holder, "second")
        self.assertEqual(MissionRunTale.objects.count(), 1)
        self.assertEqual(tale.text, "second")

    def test_tale_too_long_rejected(self):
        instance, holder = _make_terminal_run()
        with self.assertRaises(SaveRunTaleError):
            save_run_tale(instance, holder, "x" * (TALE_MAX_LENGTH + 1))

    def test_empty_tale_rejected(self):
        instance, holder = _make_terminal_run()
        with self.assertRaises(SaveRunTaleError):
            save_run_tale(instance, holder, "   ")


def _make_legend_run(status: str = MissionStatus.COMPLETE):
    """Build a complete run with a deed that has a legend entry linked."""
    template = MissionTemplateFactory()
    node = MissionNodeFactory(template=template)
    option = MissionOptionFactory(node=node)
    instance = MissionInstanceFactory(template=template, status=status)
    holder_char = CharacterFactory(db_key="LegendHolder")
    sheet = CharacterSheetFactory(character=holder_char)
    holder_persona = sheet.primary_persona
    MissionParticipantFactory(instance=instance, character=holder_char, is_contract_holder=True)
    deed = MissionDeedRecordFactory(instance=instance, actor=holder_char, node=node, option=option)
    return instance, holder_char, holder_persona, deed


class SaveRunTaleLegendSeedingTests(TestCase):
    """On a legend-minting run, saving a tale seeds LegendDeedStory for unstoried entries."""

    def test_tale_seeds_unstoried_legend_deed_stories(self):
        from world.societies.factories import LegendEntryFactory
        from world.societies.models import LegendDeedStory

        instance, holder, holder_persona, deed = _make_legend_run()
        entry = LegendEntryFactory(persona=holder_persona)
        deed.legend_entries.add(entry)

        save_run_tale(instance, holder, "The tale of my deeds.")

        story = LegendDeedStory.objects.get(deed=entry, author=holder_persona)
        self.assertEqual(story.text, "The tale of my deeds.")

    def test_already_storied_entries_not_overwritten(self):
        from world.societies.factories import LegendDeedStoryFactory, LegendEntryFactory
        from world.societies.models import LegendDeedStory

        instance, holder, holder_persona, deed = _make_legend_run()
        entry = LegendEntryFactory(persona=holder_persona)
        deed.legend_entries.add(entry)
        LegendDeedStoryFactory(deed=entry, author=holder_persona, text="original story")

        save_run_tale(instance, holder, "new tale text")

        story = LegendDeedStory.objects.get(deed=entry, author=holder_persona)
        self.assertEqual(story.text, "original story")

    def test_no_legend_entries_no_seeding(self):
        from world.societies.models import LegendDeedStory

        instance, holder = _make_terminal_run(MissionStatus.COMPLETE)
        save_run_tale(instance, holder, "A plain run.")
        self.assertEqual(LegendDeedStory.objects.count(), 0)

    def test_accepted_as_persona_seeds_matching_entry(self):
        """Contract holder with accepted_as_persona seeds entries under that persona."""
        from world.scenes.factories import PersonaFactory
        from world.societies.factories import LegendEntryFactory
        from world.societies.models import LegendDeedStory

        instance, holder, _, deed = _make_legend_run()
        mask_persona = PersonaFactory(character_sheet=holder.sheet_data)
        instance.accepted_as_persona = mask_persona
        instance.save(update_fields=["accepted_as_persona"])
        entry = LegendEntryFactory(persona=mask_persona)
        deed.legend_entries.add(entry)

        save_run_tale(instance, holder, "Under the mask.")

        story = LegendDeedStory.objects.get(deed=entry, author=mask_persona)
        self.assertEqual(story.text, "Under the mask.")
