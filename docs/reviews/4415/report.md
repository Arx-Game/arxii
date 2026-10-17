# Review evidence

- Reviewed revision: `232e03774f59810e6b4d91a2bd8eb6697661cc3f`
- Reviewer: `demo-fidelity-reviewer agent (local), two passes`
- Reviewer verdict: `PASS`
- Application/build identity: production frontend bundle built with pnpm from this branch (frontend unchanged since 9702b9933), served by the branch's own Evennia server on :4001 against a throwaway Postgres database rt_4415, running 232e03774
- Environment: Linux devcontainer, Chromium (Playwright, 1 worker), Evennia/Django backend on Postgres, database built with tools/build_schema.py and seeded by a throwaway script; telnet driven over a real socket on :4000; the lapse sweep run by the server's own scheduler
- Viewports/themes: 1500x1100 desktop, light theme
- Approved design: https://claude.ai/artifact/1926LF7noogf1hKijgL3v8 (spec on #4121, slice 4: items 8 and 9, Walkthrough B, Walkthrough A step 6)
- Visual review: Completed
- Visual verdict: PASS
- Screenshots: ![06](docs/reviews/4415/06-gm-two-proposals.png) ![07](docs/reviews/4415/07-guards-leave.png) ![07c](docs/reviews/4415/07c-toll-takers-proposed-gm.png) ![07c2](docs/reviews/4415/07c2-toll-takers-box.png) ![07d](docs/reviews/4415/07d-toll-takers-player.png) ![08](docs/reviews/4415/08-builder-cause-effect.png) ![09](docs/reviews/4415/09-config-preview.png) ![10](docs/reviews/4415/10-config-preview-after-save.png)
- Comparison notes: In scope: the demo's "Five causes, five shapes" table, Admin A's Cause effect select and help, Admin E (Causes fieldset, help texts, Preview rail), and the scenarios "The Greyrush quay" and "A Calm hold lapses later". The first review pass asked for live evidence of the unpaid group's GM prompt; the evidence run added it and found a defect (a second lapsing member restated the proposal without the "A hold on them ended" prefix), fixed in 2cfcc9952 with a two-member test; every file is from the final run on 232e03774 (2cfcc9952 plus a docs-only commit). Stated divergences accepted: the Builder's Cause help explains all five causes; the config page carries stock admin breadcrumbs and also groups the Force and Terms and regard fields the demo left out. Out of scope: the Greyrush terms, society rule and deed angle (authored content on earlier-slice surfaces); "the cause remains for the next scene" (no surface in this slice).
- Tested interactions: signed in through the real login form as the GM, two players, an onlooker and staff; the GM shook the Hatred group twice from the panel and held its prompt on telnet; the players read groups on telnet and the web card (three party actions); every seat read the scene feed; the GM read `standoff` and `gm prompts` on telnet; the holds on two settled groups lapsed through the scheduler's sweep; staff changed a faction rule's Cause effect on the Standoff Profile Builder and saved the config page, reloading each
- Fixture/live boundary: everything reached the live backend; the scripted part was the seed (accounts, characters, scene, encounter, five groups with their templates, faction rule, Calm holds and config), and nothing was mocked
- Overall outcome: PASS

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Five causes: Hunger fires on the force test, margin widening each unfed action | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c-toll-takers-proposed-gm.png) ![1](docs/reviews/4415/06-gm-two-proposals.png) ![2](docs/reviews/4415/10-config-preview-after-save.png) telnet-gm.txt margin 0% to 10% to 30%; shot 06/07c "Hunger fires: ... widened by hunger to 30%", force party 10 vs 8 |
| Hatred fires on a matching provoke rule whatever the force; ends by breaking morale | As drawn in the demo | MATCH | ![0](docs/reviews/4415/06-gm-two-proposals.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) telnet-gm.txt Hatred prompt with party 10 vs them 1.6; shot 06 Grudge-bearers "Broken", "Hatred holds: will not attack first" |
| Territory fires after set actions; warns one earlier | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c-toll-takers-proposed-gm.png) ![1](docs/reviews/4415/06-gm-two-proposals.png) feed "The Den hounds are losing patience."; "Patience: 3 of 3 actions."; proposal "They waited 3 actions"; shot 06/07c |
| Orders (existing) still holds, satisfied by terms | As drawn in the demo | MATCH | ![0](docs/reviews/4415/06-gm-two-proposals.png) shot 06 Paid guards settled, "Orders holds: will not attack first" |
| Admin A "Cause effect:" select None/Suppress/Provoke | As drawn in the demo | MATCH | ![0](docs/reviews/4415/08-builder-cause-effect.png) shot 08 "Cause effect: Provoke" |
| Admin A help "None, Suppress (they will not start it against this character) or Provoke (they will, whatever the force)." | As drawn in the demo | MATCH | ![0](docs/reviews/4415/08-builder-cause-effect.png) shot 08 same text |
| Admin A Cause help | As drawn in the demo | MATCH | Stated divergence, accepted: five causes need five glosses. ![0](docs/reviews/4415/08-builder-cause-effect.png) shot 08 extends the Orders gloss to Predation, Orders, Hunger, Hatred, Territory |
| Admin E title and breadcrumb | As drawn in the demo | MATCH | Stated divergence, accepted: framework text. ![0](docs/reviews/4415/09-config-preview.png) shot 09: title "Change standoff config"; stock crumbs add "Arx II" and subtitle "Standoff settings" |
| Admin E "Checks and holds" | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) shot 09 read, terms, pass, turn conditions |
| Admin E "Causes": Hunger margin step + help | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) shot 09 "Hunger margin step: 10", "Percent added to a Hunger group's margin for each action nobody feeds them." |
| Admin E Territory patience + help | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) shot 09 "Territory patience: 3", "Actions a Territory group allows before it fires. They warn one action earlier." |
| Admin E Botch force bands | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) shot 09 in Causes |
| Admin E Save / Save and continue editing | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) shot 09 |
| Preview line 1 "A Hunger group with margin 0: needs the party to outweigh it now; after 3 unfed actions, by 30 percent." | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) shot 09 identical; shot 10 after save "by 45 percent" |
| Preview line 2 "A Territory group: warns after action 2, fires after action 3." | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) shot 09 identical; shot 10 "warns after action 3, fires after action 4" |
| Preview line 3 "Listed on Game Tuning as Required content." | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) shots 09, 10 |
| Rail in a right-hand column beside the form | As drawn in the demo | MATCH | ![0](docs/reviews/4415/09-config-preview.png) ![1](docs/reviews/4415/10-config-preview-after-save.png) shot 09, 10 |
| Greyrush quay: hunger crowd, margin widening each action | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c-toll-takers-proposed-gm.png) ![1](docs/reviews/4415/06-gm-two-proposals.png) shots 06, 07c Quay crowd |
| Greyrush: GM morale control (shake) | As drawn in the demo | MATCH | ![0](docs/reviews/4415/06-gm-two-proposals.png) shot 06 Shake/Steady per group, "one morale step, reason required" (slice 3 control) |
| Calm hold lapses: cause re-tested on release | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07-guards-leave.png) feed "The Calm on Paid guard 1 has run out." then "Paid guard 1 leaves."; shot 07 (GM tab) |
| Paid-off sellsword leaves | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c-toll-takers-proposed-gm.png) ![1](docs/reviews/4415/07-guards-leave.png) shot 07/07b room lines "Paid guard 1/2 leaves."; shot 07c Paid guards "x0 settled" |
| Unpaid one brings a GM prompt in a story | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c2-toll-takers-box.png) ![1](docs/reviews/4415/07c-toll-takers-proposed-gm.png) shots 07c, 07c2: Toll-takers (x2) "proposed", "Predation fires: The party does not outweigh them by their margin.", "The cause fires: A hold on them ended and their cause still holds: The party does not outweigh them by their margin. Decide it in the GM prompts."; telnet-gm.txt `[4] Standoff: Toll-takers (test) ... Reason: A hold on them ended and their cause still holds: ...` with one prompt, no fight |
| Prompt card Confirm: they attack / Hold for one action / Override with required reason | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07c-toll-takers-proposed-gm.png) shot 07c prompts for Toll-takers, Den hounds, Quay crowd |
| Player sees the group as deciding, without the proposal | As drawn in the demo | MATCH | ![0](docs/reviews/4415/07d-toll-takers-player.png) shot 07d Toll-takers "deciding" with face-down tiles; no reason text shown |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| S4-hunger | PASS | 06, 07c; telnet-gm.txt margin 0/10/30%; test_remaining_causes.HungerTests | |
| S4-hatred | PASS | 06; telnet-gm.txt; HatredTests, CauseEffectTests | |
| S4-territory | PASS | 06; scene-feed-interactions.txt losing-patience line; TerritoryTests | |
| S4-cause-effect | PASS | 08, 08b; migrations 0243-0245 against a production copy with seeded old-shape rows | ADR-4415-A |
| S4-broken-hold | PASS | 07, 07b, 07c, 07c2, 07d; ReleaseTests | ADR-4415-A |
| S4-config-preview | PASS | 09, 10; test_standoff_config_admin | |

## Unresolved findings

- None
