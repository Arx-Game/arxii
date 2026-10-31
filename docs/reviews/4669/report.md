# Review evidence: #4669 staff technique builder Gift list

- Reviewed revision: `85ff89e4427389c8d2627bd331d39ad81a3d97e4`
- Reviewer: Claude Opus 5.5 (implementing agent; no demo exists, so demo-fidelity-reviewer does not apply)
- Reviewer verdict: PASS
- Application/build identity: production bundle built with `pnpm build` from the reviewed revision, served by Evennia (banner `Arx Server 5.0.1 (rev 6d72b737a)`; the later commit c639d626f touches only the skill doc and the evidence spec)
- Environment: own Evennia server on :4001 against a throwaway Postgres database `rt_4669` (dropped afterwards), headless Chromium via Playwright, one worker
- Viewports/themes: 1280x720 desktop, light theme
- Approved design: none; the issue is a bug fix with no demo. The expected result comes from the issue: staff see the gift catalog in the builder's Gift picker.
- Visual review: completed against the running app, before (main's getGifts) and after (this branch)
- Visual verdict: PASS
- Screenshots: ![Builder with the fix](docs/reviews/4669/builder.png) ![Gift picker open with the fix](docs/reviews/4669/gift-picker-open.png) ![Builder on main](docs/reviews/4669/before-main.png)
- Comparison notes: on main the page shows "Something went wrong / l.map is not a function" instead of the builder. With the fix the full form renders, the Gift field defaults to the first gift, and opening it lists the gifts in name order. The screenshots were taken at c639d626f; the one later code commit, 85ff89e44, changes only the GiftListItem type alias in frontend/src/character-creation/types.ts (`git diff --stat c639d626f 85ff89e44 -- . ":!docs/reviews"`: that 1 file), which TypeScript erases at build, and `tsc -b` passes on it.
- Tested interactions: log in as the staff account through the login form; open /techniques/build; read the /api/magic/gifts/ response the page fetched; open the Gift picker and count its options; repeat on a bundle built from main's api.ts
- Fixture/live boundary: everything live. No /api route was mocked. Data: the e2e_test_account seed made staff, plus 25 Gift rows named "RT Ashfall" to "RT Zephyr" (more than the endpoint's default page of 20)
- Overall outcome: PASS

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R1-builder-renders | PASS | With the fix, /techniques/build renders the full form for staff (builder.png); on main the same page crashed with "l.map is not a function" (before-main.png) | none |
| R2-picker-lists-gifts | PASS | Playwright opened #tech-gift and counted 25 options, "RT Zephyr" (the 25th) among them (gift-picker-open.png; spec frontend/e2e/evidence/technique-builder-gifts-4669.spec.ts) | none |
| R3-real-response-shape | PASS | The live response was an envelope, not a list: count 25, results 25 items; server log shows GET /api/magic/gifts/?page_size=100 returning 200 | none |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Builder page | Form renders for a staff account, no error card | MATCH | builder.png |
| Gift field | Shows a gift name, not empty | MATCH | builder.png shows "RT Ashfall" |
| Gift picker list | Lists every gift, including past the 20th | MATCH | gift-picker-open.png plus the 25-option count in the spec |

## Unresolved findings

None
