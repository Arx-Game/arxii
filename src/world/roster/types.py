"""Type declarations for the roster system."""

from typing import TypedDict


class PolicyIssue(TypedDict):
    code: str
    message: str


class PolicyInfo(TypedDict):
    basic_eligibility: str
    policy_issues: list[PolicyIssue]
    requires_staff_review: bool
    auto_approvable: bool
    player_current_characters: list[str]
    character_previous_players: int
