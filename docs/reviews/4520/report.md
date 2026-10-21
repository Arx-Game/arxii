# Review evidence

- Reviewed revision: `e27097cd8e8cf87e1f2ca06cabd5ea976581a0d6`
- Reviewer: `demo-fidelity-reviewer agent (local); first pass FAIL on one defect (the picker's chips dropped each signal's detail), fixed in the last code commit; the other three surfaces PASS`
- Reviewer verdict: `PASS`
- Application/build identity: this branch's code, Django dev server on :4920 (`arx manage runserver`, not started with arx start) against a scratch Postgres database rt_4520b built with tools/build_schema.py; world rows made by a throwaway script through the real commands
- Environment: Linux devcontainer, Chromium (Playwright), Postgres. Own database and port; no other session's server or database touched. The React picker was not run in a browser (BLOCKED: it needs a mission or scene check UI session); it is covered by a component test and the telnet/real-command runs below.
- Viewports/themes: 1300 px wide desktop, light theme
- Approved design: local copy of the demo for spec #4462 (demo.html: "Calling on the Highwind while wearing it", "Invocation detail at a festival", Devotion config "Worn pieces and invocations", Being Service builder favored facets and side panel)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![1](docs/reviews/4520/1-invocation-detail.png) ![2](docs/reviews/4520/2-builder.png) ![3](docs/reviews/4520/3-devotion-config.png)
- Comparison notes: In scope: the staff invocation page (the GM detail), the Being Service builder's favored-facets table and side panel, the Devotion config fieldset, the picker's worn-piece table. Accepted divergences: the builder rail sits below the stats rather than first; the demo's per-facet supplier links are plain text and the template count is not a link; the admin invocation page adds Worn ease and Bonus rows; the steward panel shows the same table from the pledge's invocations (checked by source and a component test, not in a browser); "held 150 days" where the demo says "3 weeks". Out of scope: keepsakes, trophies, requested items, Relic points (slice 4).
- Tested interactions: through telnet commands as the characters (craft create for=Linnet, give, market/commission with a name and description, wear, invoke Highwind, check Perception at hard /invoke Highwind, sacrifice); ran ten daily outfit trickle ticks; read the staff invocation page; in the browser edited Kestrel's ease and earning rate on the builder, saved and read them back with the preview recomputed
- Fixture/live boundary: the world was seeded by a script (people, shop, being, relationships); every step shown was a real command or page. Rolls were real and random (no forced outcome): a commission failed twice before succeeding, which is why the run repeats it.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Invocation detail table | worn piece, signal, detail, points, favored facet row "(the gate; ease 2 per point)", summary of points and ease | MATCH | ![1](docs/reviews/4520/1-invocation-detail.png) |
| Favored facets table | Facet, Invocation ease points, Earning bonus percent, Delete, per-meaning-point help | MATCH | ![2](docs/reviews/4520/2-builder.png) |
| Side panel | who supplies each facet, worn ease preview at 4 points and at the cap, cap of 40 | MATCH | ![2](docs/reviews/4520/2-builder.png) |
| Devotion config fieldset | five worn-piece fields in the demo's order and help | MATCH | ![3](docs/reviews/4520/3-devotion-config.png) |
| Picker table | piece, what it means chips with detail, counts "N points x E = eased X", bought piece chip, limits note | MATCH | the component test  frontend/src/worship/__tests__/CallOnFavor.worn.test.tsx |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| worn-ease | PASS | live: coat of 7 points (carried 2, made by a tie 2, gift 1, made for 1, designed 1; computed by hand from the rules) shown as "7 points x 2 = eased 14", difficulty 75 to 61; the roll itself is eased once (test_worn_pieces asserts the check's target difficulty equals base minus the recorded ease) | |
| bought-adds-zero | PASS | live: a Kestrel brooch bought for 4000 listed "bought; no history beyond holding it", 0 ease, before and after ten trickle ticks that fed it the same resonance | |
| caps | PASS | test_worn_pieces: three pieces count highest first, one piece capped at 8 points, total ease capped at 40 | |
| earning-rate | PASS | live: rate 100, then 107 with the coat on (matching 7 points x 1%), 108 after resonance fed, 100 once the coat is given up | |
| resonance-fed | PASS | live: 10 daily ticks gave the coat 30 Gale (favored) = 3 points, the brooch fed the same read 0; counted at the shrine and kept on the offering | |
| give-up-removes | PASS | live: sacrificing the coat removes its ease and bonus from invoke and the rate; its signals including resonance fed kept on the offering | |
| gm-detail | PASS | shot 1; FavorInvocation row with the piece and signals; steward panel test | |
| builder | PASS | shot 2; edited and saved in the browser, read back with the preview recomputed | |
| migration | PASS | just prod-migration-check: forward, back, forward over the newest production dump, RESULT: PASS; migration-reviewer: no findings | |

## Unresolved findings

- None
