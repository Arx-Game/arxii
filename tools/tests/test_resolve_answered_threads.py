"""Thread selection for the resolve-answered-threads workflow (#4510)."""

from __future__ import annotations

import unittest

from resolve_answered_threads import select_threads


def _c(login: str, typename: str = "User") -> dict:
    return {"author": {"login": login, "__typename": typename}, "body": "x"}


def _bot() -> dict:
    return _c("github-actions", "Bot")


def _thread(tid: str, comments: list[dict], resolved: bool = False) -> dict:
    return {"id": tid, "isResolved": resolved, "path": "a.py", "comments": {"nodes": comments}}


class SelectThreadsTests(unittest.TestCase):
    def ids(self, nodes: list[dict]) -> list[str]:
        return [t["id"] for t in select_threads(nodes)]

    def test_reviewer_thread_with_human_reply_is_selected(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_bot(), _c("tehom")])]), ["A"])

    def test_unanswered_reviewer_thread_is_left(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_bot()])]), [])

    def test_bot_only_reply_is_left(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_bot(), _bot()])]), [])

    def test_human_started_thread_is_never_touched(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_c("tehom"), _c("agent")])]), [])

    def test_other_bot_started_thread_is_left(self) -> None:
        other = _c("advanced-security", "Bot")
        self.assertEqual(self.ids([_thread("A", [other, _c("agent")])]), [])

    def test_already_resolved_is_skipped(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_bot(), _c("x")], True)]), [])

    def test_human_impersonating_the_login_is_not_the_reviewer(self) -> None:
        self.assertEqual(self.ids([_thread("A", [_c("github-actions"), _c("x")])]), [])


if __name__ == "__main__":
    unittest.main()
