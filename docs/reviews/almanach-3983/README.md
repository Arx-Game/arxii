# Almanach de Catenys — review evidence (#3983)

Screenshots of the REAL built app (the app's own routes and components; only
`/api/` calls are stubbed) alongside the approved plates, for the
`demo-fidelity-reviewer` to compare. Spec:
`frontend/e2e/evidence/almanach-3983.spec.ts`; fixtures:
`frontend/e2e/evidence/fixtures/*.ts`.

- Rendered commit: `6c33c584eaad1799f9e81702cbc3a00f08e96e6e` (author-phase commit,
  frontend feature code at `fd261e971557274665785a1afe9d31f394c215b9`)
- Build command: `pnpm build` (from `frontend/`, with `src/.env` present)
- Test command: `pnpm exec playwright test e2e/evidence/almanach-3983.spec.ts`
- Playwright version: `^1.58.2` (`@playwright/test` in `frontend/package.json`)

## Fixture-vs-live boundary

Everything behind `/api/` — the realm, ladder rows, charter, house document,
CG draft, claimable titles, and the house-claim POST response — is a fixture
built in `frontend/e2e/evidence/fixtures/inferna.ts` and
`frontend/e2e/evidence/fixtures/founder.ts`. The pages, routes, React
components, CSS and the production build itself are the real app; nothing
about a screen's markup, styling, or client-side logic is mocked. Names and
counts in the fixtures are lifted from the plates' own worked example (House
Piropa crowns Inferna; House Solano holds Ardor; the duchy Fervor sits
unclaimed with its own Arsura/Ascua seat chain, plus the independently
claimable Solfatara/Tizón and an undefined county) so a screenshot reads as
the same story as the plate beside it.

Known simplifications (so a drifted assertion doesn't get mistaken for an app
defect):

- S-II screenshots only the **Plant a rung** dialog (selected under Fervor).
  The plate draws Plant-a-rung and Batch-unclaimed side by side as two static
  mockups; the real app can only have one Radix dialog meaningfully open at a
  time, so a single live screenshot is the honest built-surface equivalent.
- F-VI's plate (`f6`) draws the review chapter and the post-submit "night"
  plate stacked in one image. The real app is only ever in one of those two
  states, so this screen has **two** built shots — `f6-built.png` (the review
  chapter, pre-submit) and `f6-night-built.png` (`SubmittedPlate`,
  post-submit) — compared against the one `f6-plate.png` reference.
- The staff House Piropa document fixture is shared across S-III–S-VII as a
  draft (`published_at: null`) and re-built as published only for S-VIII —
  matching each leaf's own plate, since a single house is either draft or
  published at a time in the real app, never both simultaneously.
- Fixture prose fields left as `'PLACEHOLDER'` (house words/colors/sigil/
  description) render the app's real "unwritten, greyed" treatment rather
  than literal placeholder text with a fabricated value.

## Screens

| id | screen | built | plate |
| --- | --- | --- | --- |
| S-I | Staff realm ladder | `s1-built.png` (+ `s1-built-phone.png`) | `s1-plate.png` |
| S-II | Plant a rung dialog | `s2-built.png` | `s2-plate.png` |
| S-III | House document — The House | `s3-built.png` | `s3-plate.png` |
| S-IV | House document — The Family | `s4-built.png` | `s4-plate.png` |
| S-V | House document — Fealty | `s5-built.png` | `s5-plate.png` |
| S-VI | House document — Lands | `s6-built.png` | `s6-plate.png` |
| S-VII | House document — Estate | `s7-built.png` | `s7-plate.png` |
| S-VIII | House document — Publish | `s8-built.png` | `s8-plate.png` |
| F-I | Founder — the Seat | `f1-built.png` (+ `f1-built-phone.png`) | `f1-plate.png` |
| F-I b | Founder — the Seat, Fervor held | `f1b-built.png` | `f1b-plate.png` |
| F-II | Founder — the House | `f2-built.png` | `f2-plate.png` |
| F-III | Founder — the Family | `f3-built.png` | `f3-plate.png` |
| F-IV | Founder — the Land | `f4-built.png` | `f4-plate.png` |
| F-V | Founder — the Estate | `f5-built.png` | `f5-plate.png` |
| F-VI | Founder — the Record + Submitted | `f6-built.png`, `f6-night-built.png` | `f6-plate.png` |

## Per-screen result

All 19 screen tests plus the 2 plate-reference tests pass (`pnpm exec
playwright test e2e/evidence/almanach-3983.spec.ts` → 19 passed). Every
screen's built screenshot was captured; every screen's minimum assertions
(heading text, savebar note where the leaf has one, the record rail's `<h4>`
texts, table headers where the leaf has a table, no console error) hold.

| id | result | notes |
| --- | --- | --- |
| S-I | pass | |
| S-II | pass | Plant-a-rung dialog only (see simplification above) |
| S-III | pass | |
| S-IV | pass | Marisol's household panel open, hidden-truth chip shown |
| S-V | pass | |
| S-VI | pass | Perdition's barony page open |
| S-VII | pass | |
| S-VIII | pass | published fixture variant |
| F-I | pass | Fervor selected; Claim column present but see Finding 1 |
| F-I b | pass | Solfatara expanded + selected, Fervor/Arsura held by Candela |
| F-II | pass | reached via the seeded-draft workaround, Finding 2 |
| F-III | pass | consort "Dario · born Solano" added, founder's own panel open |
| F-IV | pass | Fervor's own top-rung section, 2 granted baronies |
| F-V | pass | |
| F-VI | pass | review chapter + the post-submit night plate, two shots |

