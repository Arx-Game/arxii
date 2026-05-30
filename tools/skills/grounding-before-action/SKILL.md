---
name: grounding-before-action
description: Use at the start of every session and before composing ANY message that contains an AskUserQuestion or a sentence stating what a tool returned / what an issue/file/branch contains / what a subagent found. Also before any irreversible or outward-facing action (gh/git writes — issue comment/edit/label/assign/close, PR ops, pushes, file deletes). Especially when a tool result looks empty or hasn't appeared — that is the moment confabulation happens.
---

# Grounding Before Action

<!-- TEMP HARNESS-BUNDLING-WORKAROUND — remove when GH #647 is resolved.
     This skill exists ONLY to work around a Claude Code 2.1.158 regression
     (co-emitted tool results are invisible at compose time). Delete the whole
     skill dir + the CLAUDE.md/README pointers + the memory note when the
     harness is fixed. See issue #647 for the removal manifest + test. -->

> ⚠️ **TEMPORARY — harness workaround (grep: `HARNESS-BUNDLING-WORKAROUND`).**
> This is not permanent project discipline. It exists because Claude Code
> **2.1.158** (latest as of 2026-05-30) cannot see a tool result that is
> emitted in the **same assistant message** as the call it depends on. When the
> harness is fixed, **delete this skill** per the manifest in **GH #647**.

## The one rule

**Never put a tool call and a claim-about-its-result in the same message.**

Concretely:
- `AskUserQuestion` goes in its **own message**, alone — never co-emitted with the tool calls whose output the question reasons about.
- Any sentence asserting what a tool returned — file contents, an issue's title/body, comment counts, a branch name, a subagent's findings — must be written in a turn that comes **after** the turn that produced it, where you can actually see the result.

Emit calls → **end the turn** → observe the real results → **then** compose whatever depends on them.

## Keeping `AskUserQuestion` (the picker) safe — solo emission + echo-back

The picker UI is worth keeping. It only breaks when `AskUserQuestion` is **co-emitted with other tool calls** — then the batch resolves together, the answer isn't visible at compose time, and the model confabulates an answer (or barrels past as if auto-answered). Emitted **alone**, the turn ends cleanly, the picker shows, and the real answer arrives in the next turn. So the trigger is *bundling*, not the tool. Two rules preserve the picker AND guard it:

1. **Solo emission.** `AskUserQuestion` must be the **only** tool call in its message — never alongside any Bash/Read/Edit/Agent/other call. If you're tempted to "ask and also kick off some reads," split it: ask alone, end the turn, then act on the answer next turn. (If the picker is misbehaving in this session anyway, downgrade further: ask in **plain text with zero tool calls** and stop — a turn with no tool call cannot be auto-resolved.)

2. **Echo-back before acting.** After an answer returns, **restate it in plain text before any irreversible action** — "You chose X, so I'll do Y." This converts a silent auto-answer/confabulation into a loud, catchable error at the cheapest moment: if the echo is wrong, the user stops you *before* the GitHub write or edit. One sentence; non-negotiable before mutations.

## Why (the bug, precisely)

Tool results are **not** lost or garbled. They arrive intact. The failure is that when you bundle a dependent step into the same message as its tool call, you are composing that step **before the result exists in your view** — so you see a blank and fill it with a plausible story. The batch then resolves and the real output sits right next to your fabrication. The content of the lie is random (an "empty" file, a "corrupted" read, "41 passing tests", a fake issue #643); the cause is fixed: **dependent step co-emitted with its call.**

## The gates

1. **Un-bundle (solo `AskUserQuestion`).** `AskUserQuestion` must be the only tool call in its message; result-narrating sentences get their own message too. If you're about to write "the output shows…", or co-emit a question with reads/edits, or reason about a result in the same message as the call producing it — STOP, split it. Echo the answer back in plain text before acting on it (see "Keeping `AskUserQuestion` safe" above).
2. **A read is only true for the instant it returned.** State drifts and turns are long; **re-read immediately before acting**, in a turn where the fresh result is visible before the write.
3. **One sequential call for state-changing or state-reading git/gh work.** No large parallel batches. Independent *pure reads* may batch; never batch a read with the action it informs. (See [[feedback-sequential-mutations]].)
4. **Verify number↔title before ANY issue mutation.** Before `gh issue comment/edit/--add-label/--add-assignee/close` (or PR equivalents), fetch and quote the target's number AND title — and confirm `gh issue create` returned the number you think it did (it is NOT the next sequential number). Never assume numbers are sequential or that a remembered title is current.
5. **Reads → user-checkable summary → writes.** Surface what you observed (titles, IDs, counts) before a batch of irreversible actions, so it can be checked.
6. **If you didn't see it, you don't know it.** Never narrate a tool result, file content, issue body, or subagent finding you have not observed in a returned result. "Probably returned…", "should say…", "the agent found…" are confabulation. Say "I haven't seen it yet" and go look.

## Red flags — STOP, you're about to confabulate

- You're writing an `AskUserQuestion` in the same message as other tool calls. (Emit it solo.)
- You're about to act on a picker answer without echoing it back in plain text first.
- A result looks empty/partial/corrupted and you're tempted to "proceed as if…" or to report a problem with the tooling. (The tooling is fine — you just haven't seen the result yet.)
- You're about to `gh issue edit/comment/close` without a title quote in this turn, or trusting that `gh issue create` made issue #N+1.
- You're describing what a subagent "found" but can't point to its returned text.
- You're relying on a read from earlier in a long turn for a write happening now.

**All of these mean: end the turn, observe the real result (or re-read), then act.**

| Rationalization | Reality |
|---|---|
| "The output is empty, I'll infer it" | Empty-at-compose ≠ empty. End the turn; it's there when you look. |
| "The reads look corrupted/fabricated" | They're not. You composed that claim before seeing them. |
| "I already read that issue earlier" | State drifts, turns are long. Re-read in the same turn as the write. |
| "Bundling the read + the edit is faster" | Bundling IS the bug. One call, observe, then act. |
| "Issue #N+1 follows #N" | Numbers aren't guessable. Quote the create URL / `gh issue view`. |
| "Saying it stalled is harmless" | Groundless status claims are confabulation too — and burn user trust. |
| "I'll ask and start the reads in one go" | That co-emission is what breaks the picker. Ask solo, end the turn. |
| "The picker answer is obviously right, just act" | Auto-answers look identical to real ones. Echo it back first; let the user catch it. |
| "Dropping the picker is the only safe option" | Solo emission keeps the picker working; echo-back catches the rare miss. |

## Real-world impact

2026-05-30, in the very session this skill was written: the author bundled `AskUserQuestion` calls with the tool calls they depended on, repeatedly saw blanks at compose time, and confabulated — first "output stalled," then "reads are corrupted/fabricated," and earlier an entire subagent investigation that never ran (invented file contents, an Explore report, "41 passing tests", the bodies of issues #635/#636, and a non-existent issue #643). Acting on that fiction produced real erroneous GitHub edits (wrong assignee/label/comments) that had to be reverted. The author then **broke this very skill minutes after writing and GREEN-testing it** — proving both that the skill is needed and that a passive document is a weak guard against this harness bug. The prior day, #629 was clobbered by editing an issue whose title was assumed from its number (gate 4). Every instance is the same move: a dependent step co-emitted with its tool call.
