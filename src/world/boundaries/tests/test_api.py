"""API tests for the boundaries DRF surfaces (#1771 task 6) — privacy-critical.

Covers /api/boundaries/ (PlayerBoundary/TreasuredSubject/ContentTheme CRUD +
the scene lines-and-veils aggregate) plus the sign-off grant/withdraw and
GM stake-availability endpoints.

The latter two are mounted under world.stories' own router
(world/stories/views.py TreasuredSignoffViewSet / BeatStakeAvailabilityView)
rather than world.boundaries — they operate on stories-owned models (Beat,
TreasuredSignoff) and call world.stories.services.boundaries, so putting
them in world.boundaries would make that app import world.stories, which
ADR-0010's FK direction (specific->general) forbids. This mirrors Task 5's
identical call for the underlying service functions themselves (see
world/stories/services/boundaries.py). This test file still exercises them
here per the task brief's stated test-file location.

The PRIVACY tests are the point (ADR-0033):
- a non-owner GET of another player's boundary never returns its detail/
  theme/hard-line row (owner-scoped queryset -> 404, not a filtered field).
- the scene aggregate omits owner identity and structurally excludes hard
  lines (the underlying service never queries kind=HARD_LINE).
- the GM stake-availability read returns COUNTS ONLY -- no reason, no
  player/stake identifier, and blocked_reason_private appears nowhere.
"""

from types import SimpleNamespace

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from world.boundaries.constants import BoundaryKind, TreasuredSubjectKind
from world.boundaries.factories import (
    ContentThemeFactory,
    PlayerBoundaryFactory,
    TreasuredSubjectFactory,
)
from world.boundaries.models import PlayerBoundary, TreasuredSubject
from world.character_sheets.factories import CharacterSheetFactory
from world.consent.models import VisibilityMixin
from world.roster.factories import PlayerDataFactory, RosterEntryFactory, RosterTenureFactory
from world.scenes.factories import SceneFactory
from world.stories.constants import StakeSubjectKind
from world.stories.factories import BeatFactory, StakeFactory, StakeTemplateFactory
from world.stories.models import TreasuredSignoff


def _api_user(player_data=None, *, is_staff=False):
    """A minimal request.user stand-in matching world.consent's test convention.

    ``id`` mirrors the account id when a ``player_data`` is given (needed by
    ``world.stories.permissions.user_owns_beat_story``'s
    ``story.owners.filter(id=user.id)`` walk); ``None`` otherwise, which
    simply never matches any story owner.
    """
    account_id = player_data.account_id if player_data is not None else None
    return SimpleNamespace(
        is_authenticated=True, is_staff=is_staff, player_data=player_data, id=account_id
    )


def _sheet_with_tenure(player_data=None):
    """A CharacterSheet with a live tenure (roster_entry -> tenure -> player_data)."""
    sheet = CharacterSheetFactory()
    entry = RosterEntryFactory(character_sheet=sheet)
    tenure = RosterTenureFactory(
        roster_entry=entry,
        player_data=player_data or PlayerDataFactory(),
        end_date=None,
    )
    return sheet, tenure


class ContentThemeViewSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = PlayerDataFactory()
        cls.theme = ContentThemeFactory(key="body-horror", name="Body horror")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=_api_user(self.player))

    def test_unauthenticated_returns_401_or_403(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/boundaries/content-themes/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_content_themes(self):
        response = self.client.get("/api/boundaries/content-themes/")
        assert response.status_code == status.HTTP_200_OK
        keys = [row["key"] for row in response.data["results"]]
        assert "body-horror" in keys

    def test_content_themes_read_only(self):
        response = self.client.post(
            "/api/boundaries/content-themes/",
            {"key": "new-theme", "name": "New"},
            format="json",
        )
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


class PlayerBoundaryViewSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = PlayerDataFactory()
        cls.other_player = PlayerDataFactory()
        cls.theme = ContentThemeFactory(key="a-theme", name="A Theme")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=_api_user(self.player))

    def test_unauthenticated_returns_401_or_403(self):
        self.client.force_authenticate(user=None)
        response = self.client.get("/api/boundaries/player-boundaries/")
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_list_returns_only_own_boundaries(self):
        PlayerBoundaryFactory(owner=self.player, kind=BoundaryKind.ADVISORY, theme=None)
        PlayerBoundaryFactory(owner=self.other_player, kind=BoundaryKind.ADVISORY, theme=None)

        response = self.client.get("/api/boundaries/player-boundaries/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_owner_can_create_hard_line(self):
        response = self.client.post(
            "/api/boundaries/player-boundaries/",
            {
                "kind": BoundaryKind.HARD_LINE,
                "theme": self.theme.pk,
                "detail": "no depictions of X",
                "visibility_mode": PlayerBoundary.VisibilityMode.PRIVATE,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert PlayerBoundary.objects.filter(owner=self.player, theme=self.theme).exists()
        # owner is never client-writable
        created = PlayerBoundary.objects.get(owner=self.player, theme=self.theme)
        assert created.owner_id == self.player.pk

    def test_owner_field_ignored_on_create(self):
        response = self.client.post(
            "/api/boundaries/player-boundaries/",
            {
                "owner": self.other_player.pk,
                "kind": BoundaryKind.ADVISORY,
                "detail": "advisory text",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        created = PlayerBoundary.objects.get(pk=response.data["id"])
        assert created.owner_id == self.player.pk

    def test_hard_line_must_be_private(self):
        response = self.client.post(
            "/api/boundaries/player-boundaries/",
            {
                "kind": BoundaryKind.HARD_LINE,
                "theme": self.theme.pk,
                "detail": "x",
                "visibility_mode": PlayerBoundary.VisibilityMode.PUBLIC,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_hard_line_requires_theme(self):
        response = self.client.post(
            "/api/boundaries/player-boundaries/",
            {"kind": BoundaryKind.HARD_LINE, "detail": "x"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_retrieve_returns_404_no_leak(self):
        boundary = PlayerBoundaryFactory(
            owner=self.other_player,
            kind=BoundaryKind.HARD_LINE,
            theme=self.theme,
            detail="staff-only secret detail",
            visibility_mode=PlayerBoundary.VisibilityMode.PRIVATE,
        )

        response = self.client.get(f"/api/boundaries/player-boundaries/{boundary.pk}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "staff-only secret detail" not in response.content.decode()

    def test_non_owner_list_never_contains_other_players_hard_line_rows(self):
        PlayerBoundaryFactory(
            owner=self.other_player,
            kind=BoundaryKind.HARD_LINE,
            theme=self.theme,
            detail="staff-only secret detail",
            visibility_mode=PlayerBoundary.VisibilityMode.PRIVATE,
        )

        response = self.client.get("/api/boundaries/player-boundaries/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"] == []
        assert "staff-only secret detail" not in response.content.decode()

    def test_non_owner_cannot_patch_or_delete(self):
        boundary = PlayerBoundaryFactory(owner=self.other_player, kind=BoundaryKind.ADVISORY)

        patch_response = self.client.patch(
            f"/api/boundaries/player-boundaries/{boundary.pk}/",
            {"detail": "hijacked"},
            format="json",
        )
        delete_response = self.client.delete(f"/api/boundaries/player-boundaries/{boundary.pk}/")

        assert patch_response.status_code == status.HTTP_404_NOT_FOUND
        assert delete_response.status_code == status.HTTP_404_NOT_FOUND
        boundary.refresh_from_db()
        assert boundary.detail != "hijacked"

    def test_owner_can_update_own_boundary(self):
        boundary = PlayerBoundaryFactory(owner=self.player, kind=BoundaryKind.ADVISORY, theme=None)

        response = self.client.patch(
            f"/api/boundaries/player-boundaries/{boundary.pk}/",
            {"detail": "updated"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        boundary.refresh_from_db()
        assert boundary.detail == "updated"

    def test_owner_can_delete_own_boundary(self):
        boundary = PlayerBoundaryFactory(owner=self.player, kind=BoundaryKind.ADVISORY, theme=None)

        response = self.client.delete(f"/api/boundaries/player-boundaries/{boundary.pk}/")

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not PlayerBoundary.objects.filter(pk=boundary.pk).exists()


class TreasuredSubjectViewSetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.player = PlayerDataFactory()
        cls.other_player = PlayerDataFactory()
        _sheet, cls.tenure = _sheet_with_tenure(cls.player)
        _other_sheet, cls.other_tenure = _sheet_with_tenure(cls.other_player)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=_api_user(self.player))

    def test_list_returns_only_own_treasured_subjects(self):
        TreasuredSubjectFactory(owner=self.tenure, subject_kind=TreasuredSubjectKind.CUSTOM)
        TreasuredSubjectFactory(owner=self.other_tenure, subject_kind=TreasuredSubjectKind.CUSTOM)

        response = self.client.get("/api/boundaries/treasured-subjects/")

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1

    def test_owner_can_create_for_own_tenure(self):
        response = self.client.post(
            "/api/boundaries/treasured-subjects/",
            {
                "owner": self.tenure.pk,
                "subject_kind": TreasuredSubjectKind.CUSTOM,
                "subject_label": "Grandmother's locket",
                "detail": "means everything",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert TreasuredSubject.objects.filter(owner=self.tenure).exists()

    def test_create_for_other_players_tenure_rejected(self):
        response = self.client.post(
            "/api/boundaries/treasured-subjects/",
            {
                "owner": self.other_tenure.pk,
                "subject_kind": TreasuredSubjectKind.CUSTOM,
                "subject_label": "Not yours",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_owner_retrieve_returns_404_no_leak(self):
        subject = TreasuredSubjectFactory(
            owner=self.other_tenure,
            subject_kind=TreasuredSubjectKind.CUSTOM,
            subject_label="Their secret treasure",
            detail="their private nuance",
        )

        response = self.client.get(f"/api/boundaries/treasured-subjects/{subject.pk}/")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "their private nuance" not in response.content.decode()


class SceneLinesAndVeilsViewTests(TestCase):
    def _participant(self):
        sheet, tenure = _sheet_with_tenure()
        return tenure.player_data.account, sheet, tenure, tenure.player_data

    def setUp(self):
        self.client = APIClient()

    def test_scene_aggregate_omits_owner_and_hard_lines(self):
        account, _sheet, _tenure, player_data = self._participant()
        theme = ContentThemeFactory(name="Body horror")
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.ADVISORY,
            theme=theme,
            detail="fine with implied, not graphic",
            visibility_mode=VisibilityMixin.VisibilityMode.PUBLIC,
        )
        PlayerBoundaryFactory(
            owner=player_data,
            kind=BoundaryKind.HARD_LINE,
            theme=theme,
            detail="staff-only secret hard line",
            visibility_mode=VisibilityMixin.VisibilityMode.PRIVATE,
        )
        scene = SceneFactory(participants=[account])
        viewer_player = PlayerDataFactory()
        _viewer_sheet, viewer_tenure = _sheet_with_tenure(viewer_player)
        self.client.force_authenticate(user=_api_user(viewer_player))

        response = self.client.get(
            f"/api/boundaries/scenes/{scene.pk}/lines-and-veils/?tenure={viewer_tenure.pk}"
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["advisories"]) == 1
        assert response.data["advisories"][0]["theme_name"] == "Body horror"
        assert response.data["advisories"][0]["detail"] == "fine with implied, not graphic"
        body = response.content.decode()
        assert "staff-only secret hard line" not in body
        assert "owner" not in response.data["advisories"][0]
        assert "player_data" not in response.data["advisories"][0]

    def test_lines_and_veils_requires_own_tenure(self):
        _account, _sheet, _tenure, player_data = self._participant()
        scene = SceneFactory()
        other_player = PlayerDataFactory()
        _other_sheet, other_tenure = _sheet_with_tenure(other_player)
        self.client.force_authenticate(user=_api_user(player_data))

        response = self.client.get(
            f"/api/boundaries/scenes/{scene.pk}/lines-and-veils/?tenure={other_tenure.pk}"
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND


class TreasuredSignoffAPITests(TestCase):
    """Grant/withdraw endpoints, and their reflection in requires_signoff."""

    def setUp(self):
        self.client = APIClient()

    def _treasured_stake_fixture(self):
        from world.stories.services.boundaries import check_stake_boundaries

        self.check_stake_boundaries = check_stake_boundaries
        player_data = PlayerDataFactory()
        sheet, tenure = _sheet_with_tenure(player_data)
        beat = BeatFactory()
        treasured = TreasuredSubjectFactory(
            owner=tenure,
            subject_kind=TreasuredSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        stake = StakeFactory(
            beat=beat,
            template=None,
            subject_kind=StakeSubjectKind.CUSTOM,
            subject_label="Grandmother's locket",
        )
        return player_data, sheet, beat, treasured, stake

    def test_grant_clears_requires_signoff(self):
        player_data, sheet, beat, treasured, stake = self._treasured_stake_fixture()
        self.client.force_authenticate(user=_api_user(player_data))

        before = self.check_stake_boundaries([stake], [sheet])
        assert sheet.pk in before.requires_signoff

        response = self.client.post(
            "/api/treasured-signoffs/",
            {"beat": beat.pk, "treasured_subject": treasured.pk},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["active"] is True

        after = self.check_stake_boundaries([stake], [sheet])
        assert sheet.pk not in after.requires_signoff
        assert after.cleared

    def test_withdraw_restores_requires_signoff(self):
        player_data, sheet, beat, treasured, stake = self._treasured_stake_fixture()
        self.client.force_authenticate(user=_api_user(player_data))
        grant_response = self.client.post(
            "/api/treasured-signoffs/",
            {"beat": beat.pk, "treasured_subject": treasured.pk},
            format="json",
        )
        signoff_id = grant_response.data["id"]

        withdraw_response = self.client.post(f"/api/treasured-signoffs/{signoff_id}/withdraw/")

        assert withdraw_response.status_code == status.HTTP_200_OK
        assert withdraw_response.data["active"] is False
        after = self.check_stake_boundaries([stake], [sheet])
        assert sheet.pk in after.requires_signoff

    def test_cannot_signoff_for_someone_elses_treasured_subject(self):
        _player_data, _sheet, beat, treasured, _stake = self._treasured_stake_fixture()
        other_player = PlayerDataFactory()
        self.client.force_authenticate(user=_api_user(other_player))

        response = self.client.post(
            "/api/treasured-signoffs/",
            {"beat": beat.pk, "treasured_subject": treasured.pk},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not TreasuredSignoff.objects.filter(beat=beat, player_data=other_player).exists()


class BeatStakeAvailabilityViewTests(TestCase):
    """GM-facing counts-only tally — never a reason, never blocked_reason_private."""

    def setUp(self):
        self.client = APIClient()

    def test_availability_returns_counts_only_and_never_leaks_reason(self):
        theme = ContentThemeFactory(name="Very Specific Secret Theme")
        template = StakeTemplateFactory()
        template.content_themes.add(theme)
        player_data = PlayerDataFactory()
        sheet, _tenure = _sheet_with_tenure(player_data)
        PlayerBoundaryFactory(owner=player_data, kind=BoundaryKind.HARD_LINE, theme=theme)
        beat = BeatFactory()
        StakeFactory(beat=beat, template=template)

        self.client.force_authenticate(user=_api_user(is_staff=True))
        response = self.client.get(f"/api/beats/{beat.pk}/stake-availability/?sheets={sheet.pk}")

        assert response.status_code == status.HTTP_200_OK
        assert set(response.data.keys()) == {"available", "blocked", "needs_signoff"}
        assert response.data["blocked"] == 1
        body = response.content.decode()
        assert "blocked_reason_private" not in body
        assert theme.name not in body

    def test_availability_requires_staff_or_story_owner(self):
        beat = BeatFactory()
        player_data = PlayerDataFactory()
        self.client.force_authenticate(user=_api_user(player_data))

        response = self.client.get(f"/api/beats/{beat.pk}/stake-availability/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
