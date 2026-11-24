# Screenshots live on refs/evidence, never on a branch

A screenshot of the running app belongs on the PR, where a reviewer looks, and
nowhere in the PR's branch. Since #5310 there is one way to put it there:

```bash
just shot /characters/1/sheet /roster            # from the worktree, by the coordinator
just shot-post <pr-or-issue> frontend/test-results/shots/<stamp>/*.png
```

`just shot` (`tools/shot.sh`) runs this worktree's own server on its own port block
(4100-4106) and its own `rt_<issue>` database, under the container-wide heavy-work
lock, and saves one full-page PNG per path (or runs a spec with `--spec`). See the
`real-testing` skill.

`just shot-post` (`tools/shot_post.sh`) stores the PNGs on an orphan commit made with
git plumbing and pushes it to `refs/evidence/<number>/<stamp>`. It checks every image
link answers 200 with `image/png`, adds the images to its one comment on the PR (or
issue), and prints the Markdown. **Paste that Markdown into the PR body**: the
`frontend-screenshot` job in `spec-evidence.yml` requires an image this repository
hosts in the body of any PR that changes non-test `frontend/src/**/*.tsx`, unless the
body has a line `No visual change: <reason>`.

## Why a ref, not the branch

Until #5310 the images were committed to the PR branch (by hand or through the
Contents API), linked by the upload commit's SHA, and then removed with a `git rm`
commit. Every step of that cost something:

- each upload commit restarted CI and changed the PR's head, so "green on the
  current head" had to be earned again;
- the local worktree fell behind origin, which invited the force-push that orphans
  the upload commit and breaks the image links;
- `review-evidence-not-committed` failed on every push until the removal commit
  (nine of the last fourteen failed evidence jobs before #5310 were this step).

A commit under `refs/evidence/` is reachable from a ref no one rebases, no workflow
watches (`push` triggers name `main` only), and a clone does not fetch by default.
`raw.githubusercontent.com/<owner>/<repo>/<sha>/<file>` serves its files the same
as a branch commit's (checked 2026-11-24). The pre-push hook skips a push whose refs
are all under `refs/evidence/`, because pre-commit would otherwise run every hook
over the whole repository for a commit with no common ancestor.

**Never delete an evidence ref.** A merged PR's screenshots are linked through it.

The `review-evidence-not-committed` job stays: a file under `docs/reviews/` or
`.github/issue-evidence/` on the branch still fails it.

## The review report

The demo-fidelity report (`# Review evidence ...`) goes in a PR comment (or an issue
comment, before the PR exists), with its screenshots linked as `just shot-post`
printed them. Point the PR body's `- Report:` line at that comment's URL
(`PR_EVIDENCE_URL` for `open-pr.sh`). CI runs `validate_review_evidence.py
--check-urls`, so a screenshot link that does not load fails the check.

Record the exact commit that was reviewed in the report. The evidence gate carries
that report across later commits that cannot change what a screen renders: commits
that touch only test files (`src/integration_tests/`, any `tests/` directory under
`src/` or `tools/`, `frontend/e2e/`, `frontend/src/test/`, frontend `*.test.ts` and
`*.test.tsx` files, frontend `__tests__/` directories), documents (`docs/` and any
`*.md` file) or `.github/`. It also carries it across clean main merges the gate
reproduces, and merges of main that renumber the branch's migrations, whether the
migration bot or a person made them, when the gate rebuilds the identical tree from
the trusted transformer. A person gets that tree by running
`just migration-rebase-like-bot` when `max_migration.txt` is the only conflict; a
merge made with `arx manage rebase_migration arxii` is not byte-identical to it and
needs a fresh review. A commit that touches any other path changes application code
and requires a fresh review and an updated report, as does a merge of main whose
conflict resolution is anything beyond that renumbering. Changing the revision in a
report is not a substitute for review. Retaking the screenshots is one `just shot`
and one `just shot-post`.

## Why not a gist, GitHub's own image upload, or release assets

`gh gist create` fails with `HTTP 403: Resource not accessible by personal access
token` (2026-09-11, #3759): the agents' PAT is scoped to this repository. The web
UI's drag-and-drop upload goes through a session-authenticated endpoint that no
public API reaches. Release assets are mutable and clutter the public Releases page.
An orphan branch would be fetched by every clone. A separate public evidence
repository would also work, but needs a maintainer to grant the PAT access to it.

Do not upload secrets or player data. `just shot` refuses to run in the main
checkout, whose database is the shared dev copy of production content.
