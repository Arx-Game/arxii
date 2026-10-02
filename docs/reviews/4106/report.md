# Review evidence

- Reviewed revision: `488d651cc8629f9b1708107ba6351ac74df3751f`
- Reviewer: implementing agent (Claude Code), comparing the rendered Final Touches stage and the character sheet against the issue's concrete scenarios ("Two aims, one hidden", "Exiled, still of the house")
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4173
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900 and 390x1100, the CG page's parchment theme and the sheet's ember plate (each page has one)
- Approved design: issue #4106 (standard lane, nonvisual beyond two small controls, no demo page); the goal mark reuses the `entry-mark` control the stage's Entry rows already carry, the standing word reuses the sheet's `Tag` primitive beside the membership
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![Final Touches, two goals, neither secret](docs/reviews/4106/final-touches-unmarked-1280.png) ![Final Touches, the short-term goal marked Secret](docs/reviews/4106/final-touches-marked-1280.png) ![The owner's sheet: both goals, the secret one marked](docs/reviews/4106/sheet-owner-goals-1280.png) ![A friend's sheet: one goal, no mark](docs/reviews/4106/sheet-friend-goals-1280.png) ![The Ties tab: House Katta, Princess, Exiled; the Academy unmarked](docs/reviews/4106/sheet-ties-standing-1280.png) ![Final Touches at phone width](docs/reviews/4106/final-touches-390.png)
- Comparison notes: the goal row gains one control after Points, a "Secret" checkbox, checked once pressed; nothing else on the row moved (the first cut read "Keep to yourself" / "Kept to yourself"; ApostateCD ruled it too ambiguous and it is "Secret", pressed or not, in the reviewed revision). On the sheet the Goals and guidelines band lists the owner's two goals and puts "secret" in the band's note style after the kept one, on one line. A friend's payload carries one goal and the band shows one with no mark. The first cut put the sheet mark on `ActorSheetSection`, which nothing has mounted since #3898; this harness mounting the real page is what caught it, and the mark moved to `GuidelinesBand`. On the Ties tab the membership entry shows the verdict as a tag under the house's name with the reason as its title; the Academy membership, in favour, carries no tag.
- Tested interactions: open `/characters/create` at Final Touches with two goals in the draft; press the second goal's mark and read its pressed state and text; press Back and read the draft PATCH the stage sends (the kept goal carries `is_secret: true`, the other does not). Open `/characters/1` as the owner and as a friend; open the Ties tab and read the House Katta entry's tag and its title. No page errors were raised.
- Fixture/live boundary: the pages, router, stage, band, standing block and bundle are real. Every `/api/**` response is a fixture: a draft at stage 10 with two goals, one goal-domains list, a roster entry and a sheet payload shaped like `CharacterSheetPayload` in two readings (owner: both goals; friend: the server-dropped one missing) with two memberships, one exiled with a note. The server-side gate (the section builder dropping secret goals for anyone but the owner or staff, and the favor label on the standing entry) is proved by `world.character_sheets.tests.test_viewset`, not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Goal row mark, unpressed | "Secret", empty box, after Points | MATCH | docs/reviews/4106/final-touches-unmarked-1280.png |
| Goal row mark, pressed | "Secret", checked, `aria-pressed=true` | MATCH | docs/reviews/4106/final-touches-marked-1280.png |
| Draft PATCH on leaving the stage | the pressed goal carries `is_secret: true`, the other does not | MATCH | `cg-secret-goal-favor-4106.spec.ts` asserts the body |
| Owner's goals band | both goals, "secret" after the kept one only | MATCH | docs/reviews/4106/sheet-owner-goals-1280.png |
| Friend's goals band | the public goal only, no mark | MATCH | docs/reviews/4106/sheet-friend-goals-1280.png |
| Membership in exile | "Exiled" tag under House Katta, reason as its title | MATCH | docs/reviews/4106/sheet-ties-standing-1280.png |
| Membership in favour | no tag | MATCH | docs/reviews/4106/sheet-ties-standing-1280.png |
| Phone width | the mark fits the row at 390px | MATCH | docs/reviews/4106/final-touches-390.png |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-goal-kept-at-cg | PASS | `FinalTouchesStage.test.tsx` "marks a goal Secret and saves it in the draft" and the e2e PATCH assertion; `test_actor_sheet.py` proves finalize writes `is_secret` | Decision 1, 2 |
| R02-secret-goal-owner-and-staff-only | PASS | `test_viewset.py` `test_a_secret_goal_is_the_owners_alone_whatever_the_section_tier_says` (owner, friend with goals opened, stranger, staff) | Decision 1 |
| R03-secret-stays-hidden-when-section-opens | PASS | the same test opens `goals_visibility` to everyone and the friend still sees one | user story 2 |
| R04-goal-endpoint-accepts-mark | PASS | `world.goals.tests.test_views` round-trips `is_secret` through `update_all` | Decision 2 |
| R05-membership-favor-and-note | PASS | `OrganizationMembership.favor`/`favor_note`; admin inline and list show them; `test_viewset.py` `test_a_houses_verdict_rides_the_standing_entry` | Decision 3 |
| R06-exiled-still-a-member | PASS | no reader of membership changed; the row stays a membership (`exiled_at` untouched) | Decision 3, user story 5 |
| R07-default-shows-nothing | PASS | the serializer emits `''` for in favour; `ReputationTab.test.tsx` "shows the house's verdict beside a membership, and nothing for the default" and the Ties capture | Decision 5 |
| R08-in-play-verb | OUT_OF_SCOPE | admin only in this change | Decision 4 |

## Unresolved findings

- None
