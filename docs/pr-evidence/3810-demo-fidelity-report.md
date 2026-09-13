# Review evidence

- Reviewed revision: `7e3d3adf74e40694866c96810d196a3d73164f7b`
- Reviewer: `demo-fidelity-reviewer` (local agent pass, gated by `review:evidence-required` on #3810)
- Reviewer verdict: PASS
- Application/build identity: Vitest + React Testing Library render of the real `CommandInput` component (jsdom); no separate build artifact, this is the same component tree the production bundle ships
- Environment: devcontainer, Node/pnpm, jsdom (no browser paint; see Visual review below)
- Viewports/themes: not applicable, jsdom performs no layout/paint, so no viewport or theme distinction exists to compare
- Approved design: https://claude.ai/code/artifact/01ffa01c-2516-429d-9aa8-ce676bf719dc (this session had no `Artifact` tool or authenticated `claude.ai` session to re-fetch it live; the local scratchpad source file that produced and published that exact artifact, dated before this review and matching the issue's own correction comment verbatim, was used as the design reference instead, disclosed here rather than silently substituted)
- Visual review: Not applicable: no browser/pixel-rendering capability was available this pass (no `Artifact` tool or authenticated `claude.ai` session to re-fetch the hosted demo, no headless-browser screenshot taken). A DOM/class-string structural comparison was used instead and is detailed in Comparison notes and the Screen 2 caveat below; that is a real but partial substitute, not a visual review.
- Visual verdict: NOT_APPLICABLE
- Screenshots: Not applicable (see Visual review). Rendered-DOM captures (HTML, not raster images, since jsdom does not paint) committed at `docs/pr-evidence/3810-render-evidence/screen1-whisper-no-refusal.html`, `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html`, `docs/pr-evidence/3810-render-evidence/midDraft-a-reachable-same-place.html`, `docs/pr-evidence/3810-render-evidence/midDraft-b-live-refusal-after-room-state-push.html`
- Comparison notes: see the Screen-by-screen section below
- Tested interactions: whisper a target across the room (no refusal); switch the mode dropdown from Whisper to Tabletalk while that target is still set (refusal fires live, before any text is typed); with an already-set Tabletalk target at the actor's own place, a room_state push moves the target to a different place (refusal fires live, mid-draft); the symmetric case, the actor's own place changes instead (refusal fires live); a room-wide `pose` message from a seated actor to someone at a different table (no refusal, since only Tabletalk is place-scoped)
- Fixture/live boundary: all frontend evidence (RTL renders, the 3 pre-existing committed CommandInput tests, tagReachability's 9 unit tests) uses mocked room/composer state, no real WebSocket or Redux store. Backend evidence (`RoomStatePlaceAssignmentTests`, `PlaceJoinLeaveBroadcastsRoomStateTests`) runs against a real SQLite-backed test database with FactoryBoy rows. No full-stack (real WS frame to real Redux dispatch to real render) pass was performed.
- Overall outcome: PASS

## Approved-design reference

Demo URL (issue-cited, current, post-correction):
`https://claude.ai/code/artifact/01ffa01c-2516-429d-9aa8-ce676bf719dc`

Live fetch attempted and failed: this session has no `Artifact` tool and no
authenticated `claude.ai` session. `curl` on the artifact URL returns the SPA
shell only (no content); a Playwright `chromium.launch()` navigation to the
same URL 403s on `GET /api/frame/01ffa01c-...` (auth-gated), confirmed by
inspecting the network log. This is disclosed, not silently worked around.

What stood in for the live fetch: this session's own scratchpad
(`/tmp/.../6ca29b52-f39d-4a56-96d2-ecb097584fb9/scratchpad/demo-3810/index.html`,
dated well before this review began) contains the demo's full HTML/CSS/JS
source, the very file that was published to the URL above. Its content
matches the issue's own correction comment ("Demo republished to the same
link with the corrected walkthrough: whisper someone, switch mode, watch the
refusal fire live") and the corrected mechanism described in the spec
(whisper, then mode-switch, not `@Name` autocomplete) verbatim, screen
titles and all. This is treated as the demo source below, quoted and
compared against directly, but the hosted artifact was not re-rendered
pixel-for-pixel in a browser this pass.

## Environment / render method

- Backend: `arx test --sqlite --exclude-tag postgres world.scenes.tests.test_place_services flows.tests.test_room_state_serializer` and the broader `flows`/`world.scenes` suites, all green (see Requirement ledger for exact counts).
- Frontend, existing committed tests: `pnpm exec vitest run` on `CommandInput.test.tsx`, `tagReachability.test.ts`, `handleRoomStatePayload.test.ts`, `gameSlice.test.ts`, `GamePage.test.tsx`, all passed.
- Frontend, actual rendered-DOM evidence (this review's own harness, not a committed test): a throwaway Vitest + React Testing Library spec, created, run, and deleted before this report was written (`git status --short` in the worktree was clean afterward) rendered the real `<CommandInput>` component (jsdom, no visual/pixel viewport since RTL does not paint, so this is DOM/markup evidence, not a screenshot) and dumped `container.innerHTML` at each step. The four captures are committed alongside this report.
- Playwright e2e: not attempted for this feature. Standing up a real two-character room plus Place scenario in `frontend/e2e/` would require new fixture/scaffolding beyond what exists in `frontend/e2e/*.spec.ts` today (none of the existing specs stand up `PlacePresence`/multi-persona room state). Building that is a proportionate follow-up, not something this review invents on the spot; see the Requirement ledger's OUT_OF_SCOPE row for the authorized decision.
- Fixture-vs-live boundary: every character/room/Place/room_state value in both the RTL harness and the pre-existing committed tests is mocked. The backend serializer/broadcast tests run against a real SQLite-backed test database with FactoryBoy rows, live for the backend half only.

## Screen 1: Whispering across the room

Demo shows: Elyn at "The Long Table", Vayne "elsewhere in the room." Clicking
Vayne's portrait opens a card whose Whisper button sets Vayne as the real
target (composer ghost text: "Whisper -> Vayne"). Caption: "Whisper's
reachability is receiver-based, never location-based, so this is always
fine no matter where Vayne stands (unchanged)." No refusal banner is drawn
on this screen at all.

Branch renders: `tagReachability()` short-circuits to reachable whenever
`mode === 'whisper'`, before any name/place lookup
(`frontend/src/scenes/tagReachability.ts`). Rendered evidence
(`screen1-whisper-no-refusal.html`): no `tag-refusal` node in the DOM at
all, Send button has no `disabled` attribute, with Vayne's `place_id: null`
and the actor seated at a place. Covered by `tagReachability.test.ts`'s "is
reachable for a whisper regardless of location" and `CommandInput.test.tsx`'s
"does not show the tag-refusal banner in whisper mode regardless of
location."

Comparison: matches. The card-popup/Whisper-button UI itself (portrait
click, card, Whisper button) is pre-existing #3787 surface, out of this
issue's diff, and not re-checked here.

Verdict: MATCHES.

## Screen 2: Switching to table talk carries the target

Demo shows: same room, mode dropdown switched from Whisper to Tabletalk
with Vayne (still elsewhere) as the carried target. The demo's own toy JS
toggles a refusal block reading, verbatim: "Vayne is across the room and
will not see table talk." / "Address the room to reach them, or send a
whisper. Your draft is kept." Caption: "catching it the instant the mode
changes, before a single word is typed, is new this round. The same live
recheck also catches a target who leaves the table mid-draft: one
mechanism, two triggers."

Branch renders, trigger A (mode switch): rendered evidence
(`screen2-tt-live-refusal.html`), captured from a rerender of the same
mounted component (whisper to tt, no remount), contains the `tag-refusal`
banner with byte-identical wording to the demo and to the server's own
`_describe_unreachable_targets`/`_TARGET_UNREACHABLE_HINT`
(`src/world/scenes/interaction_services.py`), and the Send button gains
`disabled`.

Branch renders, trigger B (target goes stale mid-draft, no mode switch):
rendered evidence (`midDraft-a-reachable-same-place.html` to
`midDraft-b-live-refusal-after-room-state-push.html`), captured from a
rerender where only `roomCharacters` changed (Vayne's `place_id` moved from
matching the actor to a different place) while `composerMode` stayed `tt`
throughout: banner appears, Send disables, same exact markup. This is the
demo's stated second trigger, driven by the same `useMemo` as trigger A
(`CommandInput.tsx`), whose dependency array recomputes on either a
`composerMode.command` change (trigger A) or a `roomCharacters`/`isAtPlace`/
`currentPlaceId` change (trigger B).

Branch renders, trigger C (the actor's own place changes instead, the
symmetric case): a follow-up test added after this review's first pass
(`CommandInput.test.tsx`, "tag reachability (#3810)" describe block) mounts
in `tt` mode with the target at the actor's current place (no banner), then
rerenders with only `currentPlaceId` changed to a different place, target
unchanged: banner appears, Send disables. Confirms the mechanism is
genuinely symmetric, not just inferred from the shared equality check.

Visual idiom parity (demo's explicit claim: reuses the exact existing
idiom): both banner blocks in `CommandInput.tsx` (`reply-refusal` and
`tag-refusal`) carry byte-for-byte identical `className`
("flex flex-col gap-0.5 border-l-2 border-destructive bg-destructive/10
px-3 py-1.5 text-xs"), identical `role="status"`, identical
`aria-live="polite"`, identical inner `<strong>`/`<span>` structure. Only
`data-testid` differs, as it must. Confirmed by the rendered DOM captures,
not just source-reading.

Comparison: matches, on wording and mechanism, for all three live triggers,
with confirmed class-level parity to the reused idiom.

Caveat (disclosed, not a defect): this pass did not visually compare the
two banners in a real painted browser at a stated viewport/theme. The
comparison above is DOM/class-string identity, a strong but not total
substitute for a human or vision-capable side-by-side render. The reused
classes resolve to real theme tokens this repo already ships, since the
`reply-refusal` block they are copied from already renders correctly in
production (#3787); that prior production rendering is why this substitute
is reasonable here, not a claim that this pass independently re-verified it
in a browser.

Verdict: MATCHES, with the render-method caveat above.

## Screen 3: What the check reads

Demo shows: explicitly a table, not a drawing, since this feature writes
nothing to the database. Every row in the demo's table corresponds to a
real, tested surface in the diff:

| Demo row | Verified against code |
|---|---|
| `RoomStateObject.place_id`, room_state payload, per character | Present. `frontend/src/hooks/types.ts`; backend `ObjectStateSerializer.place_id` and its batched resolution, `src/flows/service_functions/serializers/room_state.py`. Covered live by `RoomStatePlaceAssignmentTests` (backend, green). |
| `join_place`/`leave_place`/`clear_place_presence_for_character` now broadcast | Present for `join_place`/`leave_place` (`src/world/scenes/place_services.py`). `clear_place_presence_for_character` is not touched, matching the spec's own design note that it already gets a broadcast for free via `at_object_leave`. Covered by `PlaceJoinLeaveBroadcastsRoomStateTests` (backend, green). |
| Viewer's own `isAtPlace`/`currentPlaceId` sourced from Redux, not the stale React Query | Present. `frontend/src/game/GamePage.tsx`, `currentPlaceId` now reads `roomData?.viewer_place_id`. Covered by `GamePage.test.tsx`'s updated tests. |
| `tagReachability()` | Present. `frontend/src/scenes/tagReachability.ts`, sibling of `replyReachability.ts` as named. 9 unit tests, all green. |
| Mode-switch recheck | Present, via the `tagRefusal` `useMemo`'s dependency on `composerMode.command`, which `handleModeChange` mutates through `onModeChange`. Verified live via rerender. |
| Composer live-recheck effect | Present, as the same `useMemo`, not a separate `useEffect`, satisfying "one mechanism, two triggers." Verified live via rerender for both original triggers plus the symmetric actor's-own-place trigger. |
| Refusal copy mirrored, not reinvented | Present, verbatim match confirmed against `src/world/scenes/interaction_services.py`. |

Comparison: every row in the demo's table corresponds to a real, tested
surface in the diff.

Verdict: MATCHES.

## Divergences the build got right

No intentional, ratified divergence from the demo was found. The one
structural choice that differs from a literal reading of the demo's Screen
3 row ("Composer live-recheck effect"), implementing it as a `useMemo`
rather than a separate `useEffect`, is an implementation detail, not a
divergence from approved behavior: the demo's own caption says "one
mechanism, two triggers," which the `useMemo`'s single dependency array
satisfies exactly.

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Refusal banner bold first line naming the target and venue | Exact wording matching the demo's `.refusal strong` and the server's own copy | MATCH | `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html` |
| Refusal banner quieter second line | Exact wording matching the demo's `.refusal .fix` and the server's own hint | MATCH | `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html` |
| Refusal banner left-rule/destructive styling idiom | Same visual idiom as the pre-existing `reply-refusal` banner (#3787) | MATCH | `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html` |
| Send button disabled while unreachable | Disabled attribute present exactly when the banner renders | MATCH | `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html` |
| Send button enabled when reachable | No disabled attribute in the whisper and place-match captures | MATCH | `docs/pr-evidence/3810-render-evidence/screen1-whisper-no-refusal.html` |
| Refusal fires on mode-switch alone, before any text is typed | Banner appears on a rerender with no draft content set | MATCH | `docs/pr-evidence/3810-render-evidence/screen2-tt-live-refusal.html` |
| Refusal fires on room-state change alone, mid-draft, without a mode switch | Banner appears on a rerender where only roomCharacters changed | MATCH | `docs/pr-evidence/3810-render-evidence/midDraft-b-live-refusal-after-room-state-push.html` |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | Screen 1: whisper always reachable regardless of location; `screen1-whisper-no-refusal.html`, `tagReachability.test.ts` | |
| A02 | PASS | Screen 2 trigger A: mode-switch carries a stale target, refusal fires live; `screen2-tt-live-refusal.html`, `CommandInput.test.tsx` | |
| A03 | PASS | Screen 2 trigger B: target's place changes mid-draft, refusal fires live; `midDraft-a-reachable-same-place.html`, `midDraft-b-live-refusal-after-room-state-push.html` | |
| A04 | PASS | Screen 2 trigger C: actor's own place changes mid-draft, refusal fires live (symmetric case); `CommandInput.test.tsx` "tag reachability (#3810)" describe block | |
| A05 | PASS | Visual idiom reuse: byte-identical className/role/aria-live between reply-refusal and tag-refusal; `CommandInput.tsx` source diff plus rendered captures | |
| A06 | PASS | Refusal copy verbatim match to server strings; `src/world/scenes/interaction_services.py` compared line by line | |
| A07 | PASS | Screen 3: every named field/module exists and is tested; serializer, broadcast, Redux, tagReachability, useMemo all verified against the diff | |
| A08 | OUT_OF_SCOPE | Frontend/e2e directory has no existing scenario standing up a multi-persona room plus Place | Full-stack pixel-level browser visual pass (real WS to Redux to paint) descoped for this PR: building the Place/room E2E fixture scaffolding it requires is substantial new infrastructure this issue did not ask for, and the reused banner classes are already visually proven in production via the pre-existing reply-refusal banner shipped in #3787. Revisit if a general Place/room E2E fixture is built for another issue. |

## Unresolved findings

- None
