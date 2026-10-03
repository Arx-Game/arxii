# Review evidence

- Reviewed revision: `d5fad0cd20040de70126846a0c8547fff9a01b87`
- Reviewer: demo-fidelity-reviewer agent (two passes: the first FAIL, its three defects fixed and re-captured; the second PASS), with the implementing agent (Claude Code) writing this report from its checklist
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4174
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900 and 390x1100, the CG page's parchment theme and the sheet's ember plate (each page has one)
- Approved design: the demo on issue #4124, https://claude.ai/artifact/WznVJ2ZfjtM1jvZz17fxoW (version 4, 2026-10-03), Screens 1 to 4; where the spec and the demo disagree, the demo wins. Every name and prompt on both the demo and the fixtures is placeholder copy, so wording is never a finding; structure, order, controls and treatment are.
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Lineage: the house block first, a one-of beat across with Patient picked, the youth pool, an any-that-apply beat down with Efficient ticked](docs/reviews/4124/lineage-beats-1280.png) ![Lineage after adding the youth beat](docs/reviews/4124/lineage-beat-added-1280.png) ![A Sleeper: one kept beat, nothing to add or remove](docs/reviews/4124/lineage-sleeper-1280.png) ![The owner's sheet: Public sheet, the told background, the Private sheet region with the beats](docs/reviews/4124/sheet-owner-private-1280.png) ![A stranger's sheet: the public sheet alone](docs/reviews/4124/sheet-stranger-1280.png) ![Lineage at phone width](docs/reviews/4124/lineage-beats-390.png)
- Comparison notes: Screen 1: the Lineage page opens with the Upbringing's frame card and the family block (the fixture's "none" path shows the naming ritual; a claim path shows the house and the kin slot, both the existing #3617 block), then the stages of a life. The childhood beat's answers run across as bordered cards with a round dot, the picked one filled and accented, each with its gloss and price; the "One of" line sits under the prompt. The youth stage offers its one untaken beat as a chip. Screen 2: the adult beat runs down the hairlines with square marks, the ticked row filled, "Any that apply" under the prompt. Adding a beat sends the whole `draft_data.beats` map and the new beat opens with its answers (second capture). Screen 3: the Sleeper's one kept beat shows its any-that-apply answers with no remove and no add control anywhere. Screen 4: "Public sheet" over the page, the told background under "Where they come from", the "Private sheet" region in a shifted tone holding "The beats" by stage with answers and the player's line, the unknown beat reading "Unknown"; no caption names who may read it. A stranger's sheet shows neither heading nor region. Deliberate differences from the demo, each ruled by a standing rule of ApostateCD's and listed in the Requirement ledger: no free "Neither" card (neither is implicit; a picked one-of card toggles off), no empty-stage or Sleeper explanatory sentences and no hint under the line field (the no-help-text rule), no entry chevron / catalogue line / "Taken" tag and no collapsed summary row (collapse is not in scope; a beat is always open), bare numbers with the award-in-green grammar (the repo's price grammar), one chip per available beat rather than an "Add a beat" button plus a picker, no age suffix on the stage heading, the existing "Where they come from" heading over the told background.
- Second-pass items, each answered: F1 (the purse line reads "0 of 100" with two picks held): the `cg-points` fixture is static and never prices the fixture picks; on the server a beat pick is priced through the same `draft_data["distinctions"]` entry every chapter uses, asserted by `test_beats.py` `test_taking_a_beat_is_a_draft_patch_and_the_sync_refuses_two_answers_on_one_of` (the synced entry carries `cost: 10` and the purse breakdown shows a distinction line of 10). F2 (no right-hand rail): the Lineage stage as built has the stage list at the left and the record card at the foot, which the demo page drew as "here already"; not a change of this PR. F3 (an "At the Glimpse" stage heading over the Sleeper's kept beat): the heading comes from the kept beat's own stage value and every stage with a beat in the pool draws its heading; the demo drew the kept beat with none. Recorded as a difference, not a defect. F4 (a line field and an Unknown mark on the kept beat): the spec makes unknown an answer on every beat and the line is the same optional line every taken beat carries; the demo's Sleeper entry omitted both.
- Tested interactions: open `/characters/create` at Lineage; read the order of the house block and the stages; read the picked and ticked states; click the youth beat's chip and read the draft PATCH (every taken beat in one map); click Spoiled on the one-of beat and read the distinctions sync (Spoiled replaces Patient, Efficient on the other beat stays); open the page with a one-kept pool; open `/characters/1` as the owner and as a stranger; the same stage at 390px. No page errors were raised.
- Fixture/live boundary: the pages, router, stage, beats block, offers block, sheet panel, beats band and bundle are real. Every `/api/**` response is a fixture: a draft at stage 3 with two beats taken and one line, a three-beat pool (one-of childhood, one-of youth, any-that-apply adulthood) and a one-kept pool, the `backgrounds` chapter's offers filtered by taken beats the way `_opener_satisfied` filters them, two held distinctions, and a `CharacterSheetPayload` in two readings (owner: three beats, one unknown; stranger: none). The server side (the pool and exclusions, the opener, the one-of refusal, finalize, the sheet's gate) is proved by `world.character_creation.tests.test_beats` and `world.character_sheets.tests.test_viewset`, not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Lineage opens with the family block, then the beats | house and parents before any beat | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Stage headings in life order with a count of taken beats | Childhood, Youth, Before the Glimpse | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| One-of beat: answers across as cards, round dot, picked card accented | Patient picked | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| "One of" / "Any that apply" line under the prompt | present | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Any-that-apply beat: answers down the hairlines, square marks, ticked row filled | Efficient ticked | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Price per answer, award in green, bare numbers (the repo's grammar) | 10; AWARDS 10 | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Optional line field under a taken beat, no hint (the no-help-text rule; the label is placeholder copy) | one field | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Unknown mark and Remove under a taken beat | present | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Untaken beats offered under their stage as one chip each (not a button plus a picker; deliberate) | the youth chip | MATCH | docs/reviews/4124/lineage-beats-1280.png |
| Adding a beat opens it with its answers | Wrathful offered | MATCH | docs/reviews/4124/lineage-beat-added-1280.png |
| Sleeper: one kept beat, any-that-apply, no remove, no add | as drawn | MATCH | docs/reviews/4124/lineage-sleeper-1280.png |
| Sheet: "Public sheet" heading, told background, "Private sheet" region in a shifted tone | as drawn | MATCH | docs/reviews/4124/sheet-owner-private-1280.png |
| Private sheet: beats by stage with answers and the line; an unknown beat reads Unknown | as drawn | MATCH | docs/reviews/4124/sheet-owner-private-1280.png |
| No privacy caption anywhere | none | MATCH | docs/reviews/4124/sheet-owner-private-1280.png |
| Stranger: neither heading nor region | public sheet alone | MATCH | docs/reviews/4124/sheet-stranger-1280.png |
| Phone width | the cards stack, nothing overflows | MATCH | docs/reviews/4124/lineage-beats-390.png |
| Elements the demo drew that the build omits by ruling (free "Neither" card; empty-stage sentence; Sleeper closing note; line hint; entry chevron, catalogue line and "Taken" tag; collapsed summary row; "pts" and the mono effect line; "Add a beat" button; age suffix; "Background" heading) | absent, by ruling: the demo marks that copy placeholder, ApostateCD's no-help-text and bare-numbers rules apply, and collapse is not in the spec | MATCH | docs/reviews/4124/lineage-beats-1280.png, docs/reviews/4124/sheet-owner-private-1280.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-library-shared-and-excluded | PASS | `test_beats.py` `test_pool_is_the_library_minus_this_beginnings_exclusions_in_life_order`, `test_no_beginning_no_pool` | Decision 2 |
| R02-answers-are-priced-choices-never-free | PASS | `BeatAnswerForm` and `LifeBeatAdmin.save_formset` fix chapter and `CHOICE`; `test_an_answer_opens_only_once_its_beat_is_taken` asserts `arrives_as == CHOICE`; no `BUNDLED`/`CARRIED` path reads a beat | Decision 1 |
| R03-one-of-and-any-that-apply | PASS | `one_of_beat_conflicts` and the sync's `_validate_one_of_beats` (`test_taking_a_beat_is_a_draft_patch_and_the_sync_refuses_two_answers_on_one_of`); `ChapterOffers` `exclusive` (`BeatsBlock.test.tsx` "a one-of pick drops the sibling"); the mode line and the across/down drawing in the captures | Decision 4 |
| R04-house-first-then-beats | PASS | `LineageStage.tsx` order; the capture | Decision 9 |
| R05-pool-not-questionnaire | PASS | add / remove / unknown through one map (`BeatsBlock.test.tsx`; the PATCH read by the evidence spec); no required beat (`get_lineage_errors` untouched) | Decisions 3, 12 |
| R06-sleeper-kept-beat-and-unknown | PASS | `test_one_kept_beginning_takes_its_pool_by_itself`; `test_an_unknown_beat_opens_nothing`; the Sleeper capture; `kept` hides Remove | Decision 2, 12 |
| R07-finalize-writes-beat-rows-and-drafts-the-background | PASS | `test_taken_beats_become_rows_and_draft_the_background`, `test_an_untaken_pool_writes_nothing` | Decisions 5, 7 |
| R08-beats-private-told-story-public | PASS | `test_viewset.py` `test_the_beats_are_the_owners_and_staffs_and_a_beat_row_refreshes_the_sheet`; `_build_story` unchanged for the told paragraph; the owner and stranger captures | Decisions 5, 6 |
| R09-no-privacy-caption | PASS | `GuidelinesBand` note removed; `CharacterSheetPage.test.tsx` asserts no "yours and staff" text; the capture | Decision 6 |
| R10-maturation-floor | PASS | `MaturationFloorTest` (45 starts at 0, earns at 47; a pre-rule sheet keeps its bank); `world.progression` and `world.vitals` suites green | Decision 7 |
| R11-species-price | PASS | `SpeciesPriceTest`; `test_cg_points_species_cost` green | Decision 8 |
| R12-secret-resolves-beat | PASS | `SecretResolvesBeatTest` (the subject learning it resolves; another reader does not) | spec, Sleepers |
| R13-admin-and-builder | PASS | `LifeBeatAdminTest`; `web.admin.tests.test_distinction_builder` green with the beat opener; `arx manage check` clean | Implementation design |
| R14-beat-answer-hands-into-the-enemy-chapter | OUT_OF_SCOPE | Decision 13 is pending; a drawback answer is a plain offer in this change | Decision 13 (pending) |
| R15-where-the-beats-live | PASS | inside Lineage below the house (Decision 10's working assumption, as drawn) | Decision 10 (working assumption) |

## Unresolved findings

- None
