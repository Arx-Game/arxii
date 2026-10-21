"""The board's "In progress" means active work, not assignment (#4539)."""

from __future__ import annotations

import unittest
from unittest import mock

import project_board_sync as sync


def issue(*labels: str, assigned: bool = True, state: str = "open", reason: str = "") -> dict:
    return {
        "number": 7,
        "node_id": "I_7",
        "state": state,
        "state_reason": reason,
        "assignees": [{"login": "owner"}] if assigned else [],
        "labels": [{"name": name} for name in labels],
    }


class ComputeStatusTests(unittest.TestCase):
    def test_assignment_alone_is_backlog(self) -> None:
        self.assertEqual(sync.compute_status(issue(assigned=True)), sync.STATUS_BACKLOG)

    def test_spec_review_waits_in_backlog(self) -> None:
        self.assertEqual(sync.compute_status(issue("status:spec-review")), sync.STATUS_BACKLOG)

    def test_claimed_label_alone_is_not_activity(self) -> None:
        self.assertEqual(sync.compute_status(issue("status:in-progress")), sync.STATUS_BACKLOG)

    def test_spec_draft_and_implementing_are_in_progress(self) -> None:
        for label in ("status:spec-draft", "status:implementing"):
            with self.subTest(label=label):
                self.assertEqual(
                    sync.compute_status(issue(label, assigned=False)),
                    sync.STATUS_IN_PROGRESS,
                )

    def test_open_linked_pr_is_in_progress(self) -> None:
        self.assertEqual(sync.compute_status(issue(), has_open_pr=True), sync.STATUS_IN_PROGRESS)

    def test_closed_stays_terminal_even_with_active_label(self) -> None:
        self.assertEqual(
            sync.compute_status(issue("status:implementing", state="closed")),
            sync.STATUS_DONE,
        )
        self.assertEqual(
            sync.compute_status(issue(state="closed", reason="not_planned")),
            sync.STATUS_CANCELLED,
        )


class ClaimedLabelTests(unittest.TestCase):
    """The status:in-progress label follows the rule, via idempotent label writes."""

    def run_issue_event(self, payload: dict, open_pr: bool = False) -> list[tuple]:
        calls: list[tuple] = []
        with (
            mock.patch.object(sync, "ensure_item", return_value="item"),
            mock.patch.object(sync, "has_open_linked_pr", return_value=open_pr),
            mock.patch.object(sync, "set_single_select"),
            mock.patch.object(sync, "clear_field"),
            mock.patch.object(sync, "current_value", return_value=None),
            mock.patch.object(
                sync,
                "set_issue_labels",
                side_effect=lambda _r, _n, add, remove: calls.append((add, remove)),
            ),
        ):
            sync.handle_issue(mock.Mock(), "o/r", {"action": "assigned", "issue": payload})
        return calls

    def test_assignment_alone_adds_no_label_and_removes_it(self) -> None:
        self.assertEqual(self.run_issue_event(issue()), [([], [sync.CLAIMED_LABEL])])

    def test_spec_draft_adds_label(self) -> None:
        self.assertEqual(
            self.run_issue_event(issue("status:spec-draft")), [([sync.CLAIMED_LABEL], [])]
        )

    def test_open_pr_adds_label(self) -> None:
        self.assertEqual(self.run_issue_event(issue(), open_pr=True), [([sync.CLAIMED_LABEL], [])])

    def test_closed_issue_labels_untouched(self) -> None:
        self.assertEqual(self.run_issue_event(issue(state="closed")), [])


class PullRequestTests(unittest.TestCase):
    def run_pr(
        self,
        action: str,
        labels: list[str],
        other_prs: list[dict],
        merged: bool = False,
        board_status: str | None = None,
    ):
        ref = {
            "number": 7,
            "node_id": "I_7",
            "state": "OPEN",
            "labels": {"nodes": [{"name": n} for n in labels]},
            "closedByPullRequestsReferences": {"nodes": other_prs},
        }
        data = {
            "repository": {
                "pullRequest": {"merged": merged, "closingIssuesReferences": {"nodes": [ref]}}
            }
        }
        statuses: list[str] = []
        labels_calls: list[tuple] = []
        with (
            mock.patch.object(sync, "gql", return_value=data),
            mock.patch.object(sync, "ensure_item", return_value="item"),
            mock.patch.object(sync, "clear_field"),
            mock.patch.object(
                sync,
                "current_value",
                side_effect=lambda _i, f: board_status if f == "Status" else None,
            ),
            mock.patch.object(
                sync,
                "set_single_select",
                side_effect=lambda _b, _i, f, o: statuses.append(o) if f == "Status" else None,
            ),
            mock.patch.object(
                sync,
                "set_issue_labels",
                side_effect=lambda _r, _n, add, remove: labels_calls.append((add, remove)),
            ),
        ):
            sync.handle_pull_request(
                mock.Mock(), "o/r", {"action": action, "pull_request": {"number": 50}}
            )
        return statuses, labels_calls

    def test_opened_makes_issue_active(self) -> None:
        statuses, labels = self.run_pr("opened", [], [])
        self.assertEqual(statuses, [sync.STATUS_IN_PROGRESS])
        self.assertEqual(labels, [([sync.CLAIMED_LABEL], [])])

    def test_active_issue_is_never_downgraded_from_in_review(self) -> None:
        statuses, _ = self.run_pr("reopened", [], [], board_status=sync.STATUS_IN_REVIEW)
        self.assertEqual(statuses, [])

    def test_stale_in_review_with_active_label_is_recomputed_when_pr_closes(self) -> None:
        statuses, _ = self.run_pr(
            "closed", ["status:implementing"], [], board_status=sync.STATUS_IN_REVIEW
        )
        self.assertEqual(statuses, [sync.STATUS_IN_PROGRESS])

    def test_closed_unmerged_with_no_active_label_goes_back_to_backlog(self) -> None:
        statuses, labels = self.run_pr("closed", ["status:spec-review"], [])
        self.assertEqual(statuses, [sync.STATUS_BACKLOG])
        self.assertEqual(labels, [([], [sync.CLAIMED_LABEL])])

    def test_closed_unmerged_with_active_label_stays_in_progress(self) -> None:
        statuses, labels = self.run_pr("closed", ["status:implementing"], [])
        self.assertEqual(statuses, [sync.STATUS_IN_PROGRESS])
        self.assertEqual(labels, [([sync.CLAIMED_LABEL], [])])

    def test_closed_unmerged_with_another_open_pr_stays_in_progress(self) -> None:
        statuses, _ = self.run_pr("closed", [], [{"number": 51, "state": "OPEN"}])
        self.assertEqual(statuses, [sync.STATUS_IN_PROGRESS])

    def test_merged_pr_is_left_to_the_issue_close(self) -> None:
        self.assertEqual(self.run_pr("closed", [], [], merged=True), ([], []))


if __name__ == "__main__":
    unittest.main()
