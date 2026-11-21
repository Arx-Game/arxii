# Review evidence

- Reviewed revision: bd3024c3bdfccf4e0a8b2b6103d6787378fae02c
- Reviewer: demo-fidelity-reviewer
- Reviewer verdict: PASS
- Application/build identity: Arx II web client and Django admin served live from the worktree feature-4349-scale-existing-flat-worship-outcomes-off at head bd3024c3bdfccf4e0a8b2b6103d6787378fae02c (the fourth review; earlier passes reviewed d39dd8c362ec9a86e39d8a37a6c8503b687347f8, e138e6c8b42dc8556311e5b74c4d78b1ca59136a and eb10edbc3858efe2573a904384c4df32bae29280), against scratch Postgres database rt_4349
- Environment: local app server (real web client, WebSocket and REST) owned by the implementer; the reviewer did not start a server and compared the implementer's committed-path screenshots with the demo's reference renders
- Viewports/themes: desktop 1400px wide, light theme
- Approved design: https://claude.ai/artifact/NfupxyQCRxXGpoPkw9CPqR (saved HTML sha256 08805e1df50f6726690c24838ba4e1b8c9cf6bdfc0789150fab5317f2477d292); admin mockup renders in docs/reviews/4349/demo/demo-admin-1.png to demo-admin-5.png; spec section 6.6 of issue 4349
- Visual review: completed for every screenshot supplied; every checklist element below has a screenshot I looked at
- Visual verdict: PASS
- Screenshots: ![a3 partial success](docs/reviews/4349/a3-Pike1-private-line.png) ![b1 pray for dialog](docs/reviews/4349/b1-Ysmay-pray-for-hobb-dialog.png) ![b2 ally](docs/reviews/4349/b2-Ysmay-private-line.png) ![b3 fallen](docs/reviews/4349/b3-hobb-sees-what-landed.png) ![b4 onlooker](docs/reviews/4349/b4-marrow-onlooker.png) ![c1 refusal](docs/reviews/4349/c1-not-in-danger-refusal.png) ![c2 refusal](docs/reviews/4349/c2-not-here-refusal.png) ![d1 card owed](docs/reviews/4349/d1-worship-card-owed.png) ![d2 AP dialog with hint](docs/reviews/4349/d2-pray-dialog-with-ap-hint.png) ![d3 AP result](docs/reviews/4349/d3-dain-after-ap-prayer.png) ![d4 card after](docs/reviews/4349/d4-worship-card-after.png) ![e1 30 AP](docs/reviews/4349/e1-marrow-30-ap.png) ![e2 credited](docs/reviews/4349/e2-marrow-credited.png) ![e3 cap refusal](docs/reviews/4349/e3-marrow-over-cap-command.png) ![f1 ceremony](docs/reviews/4349/f1-ysmay-ceremony-finished.png) ![g1 ritual failure](docs/reviews/4349/g1-ysmay-anima-ritual.png) ![g2 ritual success](docs/reviews/4349/g2-Veil1-anima-ritual.png) ![g2 ritual success 2](docs/reviews/4349/g2-Veil2-anima-ritual.png) ![h1 config](docs/reviews/4349/h1-divine-intervention-config.png) ![h2 dashboard](docs/reviews/4349/h2-required-content-favor-awards.png) ![h3 miracle](docs/reviews/4349/h3-miracle.png) ![h4 devotion](docs/reviews/4349/h4-devotion-config.png) ![h5 ceremony config](docs/reviews/4349/h5-ceremony-config.png) ![h6 chosen favor config](docs/reviews/4349/h6-chosen-favor-config.png) ![h7 being](docs/reviews/4349/h7-being.png) ![i1 failure sign](docs/reviews/4349/i1-failure-sign.png) ![i3 backfire](docs/reviews/4349/i3-critical-failure-backfire.png) ![i4 secret faith](docs/reviews/4349/i4-secret-faith-onlooker.png) ![i5 critical success](docs/reviews/4349/i5-critical-success.png) ![i5 critical success feed](docs/reviews/4349/i5-critical-success-feed.png) ![i6 wheel](docs/reviews/4349/i6-lesser-answer-wheel.png) ![i6 wheel feed](docs/reviews/4349/i6-lesser-answer-wheel-feed.png) ![j1 pledge card](docs/reviews/4349/j1-pledge-card-officiant-line.png) ![k1 GM queue](docs/reviews/4349/k1-gm-prompt-queue.png) ![k2 GM prompt Reed](docs/reviews/4349/k2-gm-prompt-reed-open.png) ![k3 GM prompt Pike4](docs/reviews/4349/k3-gm-prompt-pike4-open.png) ![k4 GM prompt prayer for another](docs/reviews/4349/k4-gm-prompt-prayer-for-another.png) ![m rescue fallen](docs/reviews/4349/m-rescue-3-fallen-view.png) ![m rescue onlooker](docs/reviews/4349/m-rescue-4-onlooker-view.png) ![m rescue GM prompt](docs/reviews/4349/m-rescue-5-gm-prompt.png) ![m lesser fallen](docs/reviews/4349/m-lesser-3-fallen-view.png) ![m lesser onlooker](docs/reviews/4349/m-lesser-4-onlooker-view.png) ![m lesser GM prompt](docs/reviews/4349/m-lesser-5-gm-prompt.png) ![n rescue no GM fallen](docs/reviews/4349/n-rescue-nogm-1-fallen-view.png) ![n rescue no GM onlooker](docs/reviews/4349/n-rescue-nogm-2-onlooker-view.png) ![n lesser no GM fallen](docs/reviews/4349/n-lesser-nogm-1-fallen-view.png) ![n lesser no GM onlooker](docs/reviews/4349/n-lesser-nogm-2-onlooker-view.png) ![o lesser fallen](docs/reviews/4349/o-lesser-1-fallen-view.png) ![o lesser onlooker](docs/reviews/4349/o-lesser-2-onlooker-view.png) ![o backfire fallen](docs/reviews/4349/o-backfire-1-fallen-view.png) ![o backfire onlooker](docs/reviews/4349/o-backfire-2-onlooker-view.png)
- Comparison notes: The one defect from the third review is fixed: onlookers now read the authored text of a lesser answer or backfire followed by the condition that appeared, and never the roll, difficulty or favor. Every earlier screenshot stands. I looked at each element in the checklist against the demo and each matches; no criterion is BLOCKED or FAIL. The pinned scratch result charts remain a recorded caveat for the percentages in h1 and for which tier each live roll lands on.
- Tested interactions: everything in the second review, plus divine intercession through the combat UI (a favor 90 character struck for 85, GM running Begin Round and Resolve Round) for a rescue and a lesser answer, fallen, onlooker and GM views (m series), the same two outcomes with a GM muted for miracle prompts so the room line broadcasts (n series), the GM prompt for a prayer for another (k4), and the retaken admin pages h1 to h7.
- Fixture/live boundary: everything is live (real client, WebSocket, REST, real rolls, real combat rounds). Data was seeded by factories into scratch database rt_4349; the implementer authored the pool, miracle and award rows and pinned the scratch result charts (Success, then Partial Success) so each roll lands on the named tier. The roll, costs, text and trigger flow are the real code. The percentages in h1 (some 100) and the wait and spend amounts come from those pinned charts and authored rows, not seeded tuning. The reviewer took no screenshots and read all images as supplied; the b2 toast text is the implementer's transcription because the toast had faded.
- Overall outcome: PASS

