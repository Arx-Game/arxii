# Review-evidence screenshots don't belong in `main`'s history

`PR_EVIDENCE_FILE` supports a repository path (`open-pr.sh`'s docstring calls it
"a scratch path" too, but a scratch path fails once the agent's session/worktree
is gone — the file has to be *somewhere durable* for CI to fetch it on later
pushes, and for a human to read it after). The obvious durable choice is
committing the report + screenshots into the feature branch. **Don't leave them
there through to merge.** They exist only to satisfy this review pass, not as
permanent documentation of the feature — committing them means every future
`git log`/`git blame`/checkout of `main` carries megabytes of PNGs and a report
whose only readers were CI and one human review. Two sibling sessions hit this
independently on the same day (#3759, #3760) before either had asked the
question.

## The move

1. Do the whole evidence pass as normal: commit the report + screenshots to the
   branch, push, let `open-pr.sh`/CI validate against them (`PR_EVIDENCE_FILE`
   pointing at the committed path). This is the easiest way to iterate — local
   files, normal `git diff`, no new external moving parts while you're still
   fixing findings.
2. Once the report is final (verdicts settled, nothing left to fix), **before
   opening the PR or as a follow-up commit on an already-open one**, post the
   report as an issue/PR comment instead, rewriting its screenshot links from
   repo-relative paths to
   `https://raw.githubusercontent.com/<owner>/<repo>/<full-40-char-commit-sha>/<path>`
   — the SHA of the commit that has the files right now (verify at least one
   resolves: `curl -sI <url>` should return `200` and `content-type: image/…`,
   not `curl -sI`'s silent everything-looks-fine-when-it-isn't habit on a
   redirect-to-404). This works, and keeps working, **because GitHub retains
   every commit that was ever pushed as part of an open PR** (reachable via
   that PR's own `refs/pull/<N>/head`) independent of what the branch's
   current tip contains — the URL doesn't stop resolving once the branch
   moves past that commit.
3. Get the new comment's URL, then switch `PR_EVIDENCE_FILE` to `PR_EVIDENCE_URL`
   pointing at it (or edit the PR body's `- Report:` line directly with
   `gh api -X PATCH` — `gh pr edit --body-file` is known to silently fail on
   this repo).
4. `git rm` the local report + screenshots directory, commit, push. Since
   `main` only ever receives a **squash-merge's tree snapshot at the PR's
   final tip**, this removal commit is what decides what lands in `main` —
   the earlier commits where the files still existed are simply never part of
   `main`'s history, even though they're still reachable (and the raw URLs
   still resolve) via the PR's own ref.

## Sequencing gotcha: this touches the same clock as the evidence gate itself

`validate_review_evidence.py --revision` (and the CI job that calls it) always
checks the report's stamped "Reviewed revision" against **`HEAD^1` of the PR's
current tip at validation time** — not a fixed point you set once. Two
consequences:

- Write the new comment's "Reviewed revision" as the SHA you're about to make
  `HEAD^1` — i.e. current `HEAD`, since the removal commit you're about to push
  will be its child. Do this **before** creating the removal commit, not after
  (you already know what that SHA will be).
- Any commit you push **after** the removal commit invalidates this again
  (its own `HEAD^1` shifts) — so the removal commit should generally be your
  last push for this evidence pass. If you must push again later, re-stamp the
  comment's revision field to the new tip (edit the same comment via
  `gh api -X PATCH`, or post a fresh one) before pushing.

## Why not a gist, why not GitHub's own image upload

Tried first (2026-09-11, #3759): `gh gist create` failed with `HTTP 403:
Resource not accessible by personal access token` — this repo's agents run
under a fine-grained PAT scoped to `Arx-Game/arxii` specifically, with no
account-wide `gist` permission; getting one requires a maintainer to grant it
by hand. The web UI's drag-and-drop image paste (what actually embeds an image
directly in a comment, independent of any commit) goes through a private,
session-authenticated upload endpoint — not any documented public REST/GraphQL
API surface, not reachable from `gh api` under any PAT scope. If GitHub ever
ships a real public API for that, switch to it — it would be strictly better
(no dependence on a specific commit's retention at all). Until then, the
raw-URL-at-commit-SHA technique above needs no new permissions and no new
external service, which is why it's the default here.
