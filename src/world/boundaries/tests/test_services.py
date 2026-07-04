"""Tests for world.boundaries.services (#1771 task 5).

Covers ``scene_lines_and_veils``: the anonymized, hard-line-free scene
aggregate over shared ADVISORY boundaries + treasured subjects.
"""

from django.test import TestCase

from world.boundaries.constants import BoundaryKind, TreasuredSubjectKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
)
from world.boundaries.services import scene_lines_and_veils
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.models import VisibilityMixin
from world.roster.factories import RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory


def _scene_participant():
    """A scene participant: (account, character_sheet, tenure, player_data)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(roster_entry=entry, end_date=None)
    return tenure.player_data.account, sheet, tenure, tenure.player_data


class SceneLinesAndVeilsTests(TestCase):
    def test_shared_advisory_boundary_is_included_and_owner_stripped(self):
        account, _sheet, _tenure, player_data = _scene_participant()
        theme = ContentThemeFactory(name="Body horror")
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.ADVISORY,
            theme=theme,
            detail="fine with implied, not graphic",
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )
        scene = SceneFactory(participants=[account])
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(len(result.advisories), 1)
        note = result.advisories[0]
        self.assertEqual(note.theme_name, "Body horror")
        self.assertEqual(note.detail, "fine with implied, not graphic")
        # Owner stripped: no field on the value object can carry it.
        self.assertNotIn("owner", vars(note))
        self.assertNotIn("player_data", vars(note))

    def test_hard_line_boundary_never_appears_even_if_marked_shareable(self):
        account, _sheet, _tenure, player_data = _scene_participant()
        theme = ContentThemeFactory()
        # Bypass model .clean() to simulate a would-be-invalid row; the service
        # must never surface a HARD_LINE row regardless of its visibility_mode.
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.HARD_LINE,
            theme=theme,
            detail="staff-only secret",
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )
        scene = SceneFactory(participants=[account])
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(result.advisories, ())

    def test_private_advisory_boundary_excluded(self):
        account, _sheet, _tenure, player_data = _scene_participant()
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.ADVISORY,
            theme=None,
            detail="never shared",
            visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE,
        )
        scene = SceneFactory(participants=[account])
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(result.advisories, ())

    def test_characters_mode_only_visible_to_named_tenure(self):
        account, _sheet, _tenure, player_data = _scene_participant()
        boundary = PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.ADVISORY,
            theme=None,
            detail="visible to one viewer only",
            visibility_mode=VisibilityMixin.VisibilityMode.CHARACTERS,
        )
        named_viewer = RosterTenureFactory()
        boundary.visible_to_tenures.add(named_viewer)
        stranger_viewer = RosterTenureFactory()
        scene = SceneFactory(participants=[account])

        stranger_result = scene_lines_and_veils(scene, stranger_viewer)
        named_result = scene_lines_and_veils(scene, named_viewer)

        self.assertEqual(stranger_result.advisories, ())
        self.assertEqual(len(named_result.advisories), 1)

    def test_shared_treasured_subject_is_included_and_owner_stripped(self):
        _account, _sheet, tenure, _player_data = _scene_participant()
        TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=TreasuredSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
            detail="means everything to them",
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )
        account = tenure.player_data.account
        scene = SceneFactory(participants=[account])
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(len(result.treasured_subjects), 1)
        note = result.treasured_subjects[0]
        self.assertEqual(note.subject_label, "Grandmother's locket")
        self.assertEqual(note.detail, "means everything to them")
        self.assertNotIn("owner", vars(note))

    def test_private_treasured_subject_excluded(self):
        _account, _sheet, tenure, _player_data = _scene_participant()
        TreasuredSubjectFactory(
            owner=tenure,
            visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE,
        )
        account = tenure.player_data.account
        scene = SceneFactory(participants=[account])
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(result.treasured_subjects, ())

    def test_no_participants_returns_empty_aggregate(self):
        scene = SceneFactory()
        viewer_tenure = RosterTenureFactory()

        result = scene_lines_and_veils(scene, viewer_tenure)

        self.assertEqual(result.advisories, ())
        self.assertEqual(result.treasured_subjects, ())