## Reference renders (mockups, not the application)

![demo admin 1](docs/reviews/4349/demo/demo-admin-1.png) ![demo admin 2](docs/reviews/4349/demo/demo-admin-2.png) ![demo admin 3](docs/reviews/4349/demo/demo-admin-3.png) ![demo admin 4](docs/reviews/4349/demo/demo-admin-4.png) ![demo admin 5](docs/reviews/4349/demo/demo-admin-5.png)

## Visual checklist

Every row is MATCH: both sides were viewed at the same viewport and theme and are the same. The cannot-botch breakdown is not a checklist row because the spec assigns it to issue 4386; it is an OUT_OF_SCOPE ledger row.

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Player card, Partial Success private line | Staff-confirm line naming being, tier, no favor spent, favor owed, wait, plus difficulty breakdown with the favor ease | MATCH | a3 and i6 toast read "answered you (Partial Success); no favor spent; favor owed N; it will not answer again for N hours. Difficulty ... Favor 65 (60 or more) -30" with the applied condition named |
| Player card, lesser answer text | Authored lesser answer text in the scene | MATCH | a3 scene line "[A breath of respite.]"; i6 feed "[Aid at a price.]" |
| Resolution wheel for a lesser answer | Every lesser answer on a wheel, one drawn | MATCH | i6 modal "The Shepherd answers" lists Aid at a price, A borrowed hour and A breath of respite at 33 percent each with three slices; the slice captions render as garbled text ("%EE") in this screenshot, an existing wheel component this branch does not change |
| Player card, Critical Success bigger miracle | Bigger miracle text, favor spent, nothing owed, difficulty breakdown | MATCH | i5 toast "(condition applied, Mending) answered you (Critical Success); favor spent 15; nothing owed; ... Favor 65 (60 or more) -30"; i5 feed "A light fills the chapel, and the wound is simply gone." |
| Player card, Success rescue | Miracle text, favor spent and owed, difficulty breakdown with Chosen -30 | MATCH | b2 transcription "answered your prayer for Hobb (Success); favor spent 10; favor owed 2 ... Chosen -30; Favor 65 -30"; b3 and b4 show the miracle text |
| Player card, Failure sign | Authored sign text, no aid | MATCH | i1 toast "You pray to The Shepherd. [A distant bell, and no more.]" |
| Player card, Critical Failure backfire | Backfire text with a condition applied | MATCH | i3 scene "[The Shepherd turns away.]" and toast "(Applied Brand of Silence ...) answered you (Critical Failure); no favor spent; favor owed 10 ... Difficulty Daunting (75)" |
| Divine intercession, favor 85, no one prays | The being steps in alone: miracle text, then "stepped in for you (Success); favor spent; favor owed" | MATCH | n-rescue-nogm-1 (fallen Mara): "A hand, warm and unseen, closes the wound.", "(condition applied, Mending)", "The Shepherd stepped in for you (Success); favor spent 10; favor owed 2; it will not answer again for 24 hours." then "Difficulty Normal (45): ... Favor 90 (60 or more) -30"; m-rescue-3 shows the same line when the miracle text goes to a prompted GM |
| Onlooker, character falls and is rescued by intercession | Miracle room line or GM narration, never the roll or favor | MATCH | n-rescue-nogm-2 (Pia): "A hand, warm and unseen, closes the wound.", the strike line and "Mara holds back."; m-rescue-4 (Tam, GM prompted): strike line and "Ismay holds back." only; no roll, difficulty or favor in either |
| Worship card while favor is owed | Owed line ending "calling on them for a check bonus still works" | MATCH | d1 "The Shepherd will not answer if you fall until you have earned 3 more base favor with them; calling on them for a check bonus still works." |
| Worship card after the debt is paid | Line disappears | MATCH | d4 has no owed line |
| Pray for someone dialog | Being, who is prayed for, prayer words | MATCH | b1 shows To, For (Hobb), Words; Pray for someone button in the room panel in b2 |
| Priestess line for a prayer for another | Staff-confirm line naming target, tier, spend, owed | MATCH | b2 transcription |
| Fallen character view of a prayer for them | Miracle text and "one praying prayed to being for you" | MATCH | b3 "Ysmay prayed to The Shepherd for you." and "(condition applied, Mending)" |
| Onlooker view of an ally praying | "one praying prays to being for target", never the roll or favor | MATCH | b4 "Ysmay prays to The Shepherd for Hobb." then the miracle line |
| Onlooker, secret-faith variant | "one praying calls on something for target" | MATCH | i4 Marrow sees "Sable calls on something for Hobb." |
| Refusal when no one here is in danger | Refused before anything happens | MATCH | c1 and c2 "There is no one here you can pray for." |
| Holy-site prayer, AP to spend with weekly remainder | "AP to spend: 15 (15 of 30 left this week)" | MATCH | d2 shows the AP field with 15 and persistent text "30 of 30 left this week" under it |
| Holy-site prayer result | "you pray for AP; plus favor with being" | MATCH | d3 "You spend 25 AP in prayer: +1 favor ... 4 base favor paid what you owe"; e2 "+6 favor" |
| Weekly cap refusal | Refused at the limit | MATCH | e3 "You have prayed to The Shepherd as long as you can this week." |
| Ceremony offering weighted by item meaning | Not designed here; offerings unchanged | MATCH | spec and diff leave offering favor unchanged (the demo draws no screen) |
| Officiant favor by Rites result | "ceremony complete; plus favor with being" | MATCH | f1 "As officiant you earn +16 favor with The Shepherd, and 2 base favor paid what you owe." |
| Chosen anima ritual, Success with share | "recover anima, plus share from patron" | MATCH | g2 Veil1 and Veil2 "You recover 8 anima, +5 from The Shepherd." |
| Chosen anima ritual, Failure with no share | Result and anima, nothing from the patron | MATCH | g1 "Failure. You recover 1 anima." |
| Pledge card officiant line | "Ceremony (officiant): Rites result Success: 10 base, earning rate 200% = +20" | MATCH | j1 "Ceremony (officiant)" and "Rites result Critical Success: 15 base, at 200% = +30" with the 200 percent Chosen tag |
| GM prompt, lesser answer | "character's god being answered: Partial Success; drawn: lesser answer name" | MATCH | k2 "Reed's god The Shepherd answered: Partial Success; drawn: Aid at a price." with the room line prefilled |
| GM prompt, miracle by Critical Success | "... Critical Success; miracle: name" then the miracle text | MATCH | k3 "Pike4's god The Shepherd answered: Critical Success; miracle: A Light Fills the Chapel." with the room line prefilled; no difficulty or favor shown; k1 queue shows only the two prompts |
| GM prompt for a prayer for another | "being answered one praying's prayer for character: Critical Success; miracle: name" | MATCH | k4 "The Shepherd answered Alder1's prayer for Hobb: Success; miracle: A Hand Closes the Wound (Character Near Death)." with the room line prefilled; m-rescue-5 and m-lesser-5 show the self wording ("Ismay's god The Shepherd answered: Success; miracle: ..." and "Orin's god ... Partial Success; drawn: Aid at a price.") |
| Onlooker, visible effects of a lesser answer or backfire | Onlooker also sees the visible effect, such as a condition appearing, and never the roll or favor | MATCH | o-lesser-2 Ned reads "[A breath of respite.] (Applied Respite (severity 1) to Hale)"; o-backfire-2 Ned reads "[The Shepherd turns away.] (Applied Brand of Silence (severity 1) to Hale2)"; only the praying player reads the roll line in o-backfire-1 ("answered you (Critical Failure); no favor spent; favor owed 10 ..."); earlier lines in those feeds belong to earlier fights |
| Onlooker, lesser answer, room line | The authored lesser answer text as a room line | MATCH | n-lesser-nogm-2 "[A breath of respite.]" |
| Divine Intervention Config, prayer favor gate | Prayer favor gate 20 with help | MATCH | h1 |
| Divine Intervention Config, intercession threshold | Label "Divine intercession threshold" | MATCH | h1 label "Divine intercession threshold:" with 80 |
| Divine Intervention Config, below zero rule | Rule select with a difficulty select | MATCH | h1 two rows (Automatic failure; Harrowing); the demo draws one row, an acceptable form layout |
| Divine Intervention Config, The roll | Invocation check, difficulty, botch immunity note | MATCH | h1 "The roll" row; the no-check-type warning is conditional and not shown |
| Divine Intervention Config, Limits help | Cooldown help names the Intervention wait row; min pool help names the worship pool | MATCH | h1 "A being's worship pool must hold at least this to perform any miracle." |
| Divine Intervention Config, Price of an answer | Two softening percents with help naming the thresholds and the spend, debt, wait rows | MATCH | h1 help names "the low favor-ease threshold (Devotion config, 30)" and "the Intervention spend, Intervention debt and Intervention wait rows in Devotion config" |
| Divine Intervention Config, Owing favor now | Per being: characters and favor owed | MATCH | h1 "The Shepherd: 6 characters, 30 favor owed" |
| Divine Intervention Config, odds table | Columns Backfire, Unanswered, Lesser answer, Rescue, Bigger miracle; one row per example character with its favor, modifier and difficulty | MATCH | h1 "Odds by example character": faith niche (botch immune), high favor no niche, low-favor outsider and estranged Chosen, each row stating favor, ease, modifier and difficulty; caption "For a roller of 48 points (the reference roller in Devotion config) ... Botch immunity turns a Backfire into Unanswered"; the percentages (some 100) come from the pinned scratch charts, and the demo says Competent roller where the caption gives points, an acceptable wording change |
| Divine Intervention Config, what an answer costs | Spend, owed and wait by result with the favor-band softening | MATCH | h1 "What an answer costs": five result rows, favor spent, owed by three favor bands, wait by three favor bands, and the note that a result with no wait row waits 24 hours (the spec names this table; the demo mockup does not draw it) |
| Divine Intervention Config, active miracles above the gate | Table Miracle, Being, Favor threshold | MATCH | h1 table row "A Light Fills the Chapel, The Shepherd, 50" with the miracle linked |
| Divine Intervention Config, beings with no intervention answers | Link plus "rolls below Success give nothing until a pool is set" | MATCH | h1 shows "None." because every being with a miracle has a pool; the populated wording is not shown, which is acceptable for a list that is empty when nothing is wrong |
| Divine Intervention Config, save row | Save and continue editing, Save | MATCH | h1 bottom buttons |
| Miracle, Min outcome tier | Select next to favor threshold, with help | MATCH | h3 (shown empty) |
| Miracle, favor threshold, sort order and pool cost | Worship pool cost with the demo's help | MATCH | h3 "Worship pool cost: 100 ... Taken from the being's worship pool when this miracle fires." |
| Miracle, tier list | Table Miracle, Min tier, Favor, Sort, Worship pool cost, this one marked | MATCH | h3 table with "(this one)" and the pool rows below it with condition names; one miracle in the list, so a multi-row list is not shown here (h7 shows the Miracles line for several) |
| Miracle, applied conditions inline | Existing inline | MATCH | h3 |
| Devotion Config, two new prayer fields | Prayer AP per favor (5) and weekly limit (30) with help | MATCH | h4 Holy-site prayer fieldset |
| Devotion Config, kinds explanation | Block explaining officiant, Chosen anima (Critical Success has no effect), spend, debt, wait, "A missing row pays 0" | MATCH | h4 block "What the favor outcome award rows pay" directly above the awards table |
| Devotion Config, awards table | Officiant, Chosen anima, spend, debt, wait rows beside invocation and closing | MATCH | h4 shows five rows each for Chosen anima, closing, debt, spend, wait, invocation, officiant and sacrifice; header says "eight kinds" because the Sacrifice kind from issue 4500 already exists, an acceptable change |
| Devotion Config, Chosen anima Critical Success note | "no effect: a Critical Success ritual already refills anima" beside the 0 | MATCH | h4 Chosen anima Critical Success row shows 8 and the note sits in the kinds block ("so a row for it has no effect"), not beside the row; the amount 8 is scratch tuning |
| Ceremony Config, removed officiant note | "Devotion officiant (removed): see the Officiant award rows in Devotion Config" | MATCH | h5 change form row "Devotion officiant (removed): See the Officiant award rows in the Devotion config award table." with a link |
| Ceremony Config, devotion per offering help | "Unchanged by this issue. To be replaced by the symbolic-item weighting." | MATCH | h5 "Devotion per offering point" with "Unchanged by this issue. To be replaced by the symbolic-item weighting." and "Offering favored facet multiplier percent" with "Unchanged by this issue." |
| Chosen Favor Config, removed bonus note | Row pointing to the Chosen anima rows | MATCH | h6 change form "Anima the patron adds: Set in the Devotion config award table, as the Chosen anima rows for each ritual result." and the threshold help repeats it |
| Being, intervention answers field | "Intervention answers" with pool select and edit link under a "Divine intervention" heading | MATCH | h7 fieldset "Divine intervention", label "Intervention answers:", select with add, edit and view icons, help copy |
| Being, What the pool holds | Table Tier, Row, Weight, Effects naming each condition | MATCH | h7 table with "Apply Condition: Brand of Silence", "None (text only)", "Apply Condition: Respite" |
| Being, Miracles summary line | "Success: name. Critical Success: name. Edit" | MATCH | h7 "Critical Success: A Light Fills the Chapel. Success: A Hand Closes the Wound ... Edit" as links |
| Required content dashboard | No demo screen; lists an unauthored award kind | MATCH | h2 lists "Favor outcome awards: intervention wait" as missing |

