"""Staff GitHub-issue filing from reports (#1164)."""

from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from evennia_extensions.factories import AccountFactory
from world.player_submissions.factories import BugReportFactory, SystemErrorReportFactory
from world.player_submissions.github_issues import (
    GitHubIssueError,
    create_github_issue,
    issue_draft_for_bug,
    issue_draft_for_error,
    redact_text,
)

_BUG = "/api/player-submissions/bug-reports"
_ERR = "/api/player-submissions/system-errors"


class RedactionTests(TestCase):
    def test_strips_names_case_insensitively(self) -> None:
        text = "Bob saw it. bob clicked again."
        assert redact_text(text, ["Bob"]) == "[redacted] saw it. [redacted] clicked again."

    def test_ignores_empty_names(self) -> None:
        assert redact_text("unchanged", [""]) == "unchanged"


class DraftTests(TestCase):
    def test_bug_draft_strips_reporter_identity(self) -> None:
        report = BugReportFactory()
        name = report.reporter_persona.name
        username = report.reporter_account.username
        report.description = f"{name} ({username}) hit a softlock in the tavern."
        report.save(update_fields=["description"])

        draft = issue_draft_for_bug(report)

        assert name not in draft.body
        assert username not in draft.body
        assert "softlock in the tavern" in draft.body
        assert f"#{report.pk}" in draft.title
        # The omit-details stub withholds the description entirely.
        assert "softlock" not in draft.stub_body

    def test_error_draft_includes_traceback_but_stub_omits_it(self) -> None:
        report = SystemErrorReportFactory(traceback="Traceback X\n  raise ValueError")

        draft = issue_draft_for_error(report)

        assert "ValueError" in draft.title
        assert "Traceback X" in draft.body
        assert "Traceback X" not in draft.stub_body


class CreateGithubIssueTests(TestCase):
    @patch("world.player_submissions.github_issues.requests.post")
    def test_success_returns_number_and_url(self, mock_post) -> None:
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {"number": 42, "html_url": "https://gh/42"}
        with self.settings(GITHUB_ISSUE_TOKEN="tok", GITHUB_ISSUE_REPO="o/r"):
            number, url = create_github_issue(title="t", body="b", labels=["bug"])
        assert (number, url) == (42, "https://gh/42")

    def test_unconfigured_token_raises(self) -> None:
        with self.settings(GITHUB_ISSUE_TOKEN=""), self.assertRaises(GitHubIssueError):
            create_github_issue(title="t", body="b", labels=[])

    @patch("world.player_submissions.github_issues.requests.post")
    def test_rejected_status_raises(self, mock_post) -> None:
        mock_post.return_value.status_code = 422
        with self.settings(GITHUB_ISSUE_TOKEN="tok"), self.assertRaises(GitHubIssueError):
            create_github_issue(title="t", body="b", labels=[])


class FileIssueActionTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        cls.staff = AccountFactory(username="ghstaff", is_staff=True)
        cls.regular = AccountFactory(username="ghregular")

    def _post(self, account, url, body=None):
        client = APIClient()
        client.force_authenticate(user=account)
        payload = body if body is not None else {"title": "T", "body": "B"}
        return client.post(url, payload, format="json")

    def test_staff_files_bug_issue(self) -> None:
        report = BugReportFactory()
        with patch(
            "world.player_submissions.github_issues.create_github_issue",
            return_value=(7, "https://gh/7"),
        ) as mock_create:
            response = self._post(self.staff, f"{_BUG}/{report.pk}/file-issue/")
        assert response.status_code == 201
        mock_create.assert_called_once()
        report.refresh_from_db()
        assert report.github_issue_number == 7
        assert report.github_issue_url == "https://gh/7"

    def test_staff_files_system_error_issue(self) -> None:
        report = SystemErrorReportFactory()
        with patch(
            "world.player_submissions.github_issues.create_github_issue",
            return_value=(9, "https://gh/9"),
        ):
            response = self._post(self.staff, f"{_ERR}/{report.pk}/file-issue/")
        assert response.status_code == 201
        report.refresh_from_db()
        assert report.github_issue_url == "https://gh/9"

    def test_idempotent_returns_existing_without_refiling(self) -> None:
        report = BugReportFactory(github_issue_number=5, github_issue_url="https://gh/5")
        with patch("world.player_submissions.github_issues.create_github_issue") as mock_create:
            response = self._post(self.staff, f"{_BUG}/{report.pk}/file-issue/")
        assert response.status_code == 200
        mock_create.assert_not_called()
        assert response.data["github_issue_url"] == "https://gh/5"

    def test_non_staff_forbidden(self) -> None:
        report = BugReportFactory()
        response = self._post(self.regular, f"{_BUG}/{report.pk}/file-issue/")
        assert response.status_code == 403

    def test_github_failure_surfaces_502_with_safe_message(self) -> None:
        report = BugReportFactory()
        with patch(
            "world.player_submissions.github_issues.create_github_issue",
            side_effect=GitHubIssueError("could not reach GitHub"),
        ):
            response = self._post(self.staff, f"{_BUG}/{report.pk}/file-issue/")
        assert response.status_code == 502
        assert response.data["detail"] == "could not reach GitHub"

    def test_missing_fields_rejected(self) -> None:
        report = BugReportFactory()
        response = self._post(self.staff, f"{_BUG}/{report.pk}/file-issue/", body={})
        assert response.status_code == 400

    def test_detail_exposes_issue_draft_and_link_fields(self) -> None:
        report = BugReportFactory(github_issue_number=3, github_issue_url="https://gh/3")
        client = APIClient()
        client.force_authenticate(user=self.staff)
        response = client.get(f"{_BUG}/{report.pk}/")
        assert response.status_code == 200
        assert response.data["github_issue_url"] == "https://gh/3"
        assert response.data["issue_draft"]["title"]
        assert "stub_body" in response.data["issue_draft"]