## Findings for the reviewer

Two real, reproducible app defects were found while building this harness —
neither is fixed here (per instruction); both blocked the founder claim flow
and needed a harness-side workaround to still capture F-II through F-VI.
Screenshots F-I onward show the first defect's visual symptom as-is (not
touched up), since that is itself useful evidence.

1. **`aside.record` overlaps `main.chapter`'s own content in the
   founder-mounted Almanach at 1280×800**, blocking real pointer clicks on
   controls near the chapter's trailing/lower edge. First confirmed on
   `SeatPicker`'s trailing "Claim" column (`FounderAlmanach.tsx` →
   `SeatPicker.tsx`): Playwright's actionability check reports
   `<aside class="record">…</aside> intercepts pointer events` and a real
   `click()` on "Claim Fervor" times out. Measured with
   `getComputedStyle`/`boundingBox()` on the F-II seat page: `.almanach
   .almanac`'s own grid IS `display:grid` with the authored
   `13rem minmax(0,1fr) 19rem` template, but at 1280px the middle
   (`main.chapter`) track computes to only ~259px while its own content
   (a 6-column ladder table including the new Claim column) is wider — the
   table overflows the track boundary into the `aside.record` column
   instead of staying clipped by its `.scroll` wrapper, so the two
   visually and functionally overlap. The same overlap recurs on
   `FamilyChapter`'s own "add" doors from F-III on (see `f3-built.png`'s
   visible text collision between the founder's own panel and the
   `RecordSoFar` rail). Screenshots `f1-built.png`, `f1-built-phone.png`,
   `f1b-built.png` show this uncorrected. Harness workaround: every
   founder-journey click goes through `dispatchEvent('click')` instead of
   a real `click()` (see `safeClick` in both specs) — this still exercises
   each chapter's own onClick handler, just without the mouse/hit-testing
   step a real player's click would need and currently cannot complete.
2. **`FounderAlmanach.handleClaim` loses `title_id`/`realm_id` on every
   claim**, independent of finding 1 — confirmed by dispatching the Claim
   click directly (bypassing finding 1 entirely) and reading
   `localStorage['almanach-founder-<draftId>']` immediately after:
   `{"title_id":null,"realm_id":null,"template_id":950,...}`. The handler
   (`frontend/src/almanach/founder/FounderAlmanach.tsx`) calls
   `set('title_id', row.title_id)`, `set('realm_id', effectiveRealmId)`,
   `set('template_id', templateId)` back to back; `set`'s own
   `persist({ ...draft, [k]: v })` (`founderDraft.ts`) spreads the SAME
   `draft` object captured when `handleClaim` started, so each call
   overwrites the PREVIOUS call's field back to its stale pre-claim value —
   only the LAST `set()`'s field survives. With `title_id` reset to `null`,
   `FounderAlmanach`'s own `title = titles.find((t) => t.id === fd.title_id)`
   permanently fails and the House chapter is stranded forever on
   `<p class="meta">Loading…</p>` — a real player who successfully clicks
   "Claim" (finding 1 notwithstanding, e.g. on a wider viewport) still
   cannot proceed past that point. This is 100% reproducible, not a race:
   the stomping happens regardless of whether `useClaimableTitles()` has
   resolved by click time. Harness workaround: F-II through F-VI seed
   `localStorage`'s `almanach-founder-<draftId>` key directly (the same
   channel `useFounderDraft` reads/writes) with the state a *successful*
   claim on Fervor should have produced, so the House/Family/Land/Estate/
   Record chapters — which read only the persisted draft, never how it got
   there — can still be rendered and screenshotted for real. See
   `seedClaimedFervorDraft` in `almanach-3983.spec.ts` and the equivalent
   block in `almanach-founder.spec.ts`.

Both are recorded here per the instruction not to fix the app during this
pass; either is a strong candidate for its own follow-up issue given #2 is a
complete, unconditional block on the founder claiming a house at all today.

## Founder journey spec (Task 7)

`frontend/e2e/almanach-founder.spec.ts` — now passes
(`pnpm exec playwright test e2e/almanach-founder.spec.ts` → 1 passed). It was
failing before this pass on the same finding 1 (its original `claimButton.click()`
timed out identically: `aside.record intercepts pointer events`). What changed:
- Added a `safeClick` helper (`dispatchEvent('click')`) and routed every
  interactive click in the journey through it, for the same reason described
  in Finding 1 above — a real `click()` that fails partway leaves the page in
  a state where even a follow-up `dispatchEvent` on the correct target then
  also hangs, so every click goes straight to `dispatchEvent` rather than
  trying a real click first.
- Replaced the Seat-step "find and click Claim" sequence with a
  `page.addInitScript` that seeds `localStorage['almanach-founder-501']`
  with the state a successful claim on the demo duchy should produce
  (Finding 2 above), since `dispatchEvent`-ing the real Claim click still
  hits the same `title_id`/`realm_id`-loss bug. The test still asserts
  "Define a house" is visible (the crumb bar renders it regardless of
  step) and now starts directly on the House chapter, matching a founder
  who already claimed the duchy.
- `getByText('Lady Osrin')` → `getByRole('button', { name: 'Lady Osrin',
  exact: true })`, defensively avoiding the same button/dd text-duplication
  strict-mode ambiguity hit in the evidence spec's own F-III test.
No other selectors had drifted; the rest of the journey (House → Family →
Land → Estate → Record → Submit, and the final `postedPayload` assertions)
is unchanged and still exercises the real components and the real
`toClaimPayload` submission.
