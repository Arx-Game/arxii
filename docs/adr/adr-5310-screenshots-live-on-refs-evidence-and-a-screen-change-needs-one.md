# ADR-5310: Screenshots live on refs/evidence, and a change to a screen needs one

**Status:** Accepted (2026-11-24, approved by the maintainer in conversation after a
review of the plan)
**Issue:** #5310
**Related:** ADR-4246 (prove a change by operating it), ADR-4247 (the CI real-test
job)

## Context

Agents took real screenshots of the running app but rarely got them onto the PR. Of
25 recent merged PRs that changed frontend `.tsx` files, 20 linked screenshots in a
comment, none showed one in the PR body, and some left them in a session scratchpad.
The screenshot check ran only when the issue carried a `frontend` label or a demo
link. Images were uploaded by committing them to the PR branch and removing them with
a later `git rm` commit: each upload restarted CI and changed the PR's head, and the
`review-evidence-not-committed` job failed until the removal (nine of fourteen recent
failed evidence jobs). Running a server for screenshots also meant sharing ports
4000-4006 with every other checkout, where `arx stop` stops whichever server holds
them.

## Decision

- **Screenshots are pushed to `refs/evidence/<number>/<stamp>`** on an orphan commit
  (`just shot-post`), linked by commit SHA through `raw.githubusercontent.com`. No
  branch carries them, no workflow runs on the ref, a clone does not fetch it, and
  nobody rebases it. Evidence refs are never deleted.
- **The diff decides whether a picture is required.** A PR that changes non-test
  `frontend/src/**/*.tsx` needs an image this repository hosts in its body, or a line
  `No visual change: <reason>`. The waiver is a line in the body, not a label, so a
  reviewer reads the reason.
- **`just shot` runs the worktree's own server on its own port block** (4100-4106,
  `ARX_PORT_BASE`) under the container-wide heavy-work lock, so one session at a time
  builds and runs a browser, and it never waits on or stops another checkout's server.
- **A chore or dependency PR may close no issue** when it says why: `No issue: <reason>`.

## Rejected alternatives

- **Keep committing images to the branch.** Rejected for the CI restarts, the head
  changes, the force-push exposure and the removal commit described above.
- **An orphan branch, release assets or a separate evidence repository.** Every clone
  fetches a branch; release assets are mutable and clutter the public Releases page;
  a separate repository needs a maintainer to widen the PAT.
- **A `no-visual-change` label as the waiver.** Agents can apply labels, so a label
  authorises nothing and records no reason.
- **Per-worktree servers on many port blocks at once.** The container has no memory
  cap; several servers and browsers beside test runs would swap the whole VM. The lock
  keeps it to one.
- **CI screenshots only.** They need a spec, a seed and a workflow edit per screen,
  and land in a zip artifact nobody opens. They stay the fallback on the small laptop.
