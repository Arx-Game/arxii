# Agent harness notes

Dated workarounds for Claude Code and devcontainer behaviour, with the incidents
that produced them. **These are not project invariants.** CLAUDE.md keeps the
rule and a one-line pointer here; this file keeps the why and the evidence, so an
agent pays for the story only when it needs it. Each entry names the harness
behaviour it works around. When a harness release removes that behaviour, delete
the entry and the rule it justified.

Machine scope, used throughout: **the workstation** (TehomCD's, well above 8 GiB
visible to the container) and **the solo laptop** (16 GB host, 6 GB WSL VM,
4 GiB app container; `grep MemTotal /proc/meminfo` under 8 GiB). Rules that
exist to make parallel implementers safe apply on the workstation; on the laptop
there is one agent, sequential, and most of them never fire.

## Implementers sharing a worktree: the commit hook, not serialisation (#3814, ADR-0296)

Workstation only. pre-commit's own hook runs `git checkout -- .` over the whole
worktree while a commit's hooks run, so a sibling's uncommitted edits vanish for
about 50 seconds and anything it writes then can be lost; a failed auto-fix then
invites `git add -A`, which sweeps the sibling's files into the commit. The
installed hook (`tools/githooks/pre-commit`, via `just install-git-hooks`) checks
staged files without clearing anything. That is why up to three implementers may
share one worktree under CLAUDE.md's conditions (disjoint file lists, named
siblings, pathspec commits, `SKIP=ty,typescript`).

Why the index matters: a pathspec commit holds `index.lock` while its hooks run,
so a sibling's `git add` or commit in that window fails with "index.lock: File
exists". Wait and retry; never delete `index.lock`. `refs/stash` is shared by
every worktree, which is why `git stash` is banned in a wave. `tsc` alone reaches
about 1.3 GB on a 4 GiB container (#3707), which is why siblings skip `ty` and
`typescript` and the coordinator runs each once before pushing.
`check-type-annotations` stays on: it is the only annotation check (a no-op under
CI's `--all-files`), and a failure it raises on a sibling's staged file clears on
a rerun.

## Subagents that background a command die silently (#1909, #2698, #3652)

Background completion notifications re-invoke the main loop only, so a subagent
that backgrounds a command and ends its turn "waiting for the notification" never
wakes. Telling it not to failed across three sessions: 2 stalls in #1909, 6+ on
2026-07-06/07, 6 of 7 agents in #2698 despite a capitalised block naming
`run_in_background`, `&`, `Monitor` and poll-a-file by name.

**#3652 found the mechanism.** The Bash tool's default timeout is 120 seconds and
the harness auto-backgrounds anything that exceeds it. An agent running a long
suite in the foreground gets it backgrounded out from under it, then waits on a
notification that only ever wakes the main loop. It never chose to background
the command, so telling it not to cannot prevent this. Two of nine implementers
on that plan stalled this way; once dispatches carried an explicit `timeout`
(for example `600000`) on the long test call, the rest ran a 4.5-5 minute suite
to completion in the foreground with no stalls.

Why ordering is the control: in #2698 the agents dispatched before the "commit,
THEN test" line stranded 21, 68 and 72 uncommitted files when they stalled; the
ones dispatched after it stalled just the same but had already committed, so
recovery was reading `git log` and moving on. The stall was never the cost. The
unrecoverable work was. Recovery when it still matters: resume the agent with a
message ordering it to re-run the checks in the foreground and commit before
ending its turn.

## A subagent that skips the worktree anchor drifts into the main checkout (#2029)

An absolute worktree path in the prompt is not enough. A subagent that does not
`cd <worktree>` then `pwd` and `git status --short` as its first action drifts
into the shared main checkout, where concurrent sessions clobber its uncommitted
work. Near-miss on #2029. Workstation only: on the laptop the branch lives in the
main checkout by design and there is no sibling to collide with.

## `cd && <command>` is flagged for manual approval on Windows (mid-2026)

Claude Code on a Windows host flags every `cd && <command>` for manual approval
as a bare-repo-attack mitigation, which blocks automation. Use `git -C /path`,
absolute paths, or a tool's own directory flag. Inside the devcontainer no
permission prompts fire at all, so this is host-only friction. Relax the rule if
a future release stops flagging the shape.

## Batched mutating tool calls cascade-cancel

When one call in a parallel batch errors or hits an approval prompt, the harness
cancels every sibling in that batch, and most of the intended work silently does
not run. This is why repo-mutating operations go one per message; read-only
fan-out can still be batched.

## Retired

- **`workflow-friction-audit` skill (2026-09-25).** Designed 2026-05-26
  (`docs/architecture/skill-friction-audit-and-takeaways-design.md`) to log
  recurring tool failures for a periodic audit. In four months the log never
  received an entry: agents do not volunteer to log friction mid-task, and the
  permission-prompt trigger it replaced does not exist inside the container.
  Friction now goes into this file directly, or into a memory note, at the moment
  it is fixed.
