# Review evidence: say and pose read as whole sentences, the actor rendered into the line on web and telnet (#3858)

Closes #3858.

- Reviewed revision: 68ef6be04426c6f7aa881c9155610b3d5055879c
- Reviewer: Claude Fable 5.1 (implementing session), vision review of the rendered application screenshots below, plus a demo-fidelity review pass (a general-purpose Sonnet 5 subagent following `tools/agents/demo-fidelity-reviewer.md`, since the named agent is not registered in this session) that read the approved demo's HTML, the same screenshots, the formatter, the delivery seams and the Python tests; it returned PASS with one low finding (serializer tests for a muted row and a masked persona were promised by the spec and missing), folded in at the reviewed revision.
- Reviewer verdict: PASS
- Application/build identity: `pnpm build` of this branch at the reviewed revision (Vite production bundle, output `src/web/static/dist`), served by `vite preview --port 4173` exactly as `playwright.config.ts` does.
- Environment: devcontainer (Ubuntu 24.04 x64), Chrome Headless Shell 145.0.7632.6 via Playwright 1.58.2 (chromium v1208), headless, `hasTouch: true` per `playwright.config.ts`.
- Viewports/themes: 1280x800, light theme (the system default; no `data-theme` stamp).
- Approved design: issue #3858's spec (demo v1, https://claude.ai/code/artifact/73da69fe-e26c-4656-81c9-7af1c20e0d93, built from Dan's design direction of 2026-09-14, which carries `spec:approved`). Seven screens: a pose and a say as whole sentences under the card with the name set heavier; an emit as its own text; a whisper; a say in a language garbled for a listener; a companion pose reading as the companion; a semipose and an already-named pose; and the same lines on telnet.
- Visual review: completed on the two screenshots below, taken from the running application (not a mockup) by `frontend/e2e/feed-sentences.spec.ts`, compared against the demo's `.pose` bubbles (card, `.txt` line, `.actor` weight), its emit and its companion row with the `(via ...)` tell.
- Visual verdict: PASS
- Screenshots: ![A pose and a say in the scene reader: each bubble keeps its card (avatar, name, time) and its body is the whole sentence, "Tehom stops at the edge of the plaza, hood up." and "Tehom says, "Rain again."", with the name set semibold](https://raw.githubusercontent.com/Arx-Game/arxii/68ef6be04426c6f7aa881c9155610b3d5055879c/docs/reviews/3858/feed-sentences-1280.png) ![The same feed with an emit from Nyx as its own text, no actor prefix, and a companion pose whose card reads "Hask (via Tehom)" and whose body reads "Hask lifts his head, ears back."](https://raw.githubusercontent.com/Arx-Game/arxii/68ef6be04426c6f7aa881c9155610b3d5055879c/docs/reviews/3858/feed-sentences-emit-companion-1280.png)
- Comparison notes: In `feed-sentences-1280.png` the two bubbles keep the card above (avatar, "Tehom", the time) and their bodies read "Tehom stops at the edge of the plaza, hood up." and "Tehom says, "Rain again."" with "Tehom" visibly heavier than the rest, the demo's `.actor` treatment; the Kudos chip and the nominate control sit below as before. `feed-sentences-emit-companion-1280.png` shows Nyx's emit "The bells go quiet, one by one." with no name in the line and the card naming the writer, and the companion row with "Hask (via Tehom)" on the card and "Hask lifts his head, ears back." as the body, the demo's screen 6. The whisper (screen 4) is asserted by the journey as the visible text "Nyx whispers, "Not here."" and not screenshotted. The language screen (5), the semipose and already-named screen (7) and the telnet block have no web render of their own: they are pinned by `test_line_rendering.py` row for row against the demo's grammar table, by `test_language_interactions.py` for a fluent and a zero-fluency viewer's REST line, by `test_interaction_services.py` for the per-object garbled line and the companion line on the live payload, and by `test_actions.py` and `test_companion_emote_action.py` for the telnet strings. Differences from the demo that are not defects: the companion row shows the owner's avatar because no companion art exists (#3294's documented stand-in), and the demo's telnet mock for Nyx's own whisper echo is Evennia's second person, which this change leaves as it was.
- Tested interactions: reach "In world" with an active scene through the shared harness; push a pose and a say over the fixture socket shaped exactly as `push_interaction` sends them, read the line as the bubble body with `data-actor` on the name and the semibold span holding the name; push an emit and a companion pose, read the emit with no actor mark and the companion line marked "Hask" with the "(via Tehom)" tell; push a whisper addressed to the viewer and read its sentence. Zero page errors (asserted).
- Fixture/live boundary: REST and the game WebSocket are mocked through `frontend/e2e/support/gameHarness.ts` (the same fixture `narrative-play-delivery.spec.ts` uses); no Django or Evennia process and no database took part, so the server side (the formatter, the payload and serializer `line`, the telnet broadcasts) is covered by the Python tests named above rather than the journey. The readers, `ActorLine`, the store, the mapper and the CSS are the real ones.
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| body-is-the-whole-line-on-web | PASS | `PoseUnit.test.tsx` "renders the line as the body"; `ExplorationReader.test.tsx`; `feed-sentences-1280.png`; journey screens 1, 2 | spec Decision 1 |
| card-is-metadata-never-the-actor | PASS | `feed-sentences-1280.png` (card and line both carry the name); `ExplorationReader.test.tsx` (name once on the card, once at the head of the line) | spec Decision 1 |
| telnet-gets-the-same-line | PASS | `test_actions.py` pose broadcast carries `{caller} stretches.` and its mapping; whisper string; `test_companion_emote_action.py` "Fang grooms itself."; say kept as `$You() $conj(say)` | spec Decision 2 |
| rendered-at-display-time-by-one-server-formatter | PASS | `test_line_rendering.py` (12 cases, the demo's table); `_line_for` on the payload (`test_interaction_services.py`); `get_line` on the serializer; ADR-0299 committed with the stored-line and client-formatter alternatives rejected | spec Decision 3 |
| content-untouched-for-threading-and-muting | PASS | `wsPayloadToInteraction.test.ts` (content beside line); serializer test "a muted row has no line either" (content and line both blank); no writer changed | spec Decision 3 |
| per-viewer-name-and-content | PASS | serializer test "a masked persona reads by the name on the card"; `test_language_interactions.py` "the line wraps what each viewer reads"; `test_interaction_services.py` "a garbled listener reads a garbled sentence" | spec user story 4; #1109, #2993 |
| emit-action-outcome-untouched | PASS | `test_line_rendering.py` emit/action/outcome cases; `feed-sentences-emit-companion-1280.png` | spec Decision 4 |
| companion-pose-reads-as-the-companion | PASS | `test_interaction_services.py` companion payload; `PoseUnit.test.tsx` "reads a companion pose as the companion"; `feed-sentences-emit-companion-1280.png` | spec screen 6; #3294 |
| leading-name-set-heavier | PASS | `feed-sentences-1280.png` (the weight reaches the page); journey asserts the semibold span holds the name | spec Decision 5 |
| already-named-and-semipose | PASS | `test_line_rendering.py` "a pose that already names the actor is left alone", "a semipose glues onto the name", "a longer name sharing the prefix is not the actor" | spec Decision 6 (proposed, easy to flip) |
| older-rows-without-a-line | PASS | `PoseUnit.test.tsx` "falls back to the recorded content on a row without a line"; `wsPayloadToInteraction.test.ts` "leaves the line absent when the server sent none" | n/a |
| api-types-in-tandem | PASS | `src/schema.json` and `frontend/src/generated/api.d.ts` regenerated (`InteractionList.line`) | n/a |
| docs-in-tandem | PASS | `docs/systems/scenes.md` "The actor in the line", `docs/systems/INDEX.md`, ADR-0299 + index, scenes glossary "Line", `src/world/scenes/CLAUDE.md`, `frontend/src/scenes/CLAUDE.md`, `frontend/src/game/CLAUDE.md` | n/a |
| where-a-players-command-output-renders | OUT_OF_SCOPE | #3856 | spec Scope |
| composer-default-and-entrance | OUT_OF_SCOPE | #3857, #3867 | spec Scope |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| Pose bubble | Card above, body "Tehom stops at the edge of the plaza, hood up." | MATCH | `feed-sentences-1280.png` |
| Say bubble | Body "Tehom says, "Rain again."" | MATCH | `feed-sentences-1280.png` |
| Leading name | Heavier than the rest of the line | MATCH | `feed-sentences-1280.png` |
| Card | Avatar, name, time unchanged; reactions and controls below as before | MATCH | both |
| Emit | The text as written, no actor prefix, card names Nyx | MATCH | `feed-sentences-emit-companion-1280.png` |
| Companion pose | Card "Hask (via Tehom)", body "Hask lifts his head, ears back." | MATCH | `feed-sentences-emit-companion-1280.png` |
| Whisper | "Nyx whispers, "Not here."" visible in its thread | MATCH | journey assertion (not screenshotted) |
| Composer and sidebar | Unchanged | MATCH | both |

## Unresolved findings

None
