# Review evidence

- Reviewed revision: `cefa8d720d1ca21f54175282a61eab096318968b`
- Reviewer: the implementing agent (Claude Code), with the Playwright harness on three real pages; no demo link on the issue, so no demo-fidelity pass
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4185
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900 and 390x1100, the sheet's ember plate and the default light theme
- Approved design: the rulings on issue #4193 (ApostateCD, 2026-10-08): the four shapes go on player screens and staff/GM tools alike; destructive confirmations, errors, account security, onboarding, bare costs and limits and voice lines stay. The evidence reads three pages for what is no longer there; the full removal list is the diff (124 files) and the commit message.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The owner's sheet: the abilities band with no note under its title](docs/reviews/4193/01-sheet-owner-1280.png) ![The Physical section: the physique stack with no colours note, the condition stack with no "yours and the staff's" note](docs/reviews/4193/01b-sheet-physical-1280.png) ![The Friends tab: one line for an empty list, no explainer above it](docs/reviews/4193/02-friends-empty-1280.png) ![The Mutes settings page: the heading and the list, no explainer](docs/reviews/4193/03-mutes-1280.png) ![The sheet at phone width](docs/reviews/4193/04-sheet-owner-390.png)
- Comparison notes: The sheet's Abilities band shows its title, the fold control and the three stats, with no "Yours, unless you open them to friends or everyone." under the title. The Physical section's physique stack ends at its rows, with no sentence about where colours are set; the condition stack carries no "Yours and the staff's only." The Friends tab reads "No friends yet." and nothing about trusted RP partners or login alerts. The Mutes page is the heading "Muted" and its list. The sheet's own section row keeps its "Yours only" divider word, which is the label-word form the rule allows. At phone width the plate stacks and nothing overflows. The harness also asserts that none of six removed sentences appears anywhere on any of the pages.
- Tested interactions: open `/characters/1` as the owner and read the Sheet section; click Physical in the section row and read the physique and condition stacks; open `/profile/friends` with an empty list; open `/profile/mutes` with an empty list; the sheet at 390px. No page errors were raised.
- Fixture/live boundary: the pages, router, section row, bands, tabs and bundle are real. Every `/api/**` response is a fixture: the account, the viewer's one roster entry, the entry and its sheet (three stats, no looks, no art), empty pages for mutes and friends, 404 for vitals, bare lists for everything else the pages ask for on load. The rest of the sweep (character creation, dialogs, GM tools, staff pages) is proved by the vitest suites of the changed components (110 test files, all green) and by `tools/lint_overexplaining_copy.py` finding nothing across `frontend/src`.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Abilities band: title, fold, stats; no note | as ruled | MATCH | docs/reviews/4193/01-sheet-owner-1280.png |
| Physique stack: rows only; no colours sentence | as ruled | MATCH | docs/reviews/4193/01b-sheet-physical-1280.png |
| Condition stack: no "yours and the staff's" note | as ruled | MATCH | docs/reviews/4193/01b-sheet-physical-1280.png |
| Friends tab empty state: one line | "No friends yet." | MATCH | docs/reviews/4193/02-friends-empty-1280.png |
| Friends tab: no explainer above the list | absent | MATCH | docs/reviews/4193/02-friends-empty-1280.png |
| Mutes page: heading and list, no explainer | absent | MATCH | docs/reviews/4193/03-mutes-1280.png |
| None of six removed sentences on any page | absent | MATCH | the spec's assertions at this revision |
| Phone width | the plate stacks, nothing overflows | MATCH | docs/reviews/4193/04-sheet-owner-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-privacy-captions-out | PASS | the sheet captures; the diff (AbilitiesBand, PhysicalPanel, ReviewStage, event forms, bulletin, report page, mutes, friends, nominations) | issue #4193, shape A |
| R02-page-explainers-out | PASS | the Mutes capture; the diff (EraAdminPage, XpLedgerCard, AdvancementTab, PrivacyPage, Boundaries, builders, staff pages) | issue #4193, shape B |
| R03-control-help-out | PASS | the diff (CG hints, dialog descriptions, GM adjudication glosses); vitest green for every changed dialog | issue #4193, shape C |
| R04-teaching-empty-states-out | PASS | the Friends capture; the diff (messages, story log, crossover inbox, tables, GM notes, episodes) | issue #4193, shape D |
| R05-what-stays | PASS | destructive confirmations, errors, account security, onboarding, bare limits, voice lines and the PLACEHOLDER marginalia untouched; the deliberate keeps listed in the PR body | issue #4193, "What stays" |
| R06-reviewer-agent | PASS | `tools/agents/overexplaining-copy-reviewer.md`; README row | CLAUDE.md, Reviewer Agents |
| R07-mechanical-check | PASS | `tools/lint_overexplaining_copy.py`, the `overexplaining-copy` hook, `tools/tests/test_lint_overexplaining_copy.py` (11); clean over `frontend/src` | issue #4193, the two guards |
| R08-no-rewording | PASS | `frontend/src/scenes/components/NarratedEventTag.tsx` (the suffix is "· Rowan Ashcombe only" for the subject alone, asserted in `NarratedEventTag.test.tsx`); `frontend/src/staff/pages/StaffPetitionDetailPage.tsx` (the placeholder is the label word "Notes to the sender"); every other change in the diff is a removal or a trim to the first sentence | issue #4193, out of scope |

## Unresolved findings

- None
