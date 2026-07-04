"""Tests for the #1771 real boundary registry backing check_stake_boundaries.

Covers hard-line auto-block (always private) and treasured-subject
requires-signoff gating. See ADR-0033 for the privacy invariant:
``blocked_reason_private`` is staff/audit only and must never carry
player- or theme-identifying specifics.
"""

from django.test import TestCase

from world.boundaries.constants import BoundaryKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import (
    BeatFactory,
    StakeFactory,
    StakeTemplateFactory,
    TreasuredSignoffFactory,
)
from world.stories.services.boundaries import check_stake_boundaries


def _sheet_with_player():
    """A CharacterSheet with a live current tenure (roster_entry -> tenure -> player_data)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    player_data = PlayerDataFactory()
    tenure = RosterTenureFactory(roster_entry=entry, player_data=player_data)
    return sheet, tenure, player_data


class HardLineBlockTests(TestCase):
    def test_hard_line_theme_match_blocks(self):
        theme = ContentThemeFactory(name="Confidential Sensitive Theme")
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        sheet, _tenure, player_data = _sheet_with_player()
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.HARD_LINE,
            theme=theme,
        )
        stake = StakeFactory(template=template)

        report = check_stake_boundaries([stake], [sheet])

        self.assertFalse(report.allowed)
        self.assertTrue(report.blocked_reason_private)
        self.assertFalse(report.cleared)

    def test_no_hard_line_match_allows(self):
        theme = ContentThemeFactory()
        other_theme = ContentThemeFactory()
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        sheet, _tenure, player_data = _sheet_with_player()
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.HARD_LINE,
            theme=other_theme,
        )
        stake = StakeFactory(template=template)

        report = check_stake_boundaries([stake], [sheet])

        self.assertTrue(report.allowed)
        self.assertTrue(report.cleared)

    def test_untemplated_custom_stake_never_hard_line_blocked(self):
        sheet, _tenure, player_data = _sheet_with_player()
        theme = ContentThemeFactory()
        PlayerBoundaryFactory(owner=player_data, kind=BoundaryKind.HARD_LINE, theme=theme)
        stake = StakeFactory(template=None)

        report = check_stake_boundaries([stake], [sheet])

        self.assertTrue(report.allowed)


class HardLinePrivacyTests(TestCase):
    """ADR-0033: blocked_reason_private is staff/audit only — terse, no specifics."""

    def test_blocked_reason_excludes_theme_and_player_identifiers(self):
        theme = ContentThemeFactory(name="Very Specific Secret Theme Name")
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        sheet, _tenure, player_data = _sheet_with_player()
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.HARD_LINE,
            theme=theme,
        )
        stake = StakeFactory(template=template)

        report = check_stake_boundaries([stake], [sheet])

        reason = report.blocked_reason_private
        self.assertNotIn(theme.name, reason)
        self.assertNotIn(theme.key, reason)
        # Structural, not narrative: a bare pair-count audit line with no
        # embedded player/theme identifiers (a numeric pair-count may
        # coincidentally contain small test pks, so assert the exact shape
        # instead of doing brittle substring-on-digit checks).
        self.assertRegex(reason, r"^hard-line theme match on \d+ \(player,stake\) pair\(s\)$")
        # Terse: an audit log line, not a narrative explanation.
        self.assertLess(len(reason), 200)

    def test_report_surface_carries_no_extra_player_facing_fields(self):
        """The dataclass contract itself has no field a serializer could
        accidentally expose beyond the three documented ones."""
        theme = ContentThemeFactory()
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        sheet, _tenure, player_data = _sheet_with_player()
        PlayerBoundaryFactory(owner=player_data, kind=BoundaryKind.HARD_LINE, theme=theme)
        stake = StakeFactory(template=template)

        report = check_stake_boundaries([stake], [sheet])

        field_names = {f.name for f in __import__("dataclasses").fields(report)}
        self.assertEqual(field_names, {"allowed", "requires_signoff", "blocked_reason_private"})


class TreasuredRequiresSignoffTests(TestCase):
    def test_treasured_subject_staked_without_signoff_requires_it(self):
        beat = BeatFactory()
        sheet, tenure, _player_data = _sheet_with_player()
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )

        report = check_stake_boundaries([stake], [sheet])

        self.assertTrue(report.allowed)
        self.assertIn(sheet.pk, report.requires_signoff)
        self.assertFalse(report.cleared)

    def test_treasured_subject_with_active_signoff_not_required(self):
        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        TreasuredSignoffFactory(
            beat=beat,
            player_data=player_data,
            treasured_subject=treasured,
            withdrawn_at=None,
        )

        report = check_stake_boundaries([stake], [sheet])

        self.assertTrue(report.allowed)
        self.assertNotIn(sheet.pk, report.requires_signoff)
        self.assertTrue(report.cleared)

    def test_withdrawn_signoff_still_requires_signoff(self):
        from django.utils import timezone

        beat = BeatFactory()
        sheet, tenure, player_data = _sheet_with_player()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        TreasuredSignoffFactory(
            beat=beat,
            player_data=player_data,
            treasured_subject=treasured,
            withdrawn_at=timezone.now(),
        )

        report = check_stake_boundaries([stake], [sheet])

        self.assertIn(sheet.pk, report.requires_signoff)

    def test_treasured_match_via_typed_subject_pointer(self):
        """NPC_FATE subjects match by subject_sheet FK, not subject_label."""
        beat = BeatFactory()
        sheet, tenure, _player_data = _sheet_with_player()
        npc_sheet = CharacterSheetFactory()
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=npc_sheet,
            subject_label="unrelated label text",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.NPC_FATE,
            subject_sheet=npc_sheet,
            subject_label="a totally different label",
        )

        report = check_stake_boundaries([stake], [sheet])

        self.assertIn(sheet.pk, report.requires_signoff)

    def test_untreasured_stake_never_requires_signoff(self):
        beat = BeatFactory()
        sheet, _tenure, _player_data = _sheet_with_player()
        stake = StakeFactory(beat=beat, template=None, subject_label="Nothing special")

        report = check_stake_boundaries([stake], [sheet])

        self.assertTrue(report.allowed)
        self.assertEqual(report.requires_signoff, ())
        self.assertTrue(report.cleared)


class EmptyInputTests(TestCase):
    def test_empty_stakes_allows(self):
        sheet, _tenure, _player_data = _sheet_with_player()
        report = check_stake_boundaries([], [sheet])
        self.assertTrue(report.allowed)
        self.assertTrue(report.cleared)

    def test_empty_sheets_allows(self):
        stake = StakeFactory()
        report = check_stake_boundaries([stake], [])
        self.assertTrue(report.allowed)
        self.assertTrue(report.cleared)
