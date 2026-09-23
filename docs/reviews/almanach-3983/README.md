# Almanach de Catenys — review evidence (#3983)

Screenshots of the REAL built app (the app's own routes and components; only
`/api/` calls are stubbed) alongside the approved plates, for the
`demo-fidelity-reviewer` to compare. Spec:
`frontend/e2e/evidence/almanach-3983.spec.ts`; fixtures:
`frontend/e2e/evidence/fixtures/*.ts`.

- Rendered commit: `<FILLED IN RUN PHASE — git rev-parse HEAD>`
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

`<FILLED IN RUN PHASE — pass/fail per screen from the Playwright run>`

## Findings for the reviewer

`<FILLED IN RUN PHASE — any screen where the fixture/harness is honest but the
BUILT APP diverges from its own plate; left for demo-fidelity-reviewer to
judge, not fixed here>`

## Founder journey spec (Task 7)

`frontend/e2e/almanach-founder.spec.ts` — `<FILLED IN RUN PHASE — pass/fail,
and what changed if its selectors had drifted>`
