# Review evidence: scene participation begins with the first pose, the threshold is marked and unaddressable, and the entrance is that pose (#3867)

Closes #3867.

- Reviewed revision: 5c244bb6d4d3657647be74f5a4644c568036d485
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below, plus a demo-fidelity review pass (a general-purpose Sonnet 5 subagent following `tools/agents/demo-fidelity-reviewer.md`, since the named agent is not registered in this session) that read the approved demo's HTML, the same screenshots, the server and client code and every named test; it returned PASS with no finding, noting one non-defect divergence recorded below.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at the reviewed revision (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as `playwright.config.ts` does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3867's spec (demo v1, https://claude.ai/code/artifact/3410b6a6-db7e-4e33-bbd6-b49fa85ccf13, built from Dan's design direction of 2026-09-14, which carries `spec:approved`). Five screens: the marked newcomers and the composer's Entrance state; the first pose; the refusal of a target at the threshold; leaving without posing; a newcomer's first pose clearing their mark.
- Visual review: completed on the two screenshots below, taken from the running application (not a mockup) by `frontend/e2e/feed-threshold.spec.ts`, compared against the demo's Here panel rows (`.thr` asterisk after the name, the `you` tag), its composer (`.state` "✨ Entrance" chip with the technique control beside it) and its cleared state after the first pose.
- Visual verdict: PASS
- Screenshots: ![Before the first pose: the Here panel lists "Tehom *" with the you tag and "Nyx *", and the composer's right slot shows the amber "✨ Entrance" state with the technique control beside it](https://raw.githubusercontent.com/Arx-Game/arxii/5c244bb6d4d3657647be74f5a4644c568036d485/docs/reviews/3867/threshold-1280.png) ![After Tehom's and Nyx's first poses: no asterisks in the Here panel and no Entrance state on the composer](https://raw.githubusercontent.com/Arx-Game/arxii/5c244bb6d4d3657647be74f5a4644c568036d485/docs/reviews/3867/threshold-entered-1280.png)
- Comparison notes: In `threshold-1280.png` the Here panel's Characters list reads "Tehom *" with the "you" tag at the row's end and "Nyx *" below, the asterisk in the muted weight the demo's `.thr` mark uses, with the title "Not yet in the scene" and no explainer text; the composer's right slot shows the amber "✨ Entrance" chip as a state (no pressed control, no "Make an entrance" button anywhere) with the entrance-technique control beside it, the demo's screen 1. In `threshold-entered-1280.png`, after the viewer's first pose and Nyx's, both asterisks are gone and the composer's right slot holds only the scene controls, the demo's screen 5. Screen 3 (the refusal of a target at the threshold) has no web affordance to reach: a target is added from a pose or a thread, which a threshold character has none of, so it is pinned by `tagReachability.test.ts` and by the server's own test, with the demo's wording byte for byte on both sides. Screen 4 (leaving without posing is the ordinary movement line) is unchanged behaviour the spec asks nothing of. Differences from the demo that are not defects: the demo draws the technique control as the text "+ technique" while the app renders the existing `EntranceTechniqueAttachment` trigger (#2183), which predates this issue; the headless font renders the star glyph as a box in the screenshot.
- Tested interactions: reach "In world" with an active scene through the shared harness; push a room_state with the viewer and Nyx both outside the scene and read two asterisks with their titles, the Entrance state and the technique trigger, and no "Make an entrance" button; type a pose and read it reaching the pose endpoint with `pose_kind: 'entry'`; push a room_state with the viewer entered and read the Entrance state and the technique trigger gone and one asterisk left; push a room_state with Nyx entered and read no asterisks. Zero page errors (asserted).
- Fixture/live boundary: REST and the game WebSocket are mocked through `frontend/e2e/support/gameHarness.ts` (the same fixture `narrative-play-delivery.spec.ts` uses), with the pose endpoint answered by the journey itself; no Django or Evennia process and no database took part, so the server side (participation off the log, the entrance marking and window, the reachability gate, the room_state fields) is covered by the Python tests named in the ledger rather than the journey. The panel, the composer, the mark, the store and the CSS are the real ones.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| participation-begins-with-the-first-pose | PASS | `test_participation.py` (pose, say, emit enter; whisper does not; other scenes do not) | spec Decision 1 |
| presence-and-participation-kept-separate | PASS | `participation.py` reads the log only; `SceneParticipation` untouched (`test_scene_admin_services` green); ADR-0300 | spec Decision 1 |
| threshold-marked-in-the-here-panel | PASS | `CharactersList.test.tsx` "marks a present character who has not entered the scene, and the viewer likewise"; `RoomStateThresholdTests` (`in_scene`, `viewer_entered`); `threshold-1280.png` | spec Decision 2 |
| threshold-sees-everything | PASS | no read-visibility surface changed (`visible_to` untouched; `test_reachability.py::TestAgreesWithVisibleTo` green) | spec Decision 2 |
| threshold-not-addressable-room-heard | PASS | `test_reachability.py::TestThreshold`; `test_interaction_services.py` "a target at the threshold is refused with its own words"; `tagReachability.test.ts` threshold refusal | spec Decision 2; ADR-0293 |
| whisper-still-reaches-the-threshold | PASS | `TestThreshold.test_a_whisper_still_reaches_the_threshold`; `tagReachability.test.ts` "still reaches the threshold by whisper" | spec Decision 7 (proposed, easy to flip) |
| entrance-is-the-first-line-server-marked | PASS | `TestEntrance.test_the_first_pose_is_the_entrance_and_the_second_is_not` (ENTRY, window, room_state refresh; second demoted, no window); `test_the_first_standard_pose_is_the_entrance` (REST) | spec Decision 3, 8 |
| second-entrance-refused | PASS | `test_a_second_entrance_is_refused` (400 with the copy); `_entrance_pose_kind` demotion | spec Decision 3 |
| a-first-say-is-an-entrance | PASS | `TestEntrance.test_a_first_say_is_an_entrance_but_a_whisper_is_not` | spec Decision 8 |
| composer-shows-the-entrance-as-a-state | PASS | `CommandInput.test.tsx` "shows the entrance state with the technique attachment before the first pose", "shows no entrance state ... once the viewer has entered", "sends the first pose as the entrance"; `threshold-1280.png` | spec Decision 3 |
| technique-stays-an-attachment | PASS | `CommandInput.test.tsx` entrance-technique dispatch test (unchanged, now under the derived state); `threshold-1280.png` | spec Decision 3 |
| mark-clears-on-the-first-pose | PASS | journey screens 2 and 5; `threshold-entered-1280.png` | spec screens 2, 5 |
| leaving-without-entering-is-nothing | PASS | no departure surface added; movement lines unchanged (#3856) | spec Decision 4 |
| present-at-start-backfill | PASS | `capture_prescene_interactions` attaches a present writer's recent room lines (`test_precapture_services` green), which `has_entered` then reads | spec Decision 5, 6 |
| idempotent-retry-of-a-first-pose | PASS | `test_replay_preserves_data_accumulated_since_the_original_submission` green after `pose_kind` left the comparison | n/a |
| docs-in-tandem | PASS | `docs/systems/scenes.md` "Scene participation and the threshold" and "The entrance", co-ownership paragraph; `docs/systems/magic.md` pointer; `docs/systems/INDEX.md`; scenes glossary (Threshold, Entrance); `src/world/scenes/CLAUDE.md`; `frontend/src/game/CLAUDE.md`; ADR-0300 + index | n/a |
| lingering-enforcement-and-shoo-commands | OUT_OF_SCOPE | ruling: courtesy, not code; a later general mechanism | spec Decision 4 |
| telnet-look-mark-and-no-resonance-warning | OUT_OF_SCOPE | spec Scope | spec Scope |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Viewer row | "Tehom *" with the you tag while not entered | MATCH | `threshold-1280.png` |
| Newcomer row | "Nyx *" while not entered | MATCH | `threshold-1280.png` |
| Mark | Asterisk after the name, muted, title "Not yet in the scene", no explainer | MATCH | `threshold-1280.png`, journey assertion |
| Composer right slot before the first pose | "✨ Entrance" as a state, technique control beside it, no button | MATCH | `threshold-1280.png` |
| After the first poses | No asterisks, no Entrance state | MATCH | `threshold-entered-1280.png` |
| Characters count | Unchanged by the mark | MATCH | both |
| Rest of the page | Feed, chips, Actions fold, exits unchanged | MATCH | both |

## Unresolved findings

None