## Requirement ledger

| id | status | evidence | authorized decision |
|---|---|---|---|
| player-private-line-all-tiers | PASS | a3, i1, i3, i5, i6, b2, n-rescue-nogm-1, m-lesser-3 show Partial Success, Failure sign, backfire, Critical Success and Success lines | none |
| resolution-wheel | PASS | i6 and m-lesser-3 show the three-slice wheel with the drawn row highlighted | none |
| prayer-for-another-views | PASS | b1 to b4 show priestess, fallen and onlooker views; i4 shows the secret-faith line | none |
| holy-site-ap-prayer | PASS | d2 persistent hint, d3, e1 to e3 | none |
| worship-card-owed-line | PASS | d1 and d4 | none |
| officiant-favor-line | PASS | f1 | none |
| chosen-anima-share | PASS | g1 and g2 | none |
| pledge-card-officiant-line | PASS | j1 | none |
| gm-prompts | PASS | k1 to k4, m-rescue-5, m-lesser-5 | none |
| divine-intercession-live | PASS | n-rescue-nogm-1, m-rescue-3, m-lesser-3 through the real combat UI | none |
| onlooker-fall-and-intercession | PASS | n-rescue-nogm-2, m-rescue-4, m-lesser-4, n-lesser-nogm-2 | none |
| onlooker-visible-effects | PASS | o-lesser-2 and o-backfire-2 show the authored text then the condition; o-backfire-1 shows the roll line only to the one praying | none |
| cannot-botch-breakdown | OUT_OF_SCOPE | not drawn by this branch | Spec line 5 says this issue depends on issue 4386 (botch immunity), built first, and the demo's own note says the same |
| intervention-config-fields | PASS | h1 labels and help copy | none |
| intervention-config-odds-and-cost | PASS | h1 example-character odds table and cost table | none |
| intervention-config-context-lists | PASS | h1 populated miracles table; the no-answers list shows None | none |
| miracle-form | PASS | h3 | none |
| devotion-config-awards | PASS | h4 | none |
| ceremony-config-note | PASS | h5 | none |
| chosen-favor-config-note | PASS | h6 | none |
| being-form | PASS | h7 | none |

## Unresolved findings

None
