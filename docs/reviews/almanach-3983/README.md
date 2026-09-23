# Almanach de Catenys — review evidence (#3983)

Screenshots of the REAL built app (the app's own routes and components; only
`/api/` calls are stubbed) alongside the approved plates, for the
`demo-fidelity-reviewer` to compare. Spec:
`frontend/e2e/evidence/almanach-3983.spec.ts`; fixtures:
`frontend/e2e/evidence/fixtures/*.ts`.

- Rendered commit: `2a9d6b596ced951c5aefe12832c6a7438ef87c3c` (the app as built for this run; the evidence commit sits on top of it)
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
| F-I | pass | Fervor selected; Claim column clickable |
| F-I b | pass | Solfatara expanded + selected, Fervor/Arsura held by Candela |
| F-II | pass | reached by a real click on Claim Fervor |
| F-III | pass | consort "Dario · born Solano" added, founder's own panel open |
| F-IV | pass | Fervor's own top-rung section, 2 granted baronies |
| F-V | pass | |
| F-VI | pass | review chapter + the post-submit night plate, two shots |

## Findings for the reviewer

The first evidence run (346102934) found two app defects and captured the
founder screens through harness workarounds. Both are fixed on the branch and
this run has no workarounds: every interaction is a real pointer click with
Playwright's actionability checks, and F-II onward follow a real "Claim Fervor"
click rather than a seeded draft.

1. The founder-mounted Almanach's `main.chapter` was being laid out by
   character creation's own `.interview .chapter` grid (cg.css:317), which
   pushed every field into a 12rem side column under `aside.record` and made
   the rail intercept clicks. Fixed in `c7a86b6ce` (an interview-scoped reset
   in `almanach.css`); the spread also now sizes to its container
   (`0b43bf647`: two columns under 64rem, one under 44rem, grid children
   `min-width: 0`).
2. `FounderAlmanach.handleClaim` wrote title, realm and template back to back
   and each write spread the draft captured when the handler started, so only
   the last survived and the House chapter was stranded on "Loading". Fixed in
   `0b43bf647` (`useFounderDraft` mutators build on a ref of the latest draft);
   regression tests in `founderDraft.test.ts` and `FounderAlmanach.test.tsx`.

Inside character creation the founder Almanach renders as two columns (the
contents rail as a strip above chapter | record) because the interview's
reading column is narrower than three railed columns; the staff routes render
the plates' three columns. That is a container-driven divergence from the
founder plates' full-page mock, ruled acceptable in the Plan B ledger.

## Founder journey spec (Task 7)

`frontend/e2e/almanach-founder.spec.ts` passes
(`pnpm exec playwright test e2e/almanach-founder.spec.ts` → 1 passed). Every
interaction is a real pointer click with Playwright's actionability checks;
the journey claims the demo duchy with a real click on its Claim button and
walks House, Family (adds a spouse), Land, Estate and the Record to Submit,
asserting the posted nested payload. The first run of this spec failed on the
two defects recorded above; both are fixed on the branch. One selector was
tightened (`getByRole('button', { name: 'Lady Osrin', exact: true })`) to avoid
the button/dd text duplication strict-mode ambiguity.
