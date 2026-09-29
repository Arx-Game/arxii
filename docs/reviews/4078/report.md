# Review evidence

- Reviewed revision: `6c4c288dbb37698b5acea1cdad64597924d7608c`
- Reviewer: implementing agent (Claude Code) for the rendered page; `enumerated-set-reviewer` for the payload family
- Reviewer verdict: PASS
- Application/build identity: production bundle from `pnpm build` at 602a0e40697ebefde8e4cc2e1f8c51962254a7b2; the reviewed revision adds one backend test and the evidence spec on top of it and changes nothing the page renders, served by `vite preview` on port 4173
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; backend payload read from this branch's `/api/character-creation/starting-areas/` through DRF's test client against a copy of the live realms
- Viewports/themes: 1280x900 and 390x1100, the character creation paper theme (the stage has one)
- Approved design: issue #4078 (lightweight lane, no demo page); the change re-sources one existing tag and adds no element
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Origin at 1280](docs/reviews/4078/origin-tags-1280.png) ![The Bonespire opened](docs/reviews/4078/origin-bonespire-open-1280.png) ![Origin at 390](docs/reviews/4078/origin-tags-390.png)
- Comparison notes: compared each area's tag on the rendered page with the `formal_name` its realm carries in the API payload. All six match, and the area whose realm has no formal name shows the realm's plain name. "The Northlands" appears nowhere. At 390 wide a long tag moves the Select mark to its own line; that is the existing `flex-wrap` rule on `.entry-tag` from #4023 and the removed table's Inferna tag was longer than the new one, so it is unchanged behavior.
- Tested interactions: load `/characters/create` on the Origin stage with no realm chosen; read every tag; open The Bonespire and read its "About Aythirmok" link. No page errors were raised.
- Fixture/live boundary: the page, router, hooks and bundle are real. Every `/api/**` response is a fixture. The starting-area rows carry the ids, names, realm names and formal names the branch's API returned for the six live areas, with descriptions replaced by a placeholder line; the seventh row (blank formal name) is invented to show the fallback. The serializer itself is covered against a real database by `world.character_creation.tests.test_public_reads`.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Tag on Kys G'Sheer | The Kingdoms of Ariwn | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on Perdition | Grand Principality of Inferna | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on Salvation | The Holy Revolutionary Republic of Luxen | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on Tenebrum | The Umbral Empire | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on The Bonespire | The Kingdom of Aythirmok | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on The City of Arx | The Necropolis | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Tag on an area whose realm has no formal name | the realm's plain name | MATCH | docs/reviews/4078/origin-tags-1280.png |
| Link under an opened entry | About Aythirmok | MATCH | docs/reviews/4078/origin-bonespire-open-1280.png |
| Tags at phone width | same seven tags, none clipped | MATCH | docs/reviews/4078/origin-tags-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01-bonespire-tag | PASS | docs/reviews/4078/origin-tags-1280.png; `frontend/e2e/evidence/cg-realm-tag-4078.spec.ts` asserts the tag text | |
| A02-tag-follows-admin | PASS | `test_starting_area_carries_its_realms_formal_name` in `world.character_creation.tests.test_public_reads`; the tag reads the payload field | |
| A03-no-hardcoded-realm-name | PASS | `grep -rn REALM_NAMES frontend/src` returns nothing at the reviewed revision; `enumerated-set-reviewer` found no other hand-written realm-name table | |
| A04-blank-formal-name | PASS | `test_starting_area_formal_name_is_blank_when_the_realm_has_none`; OriginStage.test.tsx fallback case; docs/reviews/4078/origin-tags-1280.png | |

## Unresolved findings

- None
