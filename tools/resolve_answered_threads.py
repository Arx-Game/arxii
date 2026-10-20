"""Resolve the review threads the code reviewer started and someone answered (#4510).

The ruleset requires every review thread resolved before merge. The code reviewer
(``.github/workflows/claude-code-review.yml``) opens one thread per finding as
``github-actions``; an agent that replies and then forgets to resolve leaves the
maintainer to close each one by hand. ``.github/workflows/resolve-answered-threads.yml``
runs this on every review-comment reply.

Selection is deliberately narrow: a thread is resolved only when it is unresolved,
its FIRST comment is by the reviewer bot, and a LATER comment is by a non-bot. A
thread a human started is never touched, and neither is one nobody has answered.

Usage: resolve_answered_threads.py <owner/repo> <pr> [--dry-run]
       resolve_answered_threads.py --threads-file <graphql-json> [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

REVIEWER_LOGIN = "github-actions"

THREADS_QUERY = """
query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){
  pullRequest(number:$n){reviewThreads(first:100){nodes{id isResolved path
  comments(first:50){nodes{author{login __typename} body}}}}}}}
"""
RESOLVE_MUTATION = "mutation($t:ID!){resolveReviewThread(input:{threadId:$t}){thread{isResolved}}}"


def _is_bot(author: dict | None) -> bool:
    return author is None or author.get("__typename") == "Bot"


def select_threads(nodes: list[dict]) -> list[dict]:
    """Return the threads that qualify for resolution."""
    selected = []
    for thread in nodes:
        comments = thread["comments"]["nodes"]
        if thread["isResolved"] or not comments[1:]:
            continue
        opener = comments[0]["author"]
        if opener is None or opener["login"] != REVIEWER_LOGIN or not _is_bot(opener):
            continue
        if any(not _is_bot(c["author"]) for c in comments[1:]):
            selected.append(thread)
    return selected


def _gh_graphql(*args: str) -> dict:
    out = subprocess.run(  # noqa: S603 - fixed gh argv, no shell
        ["gh", "api", "graphql", *args],  # noqa: S607 - gh on PATH
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(out.stdout)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", nargs="?")
    parser.add_argument("pr", nargs="?", type=int)
    parser.add_argument("--threads-file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.threads_file:
        data = json.loads(Path(args.threads_file).read_text())
    elif args.repo and args.pr:
        owner, name = args.repo.split("/")
        data = _gh_graphql(
            "-f",
            f"query={THREADS_QUERY}",
            "-f",
            f"o={owner}",
            "-f",
            f"r={name}",
            "-F",
            f"n={args.pr}",
        )
    else:
        parser.error("give <owner/repo> <pr> or --threads-file")
    nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    for thread in select_threads(nodes):
        first = thread["comments"]["nodes"][0]["body"].splitlines()[0]
        print(f"resolve {thread['id']} {thread['path']}: {first}")
        if not args.dry_run:
            _gh_graphql("-f", f"query={RESOLVE_MUTATION}", "-f", f"t={thread['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
