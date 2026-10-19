# Review evidence: #4418 demo fidelity (GMs and Guides play major NPCs), final review

- Reviewed revision: `51a2549241332a5c0ffd1d35cc0d9b223eabc063`
- Reviewer: demo-fidelity-reviewer (Claude Opus 5.5, vision-capable; compared each rendered screenshot with the demo screen rendered at the same viewport and theme)
- Reviewer verdict: PASS
- Application/build identity: branch `feature-4418-play-major-npcs-in-scenes-gms-and-guides` at `e4dce94a1`, frontend built with `just fe-build` by the real-testing pass. The commit each screenshot was taken at, and whether later commits touched that surface, is in "Screenshot provenance" below.
- Environment: devcontainer, Playwright Chromium, throwaway database `rt_4418` (`tools/build_schema.py` plus seed clusters; round 7 added `OpponentTierTemplate`, damage multipliers, threat pools and a combat-ready PC in a shell), dropped after each round. I did not start a server; I judged from the real-testing screenshots.
- Viewports/themes: application 1400x1000 light theme (form shots cropped to the component at 814px, cast panel at its real 360px side-column width). Demo reference rendered with Playwright at 1400x1000, `colorScheme: light`.
- Approved design: https://claude.ai/artifact/FkUJngYFbp1hF2nvNvTYQX (demo version 2); reference renders under `.github/issue-evidence/4418/demo-reference/`.
- Visual review: completed for Screens 1a, 1b, 1c, 2, 3, 4 and the staff admin screen.
- Visual verdict: PASS
> Revision note (controller): the review ran at e4dce94a1. The branch was then rebased onto origin/main (main's magical-skills and #4454 work); the only change to code this review covers is one line in world/scenes/action_services.py (`.extra_modifiers_total` instead of `.total` on the NPC-initiator resist roll, per #4454), plus the lint and reviewer-agent commits 5c57a7c0d and the aftermath test update. No surface in the screenshots changed.

- Screenshots: Demo ![1a](.github/issue-evidence/4418/demo-reference/screen-1a.png) ![1b](.github/issue-evidence/4418/demo-reference/screen-1b.png) ![1c](.github/issue-evidence/4418/demo-reference/screen-1c.png) ![2](.github/issue-evidence/4418/demo-reference/screen-2.png) ![3](.github/issue-evidence/4418/demo-reference/screen-3.png) ![4](.github/issue-evidence/4418/demo-reference/screen-4.png) ![admin](.github/issue-evidence/4418/demo-reference/screen-admin.png); Build ![1a](.github/issue-evidence/4418/1a-npc-form-quick.png) ![1b](.github/issue-evidence/4418/1b-npc-form-detailed.png) ![1c](.github/issue-evidence/4418/1c-npc-roster.png) ![1c borrower](.github/issue-evidence/4418/1c-borrower-plays-vael.png) ![1d](.github/issue-evidence/4418/1d-owner-manage-panel.png) ![2 lent](.github/issue-evidence/4418/2-cast-panel-lent.png) ![2 crowds](.github/issue-evidence/4418/2-cast-panel-crowds.png) ![3a](.github/issue-evidence/4418/3a-guide-offer-card.png) ![3b](.github/issue-evidence/4418/3b-guide-npc-tab-notes-response.png) ![3d](.github/issue-evidence/4418/3d-guide-crowd-tab.png) ![4a](.github/issue-evidence/4418/4a-player-resist-card.png) ![4c](.github/issue-evidence/4418/4c-player-romance-card.png) ![4d](.github/issue-evidence/4418/4d-pc-kills-npc.png) ![admin add](.github/issue-evidence/4418/admin-grant-guide.png) ![admin change](.github/issue-evidence/4418/admin-guide-profile.png)
- Comparison notes: the build uses the app's own tokens, not the demo's parchment mock palette; not reported. Every earlier finding (F1 to F9, E1 to E3, M1) is resolved on screen. Avatars are initials fallbacks because no portrait was uploaded (Cloudinary). Reaction glyphs draw as a missing-glyph box in headless Chromium in both demo and build (a font issue, not code). Things visible in the shots but outside the demo comparison are under "Notes outside the demo comparison".
- Tested interactions: none by me. Real-testing rounds 4 to 7 drove the UI and the endpoints it calls. They created Quick and Detailed NPCs (with powers and preferences), requested and approved a borrow, offered, accepted and declined from an NPC tab, and took an NPC back. They also posed as an NPC and a crowd, persuaded an NPC and replied through the response card, ran a resist-only deceive and a romance consent, fought a played NPC as an elite opponent to defeat, and added and changed a Guide in admin.
- Fixture/live boundary: live server and real browser on a seeded throwaway database. No paths, gifts or techniques in the seed (ruled a content gap). Opponent tiers, damage multipliers and threat pools were made in a shell before start; the encounter, mooks and swarm were added through the GM's real dispatch path, and Mira was stood as an opponent by staff.
- Overall outcome: PASS

## Maintainer and controller rulings applied (not failed)

- No Title field and no Languages field on the NPC form (1b).
- "Believe {name}" and the generic heading "{initiator} acts against you. Resist?" (4).
- "+ Add crowd" omitted from the cast panel; adding opponents lives in encounter controls (2).
- No tutorial text.
- The owner Manage panel (`1d-owner-manage-panel.png`) is an addition.
- Age and height use the sheet's real fields ("Born (IC year)", "Height (inches)") (1b).
- The resist card stays in the consent banner above the feed (4).
- Copy from has no preview of the copied text (1b).
- An empty Path list in the seed is a content gap (1b).
- No consequence line on the response card: the spec reuses the resolved-action notification (3).
- The tab dot is the existing attention badge, not an unread count (3).
- A played NPC defeated in a fight is not killed: encounter defeat never kills a persona-backed opponent. This is behaviour from main, outside this issue, and has been raised to the maintainer (4; ledger row `screen-4-kill`).

## Screenshot provenance

| File | Taken at | Later commits touching what it shows |
|---|---|---|
| `1b-npc-form-detailed.png` | round 7, `c9b0a2483` | none for `NpcForm.tsx`, `NpcPowersEditor.tsx` |
| `1a-npc-form-quick.png` | round 6, `9cb5c729b` | none for `NpcForm.tsx` since `5946204a3` |
| `1c-npc-roster.png`, `1c-borrower-plays-vael.png`, `1d-owner-manage-panel.png` | round 5, `b9c745f76` | none for `NpcRosterPage.tsx`, `GameTopBar.tsx`, `NpcOwnerPanel.tsx` |
| `2-cast-panel-lent.png` | round 5, `b9c745f76` | none for `CastListPanel.tsx`; `0d565b9c7` changes only who sees the panel (`SceneDetailPage.tsx`, staff and GMs), not how it draws |
| `2-cast-panel-crowds.png` | round 7, `c9b0a2483` | same as above |
| `3a-guide-offer-card.png` | round 2, `999ef9688` | none for `NpcOfferCard.tsx`; only the offer card is cited from this shot |
| `3b-guide-npc-tab-notes-response.png` | round 6, `9cb5c729b` | none for `GamePage.tsx`, `NpcResponseCard.tsx`, `GameTopBar.tsx` |
| `3d-guide-crowd-tab.png`, `4a-player-resist-card.png`, `4d-pc-kills-npc.png` | round 7, `c9b0a2483` | `71ac8138c` (aftermath text frame no longer sent to web sessions, backend) and `e4dce94a1` (aftermath grammar, backend); neither changes the cited elements |
| `4c-player-romance-card.png` | round 4, `5f0a8ab8d` | none for `ConsentPrompt.tsx` after `b807cf54c` |
| `admin-guide-profile.png` | round 4, `5f0a8ab8d` | none for `src/world/gm/admin.py` after `4271dda28` |
| `admin-grant-guide.png` | round 6, `9cb5c729b` | none |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| screen-1a | PASS | `1a-npc-form-quick.png` vs `demo-reference/screen-1a.png` | none |
| screen-1b | PASS | `1b-npc-form-detailed.png`: every section has controls; Powers with Path, Level, Tradition, title-cased stats, full skill names; preferences with notes | none |
| screen-1c | PASS | `1c-npc-roster.png`, `1c-borrower-plays-vael.png` | none |
| screen-2 | PASS | `2-cast-panel-lent.png` lent rows with role and Take back; `2-cast-panel-crowds.png` mook crowd and swarm rows, no toast | none |
| screen-3 | PASS | `3b-guide-npc-tab-notes-response.png`, `3d-guide-crowd-tab.png`, `3a-guide-offer-card.png` | none |
| screen-4 | PASS | `4a-player-resist-card.png` resist-only card; `4c-player-romance-card.png` protected ask; `4d-pc-kills-npc.png` attack resolves against the played NPC | none |
| screen-4-kill | OUT_OF_SCOPE | `4d-pc-kills-npc.png`: "Ysmay's Gate-breaker Strike strikes Sergeant Mira for 30 damage, defeating them"; sheet stays ALIVE | Controller ruling, raised to the maintainer: encounter defeat never kills a persona-backed opponent, behaviour from main outside #4418; `death_is_permitted` for the pair is True |
| screen-admin | PASS | `admin-grant-guide.png`, `admin-guide-profile.png` | none |

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| 1a: title and Quick/Detailed toggle | title left, toggle right, Quick selected | MATCH | `1a-npc-form-quick.png` |
| 1a: portrait slot | two initials beside Name | MATCH | `1a-npc-form-quick.png` "CV" |
| 1a: Name, Copy from | labelled input and select | MATCH | `1a-npc-form-quick.png` |
| 1a: description | multi-paragraph text area | MATCH | `1a-npc-form-quick.png` |
| 1a: section chips | Who they are, Background, Powers, Favors and opposes, What works on them, Notes, Owner and lending | MATCH | `1a-npc-form-quick.png` |
| 1a: primary button | Create and add to scene | MATCH | `1a-npc-form-quick.png` |
| 1a: header persona chip | GM persona chip in the site header | MATCH | `1d-owner-manage-panel.png` Ravenna chip above the GM dashboard holding the form |
| 1b: Start from | Copy an NPC or template, Stat block | MATCH | `1b-npc-form-detailed.png` (Guard) |
| 1b: Who they are | portrait plus identity grid (ruled fields) | MATCH | `1b-npc-form-detailed.png` |
| 1b: Description with Copy from | heading, Copy from, text area | MATCH | `1b-npc-form-detailed.png` (Copy from: Captain Vael) |
| 1b: Background and drives | Concept, Protects, Fears, Would never, Background | MATCH | `1b-npc-form-detailed.png` |
| 1b: Powers, magic | Gift and Techniques | MATCH | `1b-npc-form-detailed.png` Path, Level, Tradition; Gift and Techniques follow a tradition (`NpcPowersEditor.tsx`); empty lists are the ruled content gap |
| 1b: Powers, stat overrides | named stats with values | MATCH | `1b-npc-form-detailed.png` Agility, Charm, Intellect, Presence, Stamina, Strength, Willpower, Wits |
| 1b: Powers, skill overrides | full skill names with values | MATCH | `1b-npc-form-detailed.png` Melee Combat 2, Performance 2, Persuasion |
| 1b: Who they favor and oppose | favor/oppose, target, strength, reason | MATCH | `1b-npc-form-detailed.png` |
| 1b: What works on them | Easier/Harder rows with trait and note | MATCH | `1b-npc-form-detailed.png` Easier Proud with note, Harder Greedy with note, add row |
| 1b: Notes for whoever plays them | large text area | MATCH | `1b-npc-form-detailed.png` |
| 1b: Owner and lending | Owner, NPC roster, Who may play, Who may ask to borrow | MATCH | `1b-npc-form-detailed.png` |
| 1b: buttons | Create, Save as template | MATCH | `1b-npc-form-detailed.png` |
| 1c: title, search, filter | NPC roster, search, Lendable to me | MATCH | `1c-npc-roster.png` |
| 1c: cards | portrait, name, owner and lending line, excerpt | MATCH | `1c-npc-roster.png` CV, SM |
| 1c: Ask to borrow, Copy as a new NPC | both buttons | MATCH | `1c-npc-roster.png` |
| 1c: borrowed NPC tab | NPC tab beside own character, own character untagged | MATCH | `1c-borrower-plays-vael.png` |
| 2: header | "Cast, scene name", + Add NPC | MATCH | `2-cast-panel-crowds.png` |
| 2: NPC row | two-initial portrait, name, NPC tag, played-by | MATCH | `2-cast-panel-crowds.png` CV Captain Vael, Me |
| 2: offered state | Offered to the Guide | MATCH | `2-cast-panel-crowds.png` Sergeant Mira, Offered to Ilsa the Guide |
| 2: lent row with Take back | player and role, Take back | MATCH | `2-cast-panel-lent.png` "Corvin (GM)", "Ilsa the Guide (Guide)" |
| 2: mook crowd row | stacked portraits, name, count chip, played-by, Rename or describe, description | MATCH | `2-cast-panel-crowds.png` The Low Gate Watch, "3 · mooks" |
| 2: swarm row | stacked portraits, name, "swarm, N bodies", description, controls | MATCH | `2-cast-panel-crowds.png` Rioters, "swarm · 8 bodies", Add crowd voice, Rename or describe |
| 3: NPC tab | tagged NPC with its room | MATCH | `3b-guide-npc-tab-notes-response.png` |
| 3: crowd tab | tagged CROWD with its room | MATCH | `3d-guide-crowd-tab.png` CROWD, Low Gate, The Low Gate Watch |
| 3: own PC tab elsewhere | PC tab showing its own room | MATCH | `3b-guide-npc-tab-notes-response.png` Ilsa, The Lantern |
| 3: feed | each pose once, reactions | MATCH | `3b-guide-npc-tab-notes-response.png` |
| 3: action attachment | chip naming the action on the PC's pose | MATCH | `3b-guide-npc-tab-notes-response.png` |
| 3: response card | outcome title, excerpt, Pose as NPC | MATCH | `3b-guide-npc-tab-notes-response.png` |
| 3: notes card | Notes for whoever plays the NPC | MATCH | `3b-guide-npc-tab-notes-response.png` |
| 3: offer card | NPC offered by GM, notes, Accept, Decline | MATCH | `3a-guide-offer-card.png` |
| 3: posing as the crowd | composer and pose under the crowd's name | MATCH | `3d-guide-crowd-tab.png` |
| 4: resist card | heading, check line, effort, Roll, Believe name, no refusal | MATCH | `4a-player-resist-card.png` |
| 4: protected-category ask | refusable card, buttons inside the column | MATCH | `4c-player-romance-card.png` |
| 4: PC attack on a played NPC | attack resolves against the NPC in the feed | MATCH | `4d-pc-kills-npc.png` "...strikes Sergeant Mira for 30 damage, defeating them"; death itself ruled out of scope |
| 4: aftermath narration | narration line after the fight, once | MATCH | `4d-pc-kills-npc.png` "Aftermath: Victory." once on the scene page |
| admin: Who | Account, Granted by set on save, Active | MATCH | `admin-grant-guide.png`, `admin-guide-profile.png` |
| admin: Right now | Playing, For, Scene, Return to GM | MATCH | `admin-guide-profile.png` |
| admin: Last 30 days | hand-off counts | MATCH | `admin-guide-profile.png` |
| admin: save row | Save and add another, Save | MATCH | `admin-grant-guide.png` |

## Notes outside the demo comparison

- `4d-pc-kills-npc.png` was taken at `c9b0a2483`, before three later commits:
  - **"Could not load Guides." and the GM tools on a player's scene page.** These were round-7 bug J. `0d565b9c7` now shows the cast panel to staff and GMs only. No screenshot shows a player's scene page after it.
  - **"Ysmay stand victorious".** Fixed in `e4dce94a1`.
  - **The doubled "Aftermath: Victory." on `/game`.** This was bug K, also present on main. Fixed in `71ac8138c` with a journey test in `src/integration_tests/test_npc_lending_journeys.py`. No `/game` screenshot was taken after the fix.
- The combat narration "The field falls silent — victory." contains an em dash. It is combat copy from main and not in this diff.

## Unresolved findings

None
