# Review evidence, issue #3941, World › Journals: the Reading Room

- Reviewed revision: `ba3fb8f8df6741cdd9f227c75b993403a5295ccb`
- Reviewer: demo-fidelity-reviewer, two passes (a first pass found four departures from the demo, fixed in 067e818c0 and ba3fb8f8d; the second pass re-checked every screen at this revision)
- Reviewer verdict: PASS
- Application/build identity: the shipped `JournalsPage` (`frontend/src/journals/pages/JournalsPage.tsx`) mounted at its real route `/journals` inside the real application shell (Header, providers, `ProtectedRoute`), composing the shipped `JournalRow`, `SearchPanel`, `WriterPlate`, `YourJournalHeader`, `JournalDesk` and `JournalEntryFields`, with the shipped `frontend/src/journals/journals.css` and the application's real `index.css` token cascade, served from the production build (`pnpm build`, Vite preview on localhost:4173)
- Environment: Chromium driven by Playwright (`frontend/e2e/journals-reading-room.spec.ts`) in the project devcontainer on Linux, deviceScaleFactor 1
- Viewports/themes: 1280x900 desktop (full-page captures) and 400x900 phone, light theme, the root carrying `data-realm="arx"`
- Approved design: the Reading Room demo at https://claude.ai/artifact/JW74XTJ7cPbqV51JHpPqDW, linked from the spec on #3941; the reviewer compared against full-page renders of the demo's own HTML (viewer as the docked character with Search open, and as another player) at the same 1280 width
- Visual review: completed. Seven captures of the rendered application (five screens, the Search panel open, and the phone width) were inspected by a vision-capable reviewer against the demo renders, element by element
- Visual verdict: PASS
- Screenshots: ![Stream, own character](docs/reviews/3941/1-stream-self.png) ![Search open with the index](docs/reviews/3941/1b-search-open.png) ![A writer's journal](docs/reviews/3941/2-writer.png) ![An opened entry, another player](docs/reviews/3941/3-opened-other.png) ![Your journal](docs/reviews/3941/4-mine.png) ![The desk, Black selected](docs/reviews/3941/5-desk-black.png) ![Stream at 400px](docs/reviews/3941/6-phone.png)
- Comparison notes: the stream, the black band, the post mortem band with its reveal date, the First Journal band, the writer/IC date/title/About line, the seven-line clamp, the header's Search (quiet) beside Write and Your journal (both filled), the Search panel's four groups with the count on Since your last visit, the index table with the black row and the post-mortem glyph, the opened entry's order (text, tags, Praise, Nominate, Retort, Condemn, response count, responses with kind chips, then Mute writer and Block writer faint and last), the post mortem taking no actions, the writer plate with All / About Corvin Ashe · 2 / Written about them · 1 and no page heading above it, Your journal's eyebrow, name, Reveal / Remain sealed, Rivals only / Anyone and Write on one line, and the desk's pills, fields, After your death and the rewarded-entries line all match the demo. Five deviations are accepted and stated: the application's own header replaces the demo's fake one; Nominate is the application's existing icon button rather than the word; the plate's counts read "3 entries · 1 black" rather than the demo's wording; the phone capture shows the application shell's mobile-menu button overflowing the viewport by 10px, present on every page and untouched by this branch; and runtime behaviours the static demo cannot show (the date flip, the Search toggle) were exercised by the spec rather than pictured
- Tested interactions: the stream's first request carries `mark_visit=1` and later requests do not; clicking the IC date flips it to the posting date without opening the row; Search opens with `aria-expanded`, shows the four groups and the index, and a row click closes it and opens that entry; an opened entry shows tags, Praise, Retort, Condemn, the two responses inline, and Mute writer / Block writer for a non-own row; an opened post mortem shows no actions; `?writer=20` renders the plate and the three pills without the page heading; `?mine=1` renders the two switch groups and the own black entry; Write opens the desk, Black reveals After your death, and no help text renders; at 400px the journals column has no horizontal overflow
- Fixture/live boundary: the page, its components, the stylesheet, the router, the app shell and the token cascade are the real shipped code. Every `/api/**` call was intercepted and answered by fixtures shaped like the serializers (`src/world/journals/serializers.py`): the account (`/api/user/`), the roster entries, the journal list with `since_visit_count` and `visited_at`, entry detail with nested responses, the settings endpoint, nominations (empty), and persona search (empty); everything else returned 404. The visibility rule, the consent gate, the since-visit mark and the query bound are proven by the backend tests named in the ledger, not by these captures
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| real-surface | PASS | The shipped page, components and stylesheet rendered at the real route from the production build (identity above). | |
| one-visibility-rule | PASS | `VisibilityRuleTests` and `JournalPosthumousLeakTableTests` in `src/world/journals/tests/test_views.py`: a reader sees white and post mortems, the author sees own black, staff see all, `black_only` is ignored for non-staff, a `?deceased=` listing keeps its shape. | |
| row-is-quiet | PASS | `1-stream-self.png`: rows show writer, IC date, title, About, and clamped prose; no tags or actions until opened. | |
| open-in-place | PASS | `3-opened-other.png`: the opened row shows full text, tags, actions, responses and the respond form inside the stream. | |
| date-flip | PASS | The spec clicks the IC date and asserts the posting date replaces it with the row still closed. | |
| consent-gate | PASS | `3-opened-other.png` shows Retort and Condemn on an entry whose writer consented; `CondemnAndConsentGateTest` and `CanRetortTest` in `test_services.py` prove the service refuses with the neutral message otherwise. | |
| post-mortem-no-actions | PASS | The spec opens the post mortem and asserts no Praise and no Mute writer; `test_nominations.py` proves it is not nominable. | |
| search-not-a-mode | PASS | `1b-search-open.png` shows the panel and index above the stream; the spec closes it via a row click and asserts the table is gone and the entry is open. | |
| since-your-last-visit | PASS | `test_visited_at_names_the_previous_visit_and_since_cuts_on_it` in `test_views.py`: the response names the pre-advance mark and `since=` cuts on it. | |
| query-bound | PASS | `JournalListQueryCountTests` in `test_views.py`: the list's query count does not grow with the row count. | |
| writer-journal | PASS | `2-writer.png`: the plate, the counts, and All / About Corvin Ashe · 2 / Written about them · 1, with no page heading above the plate. | |
| your-journal | PASS | `4-mine.png`: eyebrow, name, Reveal / Remain sealed, Rivals only / Anyone and Write on one line; the own black entry below. | |
| desk-no-help-text | PASS | `5-desk-black.png`: White journal · Public / Black journal · Private, Title, Entry, About a character and Tags side by side, After your death, the rewarded-entries line, Discard and Post entry; the spec asserts no help copy renders. | |
| links | PASS | `Header.test.tsx`, `OffscreenActsPlate.test.tsx` and `CharacterSheetPage.test.tsx` pin the World menu entry, the Hall's Your journal, and the sheet's Journal link for both viewers. | |
| responsive | PASS | `6-phone.png`: one column at 400px; the journals column does not overflow (the shell's own menu button does, by 10px, on every page). | |
| no-errors | PASS | Seven Playwright tests pass with no page errors. | |
| fixture-boundary | PASS | Stated in full above: real page and shell, fixture API. | |
| migration | PASS | `0148_journal_about_consent_visit` is schema-only and additive; reviewed against the reviewing-migrations checklist before commit. | |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| [1] Band texts: "Black journal" / "Post mortem · date" / "First Journal" | Uppercase small-caps band, exact wording, post-mortem carries the reveal date | MATCH | `1-stream-self.png` |
| [1] Row: writer / IC date / title / About line | Writer name, IC date, title, "About **Name**" when set | MATCH | `1-stream-self.png` |
| [1] No actions on a collapsed row | No tags/Praise/etc. until clicked | MATCH | `1-stream-self.png` |
| [1] Header actions: Search / Write / Your journal | Search outlined (secondary); Write **and** Your journal both filled (equal, primary) | MATCH | `1-stream-self.png`: "Your journal" now renders filled/dark like Write; Search stays outlined |
| [Phone] Seven-line clamp | Body clamps at 7 lines, browser ellipsis on overflow | MATCH | `6-phone.png` ("harbor tolls", "First Journal" rows truncate mid-word) |
| [Phone] One column, nothing clipped | Single column, header buttons fit, no horizontal overflow | MATCH | `6-phone.png` |
| [3] Opened row order: text, tags, Praise/Nominate/Retort/Condemn, response count, responses w/ kind chips, Mute/Block last+faint | Exact sequence | MATCH | `3-opened-other.png` |
| [3] Post mortem opened shows no actions | Opening it adds no Praise/Retort/Mute row | MATCH | `3-opened-other.png`; `frontend/e2e/journals-reading-room.spec.ts:207-213`: proven by a post-screenshot assertion rather than pictured directly (unchanged, not a defect |
| [1b] Search groups: Find a writer / Show / About someone / Tags | Four labeled groups, same items and counts | MATCH | `1b-search-open.png`: tag list order differs, unspecified |
| [1b] Index columns: Date / Writer / Title / About / Replies | Same five columns, same header labels | MATCH | `1b-search-open.png`: built dates carry the year, demo's don't |
| [1b] The black index row | Dark-highlighted row for the viewer's own black entry | MATCH | `1b-search-open.png`: demo's decorative bullet dot before the title isn't reproduced |
| [2] Writer plate: name + counts | "Journal of" eyebrow, name, entry/black counts | MATCH | `2-writer.png`: counts wording differs — accepted variance |
| [2] Page-level heading above the plate | None — screen begins at the plate | MATCH | `2-writer.png`: the redundant "Journals" heading and Write/Your journal row above the plate are gone |
| [2] The three pills: All / About X · N / Written about them | All three pills, both non-"All" pills carry a count | MATCH | `2-writer.png`: "Written about them · 1" now carries a count |
| [4] Your journal: eyebrow + name + Reveal/Remain sealed + Rivals only/Anyone + Write | All five in one row (or one wrapped group) | MATCH | `4-mine.png`: Write now trails the two switch groups on the same line at 1280 wide |
| [5] Desk: White·Public/Black·Private, Title, Entry, About+Tags side by side, After your death, rewarded-entries line, Discard/Post entry | All present, After your death only for Black | MATCH | `5-desk-black.png` |
| [1,2,4,5] No help text anywhere | No explanatory prose beyond labels | MATCH | all built screenshots |

## Divergences

None. The four departures the first pass found (the Your journal button's weight, a page heading above the writer plate, no count on Written about them, Write dropping a line on Your journal) were fixed in 067e818c0 and ba3fb8f8d and re-checked at this revision.

## Unresolved findings

None
