---
name: grilling-session
description: Use before drafting any product brief, PRD or spec for standard or heavyweight work, and whenever the maintainer wants to talk a design through. The maintainer talks at length and the agent asks open questions, keeps the words verbatim, extracts rules with quotes beside them, plays them back as one walkthrough, and ends with a pitch. Replaces "agent proposes options, maintainer picks one".
compatibility: polytoken
---

# Grilling session

The maintainer talks, and the agent listens, asks and records. The design comes
out of the maintainer's own words, not out of options the agent drew up.

**Why this exists (2026-11-21).** Framing work as a few discrete decisions implies
the direction is already set, and the maintainer ends up shrugging at options an
agent chose. Agent-written briefs, ADRs and closing comments put the agent's
reading where the maintainer's words should be. The first session run this way
(#5280, the anima ritual) produced a design the maintainer agreed to in full.

## When to use it

- Before the product brief of any standard or heavyweight issue
  (`issue-to-merged-pr` Step 2). The critics and the brief come after it.
- Whenever the maintainer wants to rethink something, even with no issue yet.
- Not for lightweight work, and not for questions the code or a recorded
  ruling already answers.

## The loop

1. **Open with what you checked, then open prompts.** Read the code first, so the
   prompts rest on facts. Give the maintainer two or three lines of what the game
   does today, then three to five prompts. A prompt invites talk ("Walk me through
   a character whose aura is split..."), never a menu. Phrase prompts as statements
   ("Tell me whether...") so no sentence ends in `?` outside `AskUserQuestion`.
   Say that rambling, any order and dictation are all fine.
2. **Keep the words verbatim.** Append each answer, unedited, to a transcript
   file. Keep it private: `tmp/grill-<topic>-transcript.md` in the main checkout
   (untracked, never committed) or a private Claude Doc. A transcript can name
   roster characters and hold lore, so it never goes to GitHub whole.
3. **Extract rules, each with the quote beside it.** One full sentence per rule,
   then the maintainer's words in quotes. Anything with no quote behind it is a
   question, not a rule.
4. **Push.** Each turn ends with prompts on what is still open:
   - two answers that pull in different directions;
   - a word that can mean two things ("actively GM'd", "some");
   - a gap the build needs that nobody said;
   - an earlier ruling, or code, the new rule runs into.
   When you got something wrong, say so plainly and correct it.
5. **Repeat until the answers stop raising new rules.** Usually four to six turns.
6. **Play it back as one walkthrough, not a list.** Never hand the maintainer a
   long list of their own rulings to check ("lists like that are the mindkiller").
   Write one short scene of a character going through the whole design in play,
   then list only what *you* inferred or filled in. Those few items are all they
   need to check.
7. **End with a pitch.** Spin what was decided into why it is compelling: the play
   moment, what it lets a player or GM do, how it makes narrative play richer, how
   often it comes up, what it costs, and the strongest case against. Give no
   verdict of your own; the maintainer decides. A case against may come from a
   critic agent. If the pitch does not grab them, more work is needed.
8. **File from the session.** When the maintainer agrees, write the issue (or
   update the existing one): the rules grouped in collapsed sections with the maintainer's
   quotes, a separate section for the inferences the maintainer agreed to, ideas the maintainer floated
   that are not rules, and the discovery marker with `state=complete`. Redact
   roster character names from quotes in public text (`[an Abyssal character]`).
   Then `issue-to-merged-pr` continues with the technical spec.

## What the session feeds

- **Property tests.** Each rule is a statement of behaviour in the maintainer's
  words, so each one can become a Hypothesis property whose docstring quotes it
  (ADR-4248). Rules phrased as outcomes ("a ritual feeds at most two resonances")
  test well; a rule about which function is called does not belong in the list.
- **The critics.** `intent-ambiguity-critic` and `scope-simplicity-critic` read
  the extracted rules after the session, not an agent draft before it.
- **Memory.** Save corrections to the game's vocabulary the session surfaces
  (for example, a resonance is always an emotional state, never an element).

## Red flags

| Thought | Reality |
|---|---|
| "I'll offer three options to speed this up" | Options imply the direction is set. Ask the maintainer to talk it through. |
| "I'll summarise the maintainer's answer in my words" | Quote it. A paraphrase is where agents overstate. |
| "The list of rules is complete, the maintainer can tick through it" | Walkthrough plus inferences only. |
| "I'll add my verdict to the pitch" | No verdict. The maintainer decides. |
| "The docstring says so, so it's a rule" | Only the maintainer's words, a spec the maintainer approved, or a recorded ruling make a rule. |

The plain-prose rules still apply to every turn the maintainer reads. Run the
`plain-prose-reviewer` agent on each turn that runs past a few sentences, as
CLAUDE.md requires, and fix its findings before sending.
