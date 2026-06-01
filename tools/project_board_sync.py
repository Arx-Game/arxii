#!/usr/bin/env python3
"""Sync the org Project (board) with issue/PR lifecycle.

Drives the Project's ``Status`` (lifecycle columns) and ``Stage`` (swimlanes)
fields from GitHub events plus our ``status:*`` / ``spec:*`` labels. See
``docs/project-board-automation.md`` for the full design and the one manual
setup step (the ``PROJECT_PAT`` secret + the ``Cancelled`` Status option).

Two modes:

* ``event``    (default) — react to the GitHub Actions event in
  ``GITHUB_EVENT_PATH`` (``issues`` or ``pull_request``).
* ``backfill`` — one-time sweep: add every open issue to the board and set its
  Status/Stage from current assignment + labels.

Everything is resolved by *name* at runtime (project, fields, options), so the
script keeps working when option IDs change or the ``Cancelled`` option is
added later. Writes are idempotent: a field/label is only changed when it
differs from the desired value, so re-runs triggered by our own PAT writes are
no-ops and terminate.

Stdlib only — runs on a bare GitHub runner with no ``pip install``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

GRAPHQL_URL = "https://api.github.com/graphql"
REST_ROOT = "https://api.github.com"

# --- lifecycle vocabulary (must match the names on the board / our labels) ---

STATUS_BACKLOG = "Backlog"
STATUS_IN_PROGRESS = "In progress"
STATUS_DONE = "Done"
STATUS_CANCELLED = "Cancelled"

STAGE_SPEC_DESIGN = "Spec design"
STAGE_SPEC_REVIEW = "Spec review"
STAGE_IMPLEMENTATION = "Implementation"
STAGE_IN_REVIEW = "In review"

CLAIMED_LABEL = "status:in-progress"

# Label -> Stage, highest lifecycle priority first.
STAGE_BY_LABEL = [
    (("spec:approved", "status:implementing"), STAGE_IMPLEMENTATION),
    (("status:spec-review",), STAGE_SPEC_REVIEW),
    (("status:spec-draft",), STAGE_SPEC_DESIGN),
]


class GitHubError(RuntimeError):
    pass


def _token() -> str:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        # Fork PRs and missing-secret setups land here. Exit cleanly so the
        # check is green for external contributors instead of a scary red X.
        print(
            "PROJECT_PAT/GITHUB_TOKEN not available (fork PR or secret not set) "
            "- skipping board sync.",
            file=sys.stderr,
        )
        raise SystemExit(0)
    return token


def _request(url: str, payload: dict | None, method: str) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    # S310: url is always a hardcoded https api.github.com endpoint (constants above).
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    req.add_header("Authorization", f"Bearer {_token()}")
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310
            body = resp.read().decode()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        msg = f"{method} {url} -> {exc.code}: {detail}"
        raise GitHubError(msg) from exc
    return json.loads(body) if body else {}


def gql(query: str, variables: dict) -> dict:
    result = _request(GRAPHQL_URL, {"query": query, "variables": variables}, "POST")
    if result.get("errors"):
        msg = f"GraphQL errors: {json.dumps(result['errors'])}"
        raise GitHubError(msg)
    return result["data"]


# --------------------------------------------------------------------------- #
# Project metadata                                                            #
# --------------------------------------------------------------------------- #


class Board:
    """Resolved project id + single-select field/option ids, looked up by name."""

    def __init__(self, org: str, number: int):
        data = gql(
            """
            query($org:String!, $num:Int!) {
              organization(login:$org) {
                projectV2(number:$num) {
                  id
                  fields(first:50) {
                    nodes {
                      ... on ProjectV2SingleSelectField {
                        id name options { id name }
                      }
                    }
                  }
                }
              }
            }
            """,
            {"org": org, "num": number},
        )
        project = data["organization"]["projectV2"]
        if not project:
            msg = f"No project #{number} on org {org}"
            raise GitHubError(msg)
        self.id: str = project["id"]
        # field name -> {"id": ..., "options": {option name: option id}}
        self.fields: dict[str, dict] = {}
        for node in project["fields"]["nodes"]:
            if node and node.get("name"):
                self.fields[node["name"]] = {
                    "id": node["id"],
                    "options": {o["name"]: o["id"] for o in node.get("options", [])},
                }

    def option_id(self, field: str, option: str) -> str | None:
        spec = self.fields.get(field)
        if not spec:
            return None
        return spec["options"].get(option)

    def field_id(self, field: str) -> str | None:
        spec = self.fields.get(field)
        return spec["id"] if spec else None


# --------------------------------------------------------------------------- #
# Item helpers                                                                #
# --------------------------------------------------------------------------- #


def ensure_item(board: Board, content_id: str) -> str:
    """Return the project item id for an issue/PR node, adding it if missing."""
    data = gql(
        """
        query($id:ID!) {
          node(id:$id) {
            ... on Issue { projectItems(first:20) { nodes { id project { id } } } }
            ... on PullRequest { projectItems(first:20) { nodes { id project { id } } } }
          }
        }
        """,
        {"id": content_id},
    )
    for item in data["node"]["projectItems"]["nodes"]:
        if item["project"]["id"] == board.id:
            return item["id"]
    added = gql(
        """
        mutation($proj:ID!, $content:ID!) {
          addProjectV2ItemById(input:{projectId:$proj, contentId:$content}) {
            item { id }
          }
        }
        """,
        {"proj": board.id, "content": content_id},
    )
    return added["addProjectV2ItemById"]["item"]["id"]


def current_value(item_id: str, field_name: str) -> str | None:
    data = gql(
        """
        query($id:ID!, $field:String!) {
          node(id:$id) {
            ... on ProjectV2Item {
              fieldValueByName(name:$field) {
                ... on ProjectV2ItemFieldSingleSelectValue { name }
              }
            }
          }
        }
        """,
        {"id": item_id, "field": field_name},
    )
    value = data["node"]["fieldValueByName"]
    return value["name"] if value else None


def set_single_select(board: Board, item_id: str, field_name: str, option_name: str) -> None:
    """Set a single-select field by name, only if it differs (idempotent)."""
    if current_value(item_id, field_name) == option_name:
        return
    option_id = board.option_id(field_name, option_name)
    if option_id is None:
        print(
            f"  ! option {field_name!r}={option_name!r} missing on the board - "
            "add it in Project settings; leaving the field unchanged.",
            file=sys.stderr,
        )
        return
    gql(
        """
        mutation($proj:ID!, $item:ID!, $field:ID!, $opt:String!) {
          updateProjectV2ItemFieldValue(input:{
            projectId:$proj, itemId:$item, fieldId:$field,
            value:{ singleSelectOptionId:$opt }
          }) { projectV2Item { id } }
        }
        """,
        {"proj": board.id, "item": item_id, "field": board.field_id(field_name), "opt": option_id},
    )
    print(f"  -> {field_name} = {option_name}")


def clear_field(board: Board, item_id: str, field_name: str) -> None:
    if current_value(item_id, field_name) is None:
        return
    gql(
        """
        mutation($proj:ID!, $item:ID!, $field:ID!) {
          clearProjectV2ItemFieldValue(input:{
            projectId:$proj, itemId:$item, fieldId:$field
          }) { projectV2Item { id } }
        }
        """,
        {"proj": board.id, "item": item_id, "field": board.field_id(field_name)},
    )
    print(f"  -> {field_name} cleared")


def set_issue_labels(repo: str, number: int, add: list[str], remove: list[str]) -> None:
    """Add/remove labels via REST, only touching what needs to change."""
    current = {
        label["name"]
        for label in _request(f"{REST_ROOT}/repos/{repo}/issues/{number}/labels", None, "GET")
    }
    for name in add:
        if name not in current:
            _request(
                f"{REST_ROOT}/repos/{repo}/issues/{number}/labels",
                {"labels": [name]},
                "POST",
            )
            print(f"  -> +label {name}")
    for name in remove:
        if name in current:
            url = f"{REST_ROOT}/repos/{repo}/issues/{number}/labels/{urllib.parse.quote(name)}"
            _request(url, None, "DELETE")
            print(f"  -> -label {name}")


# --------------------------------------------------------------------------- #
# Lifecycle computation                                                       #
# --------------------------------------------------------------------------- #


def compute_status(issue: dict) -> str:
    if issue.get("state") == "closed":
        return STATUS_CANCELLED if issue.get("state_reason") == "not_planned" else STATUS_DONE
    if issue.get("assignees"):
        return STATUS_IN_PROGRESS
    return STATUS_BACKLOG


def compute_stage(label_names: set[str]) -> str | None:
    for triggers, stage in STAGE_BY_LABEL:
        if any(t in label_names for t in triggers):
            return stage
    return None


def label_names_of(issue: dict) -> set[str]:
    return {label["name"] for label in issue.get("labels", [])}


# --------------------------------------------------------------------------- #
# Event handlers                                                              #
# --------------------------------------------------------------------------- #


def handle_issue(board: Board, repo: str, event: dict) -> None:
    issue = event["issue"]
    action = event["action"]
    number = issue["number"]
    print(f"issue #{number} action={action}")
    item_id = ensure_item(board, issue["node_id"])

    set_single_select(board, item_id, "Status", compute_status(issue))

    # Stage is label-driven, but "In review" is owned by the PR handler - never
    # let an issue event downgrade it (only the PR closing does).
    if issue.get("state") != "closed" and current_value(item_id, "Stage") != STAGE_IN_REVIEW:
        stage = compute_stage(label_names_of(issue))
        if stage:
            set_single_select(board, item_id, "Stage", stage)
        else:
            clear_field(board, item_id, "Stage")

    if action == "assigned":
        set_issue_labels(repo, number, add=[CLAIMED_LABEL], remove=[])
    elif action == "unassigned" and not issue.get("assignees"):
        set_issue_labels(repo, number, add=[], remove=[CLAIMED_LABEL])


def handle_pull_request(board: Board, repo: str, event: dict) -> None:
    pr = event["pull_request"]
    action = event["action"]
    owner, name = repo.split("/")
    data = gql(
        """
        query($owner:String!, $repo:String!, $num:Int!) {
          repository(owner:$owner, name:$repo) {
            pullRequest(number:$num) {
              merged
              closingIssuesReferences(first:20) {
                nodes { number node_id: id state labels(first:50){ nodes { name } } }
              }
            }
          }
        }
        """,
        {"owner": owner, "repo": name, "num": pr["number"]},
    )
    refs = data["repository"]["pullRequest"]["closingIssuesReferences"]["nodes"]
    print(f"PR #{pr['number']} action={action} closes={[r['number'] for r in refs]}")
    for ref in refs:
        if ref["state"] != "OPEN":
            continue
        item_id = ensure_item(board, ref["node_id"])
        if action in ("opened", "reopened"):
            if current_value(item_id, "Status") == STATUS_BACKLOG:
                set_single_select(board, item_id, "Status", STATUS_IN_PROGRESS)
            set_single_select(board, item_id, "Stage", STAGE_IN_REVIEW)
        elif action == "closed":
            # PR went away without merging (merge closes the issue -> Done).
            labels = {n["name"] for n in ref["labels"]["nodes"]}
            stage = compute_stage(labels)
            if stage:
                set_single_select(board, item_id, "Stage", stage)
            else:
                clear_field(board, item_id, "Stage")


# --------------------------------------------------------------------------- #
# Backfill                                                                    #
# --------------------------------------------------------------------------- #


def backfill(board: Board, repo: str) -> None:
    owner, name = repo.split("/")
    cursor = None
    seen = 0
    while True:
        data = gql(
            """
            query($owner:String!, $repo:String!, $after:String) {
              repository(owner:$owner, name:$repo) {
                issues(first:50, after:$after, states:OPEN,
                       orderBy:{field:CREATED_AT, direction:ASC}) {
                  pageInfo { hasNextPage endCursor }
                  nodes {
                    number node_id: id state
                    assignees(first:1) { totalCount }
                    labels(first:50) { nodes { name } }
                  }
                }
              }
            }
            """,
            {"owner": owner, "repo": name, "after": cursor},
        )
        page = data["repository"]["issues"]
        for issue in page["nodes"]:
            seen += 1
            print(f"backfill #{issue['number']}")
            item_id = ensure_item(board, issue["node_id"])
            status = STATUS_IN_PROGRESS if issue["assignees"]["totalCount"] > 0 else STATUS_BACKLOG
            set_single_select(board, item_id, "Status", status)
            stage = compute_stage({n["name"] for n in issue["labels"]["nodes"]})
            if stage:
                set_single_select(board, item_id, "Stage", stage)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    print(f"backfill complete: {seen} open issues reconciled")


# --------------------------------------------------------------------------- #
# Entry point                                                                 #
# --------------------------------------------------------------------------- #


def main() -> None:
    repo = os.environ["GITHUB_REPOSITORY"]  # "Arx-Game/arxii"
    org = repo.split("/")[0]
    project_number = int(os.environ.get("PROJECT_NUMBER", "1"))
    board = Board(org, project_number)

    mode = sys.argv[1] if len(sys.argv) > 1 else "event"
    if mode == "backfill":
        backfill(board, repo)
        return

    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    with Path(os.environ["GITHUB_EVENT_PATH"]).open(encoding="utf-8") as handle:
        event = json.load(handle)
    if event_name == "issues":
        handle_issue(board, repo, event)
    elif event_name == "pull_request":
        handle_pull_request(board, repo, event)
    else:
        print(f"event {event_name!r} not handled - nothing to do")


if __name__ == "__main__":
    main()
