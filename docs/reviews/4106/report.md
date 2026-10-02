# Review evidence

- Reviewed revision: `9212c2bc015f1c12e1e360a95513680e26f4b46d`
- Reviewer: implementing agent (Claude Code), comparing the rendered character sheet against the issue's concrete scenarios as amended on 2026-10-02 (goals are the owner's and staff's; "Exiled, still of the house")
- Reviewer verdict: PASS
- Application/build identity: production bundle from `vite build` at the reviewed revision, served by `vite preview` on port 4173
- Environment: Linux devcontainer, Playwright 1.58.2 Chromium headless; every `/api/**` response is a fixture (no Django behind the preview build)
- Viewports/themes: 1280x900 and 390x1100, the sheet's ember plate (the page has one theme)
- Approved design: issue #4106 (standard lane, nonvisual beyond one tag, no demo page), amended by ApostateCD on PR review: the secret-goal half is withdrawn and goals read to the owner and staff only; the standing word reuses the sheet's `Tag` primitive beside the membership
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![The owner's sheet: both goals in the band](docs/reviews/4106/sheet-owner-goals-1280.png) ![A friend's sheet: the answers, no goals column](docs/reviews/4106/sheet-friend-goals-1280.png) ![The Ties tab: House Katta, Princess, Exiled; the Academy unmarked](docs/reviews/4106/sheet-ties-standing-1280.png) ![The Ties tab at phone width](docs/reviews/4106/sheet-ties-standing-390.png)
- Comparison notes: the Goals and guidelines band lists the owner's two goals under "Wants, soon" and "Wants, someday" with no mark of any kind (the Secret mark from the first cut is gone, on the stage and on the sheet); its note now reads "Goals are yours and staff's" instead of the old "Yours, your friends', or everyone's", which described a tier nothing could set. A friend's payload carries no goals and the band shows the three answers alone, with no empty goals column. On the Ties tab the membership entry shows the verdict as a tag under the house's name with the reason as its title; the Academy membership, in favour, carries no tag. The first cut's CG screenshots are removed with the control they showed.
- Tested interactions: open `/characters/1` as the owner and read the band; open it as a friend and read the band; open the Ties tab as a friend and read the House Katta entry's tag and its title; the same at 390px. No page errors were raised.
- Fixture/live boundary: the page, router, band, standing block and bundle are real. Every `/api/**` response is a fixture: a roster entry and a `CharacterSheetPayload` in two readings (owner: two goals; friend: none, as the server now sends to anyone but the owner or staff) with two memberships, one exiled with a note. The server-side gate (`show_goals = privileged`, no tier) and the favor label on the standing entry are proved by `world.character_sheets.tests.test_viewset`, not by this harness.
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Owner's goals band | both goals, numbered, no mark | MATCH | docs/reviews/4106/sheet-owner-goals-1280.png |
| Band note | "Goals are yours and staff's. Strangers learn the rest in play, or hear a version as rumor." | MATCH | docs/reviews/4106/sheet-owner-goals-1280.png |
| Friend's goals band | the answers only, no goals column | MATCH | docs/reviews/4106/sheet-friend-goals-1280.png |
| Membership in exile | "Exiled" tag under House Katta, reason as its title | MATCH | docs/reviews/4106/sheet-ties-standing-1280.png |
| Membership in favour | no tag | MATCH | docs/reviews/4106/sheet-ties-standing-1280.png |
| Phone width | the tag fits the entry at 390px | MATCH | docs/reviews/4106/sheet-ties-standing-390.png |
| Final Touches goal row | unchanged from main (no Secret control) | MATCH | `FinalTouchesStage.tsx` is byte-identical to `origin/main` |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01-goals-owner-and-staff-only | PASS | `test_viewset.py` `test_goals_are_the_owners_and_staffs_whoever_else_is_allowed` (owner reads both; a friend on the allow list and a stranger get `[]`); `show_goals = privileged` in the serializer | Amendment 2026-10-02 |
| R02-goals-tier-removed | PASS | `0171_membership_favor_and_goals_untiered` drops `goals_visibility`; `visibility_field_names()` derives the tier list so no stale copy remains (`test_privacy_tiers.py` still green) | Amendment 2026-10-02 |
| R03-no-secret-flag-ships | PASS | `is_secret` absent from `CharacterGoal`, the goals serializer, the CG finalize path, `GoalEntry` and the stage; the branch's earlier flag never reached main | Amendment 2026-10-02 |
| R04-membership-favor-and-note | PASS | `OrganizationMembership.favor`/`favor_note`; admin inline and list show them; `test_viewset.py` `test_a_houses_verdict_rides_the_standing_entry`; `test_admin_codex_grants.py` posts the field | Decision 3 |
| R05-exiled-still-a-member | PASS | no reader of membership changed; the row stays a membership (`exiled_at` untouched) | Decision 3, user story 5 |
| R06-default-shows-nothing | PASS | the serializer emits `''` for in favour; `ReputationTab.test.tsx` "shows the house's verdict beside a membership, and nothing for the default" and the Ties capture | Decision 5 |
| R07-in-play-verb | OUT_OF_SCOPE | admin only in this change | Decision 4 |
| R08-sharing-mechanism | OUT_OF_SCOPE | a per-viewer, per-section grant is #4113 (`needs-design`) | Amendment 2026-10-02 |

## Unresolved findings

- None
