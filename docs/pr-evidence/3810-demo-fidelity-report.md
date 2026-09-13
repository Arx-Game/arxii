# Demo fidelity review: #3810 "Reachable while you type"

**Reviewed commit:** `16c36db57f9753985dd997daa4742cb407eb90a6` (branch
`feature-3810-tagging-tells-you-too-late-check-reachab`, fork point from main
`579e3bba164f06f1ae11a76fd20d9c204c1fb6a1`)

**Reviewer:** `demo-fidelity-reviewer` pass, run before PR open, gated by
`review:evidence-required` on #3810.

## Approved-design reference

- **Demo URL (issue-cited, current, post-correction):**
 `https://claude.ai/code/artifact/01ffa01c-2516-429d-9aa8-ce676bf719dc`
- **Live fetch attempted and failed:** this session has no `Artifact` tool and no
 authenticated `claude.ai` session. `curl` on the artifact URL returns the SPA
 shell only (no content); a Playwright `chromium.launch()` navigation to the
 same URL 403s on `GET /api/frame/01ffa01c-...` (auth-gated), confirmed by
 inspecting the network log. **This is disclosed, not silently worked around.**
- **What stood in for the live fetch:** this session's own scratchpad
 (`/tmp/.../6ca29b52-f39d-4a56-96d2-ecb097584fb9/scratchpad/demo-3810/index.html`,
 543 lines, dated 2026-09-13 19:57, i.e. the same session that drafted and
 posted this issue's spec, well before this review began at 22:xx) contains
 the demo's full HTML/CSS/JS source. Its content matches the issue's own
 correction comment ("Demo republished to the same link with the corrected
 walkthrough: whisper someone, switch mode, watch the refusal fire live") and
 the corrected mechanism described in the spec (whisper → mode-switch, not
 `@Name` autocomplete) verbatim, screen titles and all. I am treating this as
 the demo source and quoting/comparing against it directly below, but **I did
 not re-render the hosted artifact pixel-for-pixel in a browser** - that
 distinction is called out per-screen below rather than papered over.

## Environment / render method

- **Backend:** `just test-fast world.scenes` - 1572 tests, **OK** (SQLite tier).
 Confirms the serializer/broadcast changes described in Screen 3's table.
- **Frontend, existing committed tests:** `pnpm exec vitest run` on
 `CommandInput.test.tsx`, `tagReachability.test.ts`,
 `handleRoomStatePayload.test.ts`, `gameSlice.test.ts`, `GamePage.test.tsx` -
 258 tests, all passed.
- **Frontend, actual rendered-DOM evidence (this review's own harness, not a
 committed test):** a throwaway Vitest + React Testing Library spec
 (`frontend/src/game/components/__reviewTmp3810.test.tsx`, created, run, and
 **deleted** before this report was written - `git status --short` in the
 worktree is clean) rendered the real `<CommandInput>` component (jsdom, no
 visual/pixel viewport - RTL does not paint, so this is DOM/markup evidence,
 not a screenshot) and dumped `container.innerHTML` at each step. The four
 captures are committed alongside this report at
 `docs/pr-evidence/3810-render-evidence/`:
 - `screen1-whisper-no-refusal.html`
 - `screen2-tt-live-refusal.html`
 - `midDraft-a-reachable-same-place.html`
 - `midDraft-b-live-refusal-after-room-state-push.html`
- **Playwright e2e:** not attempted for this feature. Standing up a real
 two-character room + Place scenario in `frontend/e2e/` would require new
 fixture/scaffolding beyond what exists in `frontend/e2e/*.spec.ts` today
 (none of the existing specs stand up `PlacePresence`/multi-persona room
 state); per this review's own instructions, that's substantial new E2E
 infrastructure, so I fell back to option 1 (RTL) instead of inventing it,
 and I'm saying so explicitly rather than skipping visual verification
 silently.
- **Viewport/theme:** not applicable in the above sense - jsdom has no
 viewport/theme rendering. The banner's Tailwind classes are read directly
 off both the demo's `.refusal` CSS block and the built component's JSX
 (both quoted below), which is a valid comparison for *class/structure*
 parity but **not** a substitute for a human/vision-capable check of the
 banner painted in an actual browser at a real viewport and both light/dark
 themes. That gap is called out explicitly in the verdict.
- **Fixture-vs-live boundary:** every character/room/Place/`room_state` state
 in both the RTL harness and the pre-existing committed tests is mocked
 (`mockRoomCharacters`, a fake `useAppSelector`, no real WebSocket, no real
 Redux store, no real backend). The backend serializer/broadcast tests
 (`test_room_state_serializer.py`, `test_place_services.py`) run against a
 real SQLite-backed test database with FactoryBoy rows - those are live,
 end-to-end for the backend half only. Nothing in this review exercises the
 full stack (real WS frame → real Redux dispatch → real render) end to end.

## Tested interactions

1. Render `<CommandInput>` with `composerMode={command:'whisper', targets:['Vayne']}`,
 `roomCharacters=[{name:'Vayne', place_id:null}]`, `isAtPlace=true`,
 `currentPlaceId=5` → assert no `tag-refusal` banner, Send enabled.
2. **Rerender the same mounted instance** (no remount) with
 `composerMode={command:'tt', targets:['Vayne']}`, same room state → assert
 the `tag-refusal` banner appears and Send becomes disabled, on the very
 next render after the mode-switch prop change (the literal "mode switch
 carries a stale target" trigger).
3. Render already in `tt` mode with `targets:['Vayne']`,
 `roomCharacters=[{name:'Vayne', place_id:5}]` (same place as actor,
 `currentPlaceId=5`) → assert no banner, Send enabled.
4. **Rerender the same mounted instance** with `roomCharacters` mutated so
 Vayne's `place_id` becomes `9` (simulating a `room_state` push after Vayne
 leaves the table), same `composerMode` (`tt`, unchanged) → assert the
 banner appears and Send disables, without any mode-switch (the literal
 "target goes stale mid-draft" trigger, decision 4's second half).
5. The three pre-existing committed tests
 (`CommandInput.test.tsx:1874-1914`, `describe('tag reachability (#3810)'`)
 were run and read: static-mount checks for `tt`-mismatched-place (refused),
 `tt`-matched-place (allowed), and `whisper`-anywhere (allowed).
6. `tagReachability.test.ts`'s 9 unit cases were run and read: whisper
 always-reachable, place-match reachable, place-mismatch refused (exact
 copy), room-wide (`pose`) reachable purely on physical presence even while
 seated at a place, name-not-found refused, case-insensitive match, multi-
 name refusal grammar, empty-targets short-circuit.
7. Backend: `test_room_state_serializer.py`'s new
 `RoomStatePlaceAssignmentTests` (tablemate carries `place_id`, elsewhere
 character carries `null`, `viewer_place_id` reflects the caller's own
 presence, and is `null` from a no-presence caller's own point of view) and
 `test_place_services.py`'s new broadcast test were run (part of the 1572
 green) and read.

---

## Screen 1 · Whispering across the room

**Demo shows** (`demo-3810/index.html:302-344`): Elyn at "The Long Table",
Vayne "elsewhere in the room." Clicking Vayne's portrait opens a card
(`chip-exists`) whose Whisper button sets Vayne as the real target
(`composer-box`: "Whisper → Vayne"). Caption: "Whisper's reachability is
receiver-based, never location-based, so this is always fine no matter where
Vayne stands (unchanged)." No refusal banner is drawn on this screen at all.

**Branch renders:** `tagReachability()` short-circuits to `REACHABLE` whenever
`mode === 'whisper'`, before any name/place lookup
(`frontend/src/scenes/tagReachability.ts:34-36`). Rendered evidence
(`screen1-whisper-no-refusal.html`): no `tag-refusal` node in the DOM at all,
Send button has no `disabled` attribute, with Vayne's `place_id: null` (i.e.
maximally "elsewhere") and the actor seated at a place. Covered by
`tagReachability.test.ts`'s "is reachable for a whisper regardless of
location" and `CommandInput.test.tsx`'s "does not show the tag-refusal banner
in whisper mode regardless of location."

**Comparison:** matches. Card-popup/Whisper-button UI itself (portrait click →
card → Whisper button) is pre-existing #3787/earlier surface, out of this
issue's diff and not re-checked here (no observed regression in the diff to it).

**Verdict: MATCHES.**

## Screen 2 · Switching to table talk carries the target

**Demo shows** (`:346-389`): same room, mode dropdown switched from Whisper to
Tabletalk with Vayne (still elsewhere) as the carried target. The demo's own
toy JS (`:514-543`) toggles a `.refusal` block reading, verbatim:

> **Vayne is across the room and will not see table talk.**
> Address the room to reach them, or send a whisper. Your draft is kept.

Caption: "The banner's wording and left-rule styling are the existing #3787
refusal idiom (exists today); catching it the instant the mode changes, before
a single word is typed, is new this round. The same live recheck also catches
a target who leaves the table mid-draft: one mechanism, two triggers."

**Branch renders - trigger A (mode switch):** rendered evidence
(`screen2-tt-live-refusal.html`), captured from a **rerender of the same
mounted component** (whisper → tt, no remount), contains:

```html
<div class="flex flex-col gap-0.5 border-l-2 border-destructive bg-destructive/10 px-3 py-1.5 text-xs"
 data-testid="tag-refusal" role="status" aria-live="polite">
 <strong class="text-destructive">Vayne is across the room and will not see table talk.</strong>
 <span class="text-muted-foreground">Address the room to reach them, or send a whisper. Your draft is kept.</span>
</div>
```

and the Send button gained `disabled=""`. Wording is byte-identical to the
demo's `.refusal` text and to the server's own
`_describe_unreachable_targets`/`_TARGET_UNREACHABLE_HINT`
(`src/world/scenes/interaction_services.py:54,72`).

**Branch renders - trigger B (target goes stale mid-draft, no mode switch):**
rendered evidence (`midDraft-a-reachable-same-place.html` →
`midDraft-b-live-refusal-after-room-state-push.html`), captured from a
rerender where only `roomCharacters` changed (Vayne's `place_id` moved from
`5`, matching the actor, to `9`, a different place) while `composerMode`
stayed `tt` throughout: banner appears, Send disables, same exact markup.
This is the demo's stated **second trigger** ("a target who leaves the table
mid-draft"), and it is driven by the *same* `useMemo` as trigger A
(`CommandInput.tsx:489-499`), whose dependency array
(`[composerMode, roomCharacters, isAtPlace, currentPlaceId, currentPlaceName]`)
recomputes on either a `composerMode.command` change (trigger A, arriving via
`handleModeChange`, `:858-869`, which still carries `composerMode.targets`
forward unchecked - confirmed still true, matching the spec's Correction note
verbatim) or a `roomCharacters`/`isAtPlace`/`currentPlaceId` change (trigger
B, arriving via a fresh `room_state` Redux push). One mechanism, two triggers,
exactly as both the spec (decision 4) and the demo caption claim - verified by
rendering both paths, not inferred from reading the `useMemo` alone.

**Visual idiom parity (demo's explicit claim: "reuses the exact existing
idiom"):** read both banner blocks in `CommandInput.tsx` side by side
(`:1034-1044` `reply-refusal`, `:1045-1055` `tag-refusal`). Byte-for-byte
identical `className`
(`"flex flex-col gap-0.5 border-l-2 border-destructive bg-destructive/10 px-3 py-1.5 text-xs"`),
identical `role="status"`, identical `aria-live="polite"`, identical inner
`<strong className="text-destructive">`/`<span className="text-muted-foreground">`
structure. Only `data-testid` differs (`reply-refusal` vs `tag-refusal`), as
it must. **Confirmed by rendered DOM, not just source-reading:** both classes
appear verbatim in the captured HTML files.

**Comparison:** matches, on both wording and mechanism, for both of the demo's
stated triggers, with confirmed class-level parity to the reused idiom.

**Caveat (disclosed, not a defect):** I did not visually compare the two in a
real painted browser at a stated viewport/theme (see Environment section) -
the comparison above is DOM/class-string identity, which is a strong but not
total substitute for a human/vision-capable side-by-side render. Tailwind's
`border-destructive`/`bg-destructive/10` etc. resolve to real theme tokens
this repo already ships (unlike #3660/#3667's undefined-class-hook failure
mode) since the `reply-refusal` block they're copied from already renders
correctly in production; I did not independently re-verify that in a browser
this session.

**Verdict: MATCHES, with the render-method caveat above (no live browser
visual pass performed).**

## Screen 3 · What the check reads

**Demo shows** (`:391-420`): explicitly a table, not a drawing - "this feature
writes nothing to the database." Seven rows, each naming a field/module,
today's state, and this change:

| Demo row | Verified against code |
|---|---|
| `RoomStateObject.place_id`, room_state payload, per character | **Present.** `frontend/src/hooks/types.ts:109-110`; backend `ObjectStateSerializer.place_id` and its batched resolution, `src/flows/service_functions/serializers/room_state.py:18,45-50,202-241`. Covered live by `RoomStatePlaceAssignmentTests` (backend, green). |
| `join_place`/`leave_place`/`clear_place_presence_for_character` now broadcast | **Present** for `join_place`/`leave_place` (`src/world/scenes/place_services.py:67-79,101,141`, via new `_broadcast_room_state_for_persona`). `clear_place_presence_for_character` is NOT touched in this diff - matching the spec's own design note (`:214-220`) that it already gets a broadcast for free via `at_object_leave`, so a second call would be redundant, not an omission. Covered by `PlaceJoinLeaveBroadcastsRoomStateTests` (backend, green). |
| Viewer's own `isAtPlace`/`currentPlaceId` sourced from Redux, not the stale React Query | **Present.** `frontend/src/game/GamePage.tsx:782-802` - `currentPlaceId` now reads `roomData?.viewer_place_id`, `currentPlaceName` (display-only) still resolves the name from the React Query result, matched by the Redux-sourced id. Covered by `GamePage.test.tsx`'s two updated `isAtPlace`/`tt`-offer tests (both green, both re-worded to name `viewer_place_id` explicitly). |
| `tagReachability()` | **Present.** `frontend/src/scenes/tagReachability.ts`, sibling of `replyReachability.ts` as named. 9 unit tests, all green. |
| `handleModeChange()` rechecked | **Present, indirectly** - `handleModeChange` itself is unchanged (still carries targets forward unchecked, per the Correction note), but the recheck is achieved via the `tagRefusal` `useMemo`'s dependency on `composerMode.command`, which `handleModeChange` mutates through `onModeChange`. Verified live via rerender (trigger A above), not just by reading the dependency array. |
| Composer live-recheck effect | **Present**, as the same `useMemo`, not a separate `useEffect` - a reasonable and arguably better implementation of "one mechanism, two triggers" than a literal second `useEffect`, verified live via rerender (trigger B above). |
| Refusal copy mirrored, not reinvented | **Present**, verbatim match confirmed against `src/world/scenes/interaction_services.py:54,72`. |

**Comparison:** every row in the demo's table corresponds to a real, tested
surface in the diff; no row names something absent. This screen is
architectural/informational per its own caption ("a table, not a drawing"),
so it needed source verification, not a rendered-pixel comparison, and that's
what was done.

**Verdict: MATCHES.**

---

## Scenarios grid (informational, cross-checked against `tagReachability.test.ts`)

| Demo scenario | Covered by a real test? |
|---|---|
| Room-wide, actor not at any place, target physically present → holds | `tagReachability.test.ts` "reachable in a room-wide mode as long as the target is physically present" |
| Place-scoped, actor+target same table → holds | `tagReachability.test.ts` "reachable when the target shares the actor's current place" + `CommandInput.test.tsx` "does not show...when the target shares the current place" |
| Mode switch, whisper→tt, target elsewhere → holds, new (refuses) | `CommandInput.test.tsx` "shows the tag-refusal banner...when a mode switch carries a stale target" + this review's live rerender (trigger A) |
| Mode switch, whisper→tt, target same table → holds, new (allows) | Not directly tested as a *mode-switch rerender* in the committed suite (the committed test mounts directly in `tt` mode already matched); covered indirectly by `tagReachability.test.ts`'s static place-match case. **Minor test-seam gap, not a functional defect** - the live behavior was independently confirmed by this review's own rerender harness using the reachable path (screen1→3, actor same place variant not captured as a named file but exercised while building the mid-draft harness). |
| Edge case, target leaves table mid-draft → holds, new (refuses) | This review's live rerender (trigger B) + backend `RoomStatePlaceAssignmentTests` for the payload half. No committed frontend test exercises the *rerender* form of this (only static mounts) - see Recommendation below. |
| Edge case, actor's own place changes instead → holds, new (refuses) | **Not exercised by any committed test or by this review's harness.** The `useMemo` dependency array includes `currentPlaceId`, so the mechanism should cover it (an actor-place change is symmetric with a target-place change under the same `mode==='tt' && venue.isAtPlace` branch), but I did not render this specific case. Flagging as unverified rather than inferring a pass. |
| Whisper, staying in whisper mode, target elsewhere → holds (unchanged) | `tagReachability.test.ts` + `CommandInput.test.tsx` whisper cases (Screen 1 above) |
| Room-wide, switch to Pose, target physically present → holds | `tagReachability.test.ts` "reachable in pose mode even while the actor is seated at a place" |
| Concealed target still carried forward → holds, new (refuses) | Not directly tested in the frontend diff (`tagReachability`'s "not found in roomCharacters" branch covers the mechanism generically - a concealed character is already excluded from `room_state.characters` server-side per the Verified Leak Analysis table - but no test constructs a concealed-character scenario specifically). Backend concealment-exclusion behavior itself is pre-existing (#3288) and unchanged by this diff. |
| Target has left the room entirely → holds (refuses, same as any not-found) | Covered generically by `tagReachability.test.ts`'s "unreachable when the target is not in the room at all." |

**None of these gaps are defects in the shipped mechanism** - the two
untested rows both plug into the same generic `tagReachability` logic already
covered by other cases exercising the identical code path (place-mismatch,
not-found). They are test-seam gaps worth naming, not scope questions for a
human.

## Visual checklist - Screens 1 & 2 (every drawn element, demo vs. rendered)

| Element (from the demo mockup) | Present in the real composer? | MATCH basis |
|---|---|---|
| Mode-row button showing current mode label ("Whisper" / "Tabletalk") | Yes - `ModeSelector`/mode button, pre-existing #3787 surface, unchanged by this diff | Not independently re-verified visually this pass (out of diff) |
| Composer ghost/placeholder text naming the target ("Whisper → Vayne") | Yes - pre-existing composer-mode label rendering, unchanged by this diff | Not independently re-verified visually this pass (out of diff) |
| Refusal banner: bold first line naming the target and venue | **Yes** - `<strong className="text-destructive">{tagRefusal.reason}</strong>`, exact text confirmed in rendered DOM | **MATCH** (DOM-verified) |
| Refusal banner: quieter second line ("Address the room...") | **Yes** - `<span className="text-muted-foreground">{tagRefusal.hint}</span>`, exact text confirmed | **MATCH** (DOM-verified) |
| Refusal banner: left-rule/destructive styling idiom reused from #3787 | **Yes** - identical `className` string to `reply-refusal`, confirmed by source diff + rendered DOM | **MATCH** (DOM-verified) |
| Send button disabled while unreachable | **Yes** - `disabled=""` attribute present in rendered DOM exactly when the banner renders | **MATCH** (DOM-verified) |
| Send button enabled when reachable | **Yes** - no `disabled` attribute in the whisper/place-match captures | **MATCH** (DOM-verified) |
| Refusal fires on mode-switch alone, before any text is typed | **Yes** - rerender-only, no draft content set, banner appears | **MATCH** (DOM-verified, live rerender) |
| Refusal fires on room-state change alone, mid-draft, without a mode switch | **Yes** - rerender-only, `composerMode` unchanged, only `roomCharacters` changed | **MATCH** (DOM-verified, live rerender) |
| Character portrait/card popup, Whisper button (Screen 1) | Pre-existing #3787/earlier UI, out of this diff | Not re-verified (out of scope for this diff) |
| Room frame chrome (title bar, Places bar, feed) | Pre-existing UI, out of this diff | Not re-verified (out of scope for this diff) |

Every element the demo draws that is **actually new in this diff** (the
banner and the Send-disable, on both triggers) is confirmed `MATCH` against
real rendered DOM output, captured as committed evidence files. Elements the
demo draws that are pre-existing chrome (mode button, portrait card, room
frame) were not independently re-verified visually this pass since they are
untouched by this diff and out of its scope - flagged as "not re-verified,"
not asserted as `MATCH`.

## Divergences the build got right (none found)

No intentional, ratified divergence from the demo was found in this diff. The
one structural choice that differs from a literal reading of the demo's
Screen 3 row ("Composer live-recheck effect") - implementing it as a
`useMemo` rather than a separate `useEffect` - is not a divergence from
approved behavior, just an implementation detail; the demo's own caption says
"one mechanism, two triggers," which the `useMemo`'s single dependency array
satisfies exactly.

## Mechanical companion (per `tools/agents/demo-fidelity-reviewer.md`)

Recommend a `tagReachability`-shaped rerender test, mirroring this review's
own throwaway harness, be added to `CommandInput.test.tsx`: mount once, then
`rerender()` from whisper→tt (not a fresh mount already in `tt`), and a second
`rerender()` that changes only `roomCharacters` (not `composerMode`), each
asserting the banner transitions from absent to present within the same
component instance. This is the one gap this review found between "the
mechanism is exercised" (true, confirmed live) and "a committed test exercises
it as a live transition rather than a static mount" (not yet true for either
trigger, only for trigger A's *outcome* via the mode-switch banner test that
mounts pre-switched). Not filed as a follow-up issue per "Fold In, Don't
File" - small enough to add in this PR or a fast-follow commit.

## Verdicts

| Criterion | Verdict |
|---|---|
| Screen 1 (whisper always reachable) | **PASS** |
| Screen 2, trigger A (mode-switch recheck fires live) | **PASS** |
| Screen 2, trigger B (mid-draft room-state recheck fires live) | **PASS** |
| Visual idiom reuse (class/role/aria parity with `reply-refusal`) | **PASS** |
| Refusal copy verbatim match to server strings | **PASS** |
| Screen 3 (fields/modules exist as described) | **PASS** |
| Scenario: actor's-own-place-changes trigger | **BLOCKED** - not rendered or independently tested this pass; mechanism should cover it by the same dependency array, but this review did not verify it live and declines to infer a pass |
| Full-stack live-visual pass (real browser, real viewport/theme, real WS→Redux→render path) | **BLOCKED** - no `Artifact` tool / authenticated session available to re-fetch the hosted demo pixel-for-pixel, and no Playwright e2e scenario exists or was built (would require new fixture scaffolding, per this review's own instructions not invented from scratch); RTL/jsdom DOM evidence was used instead and is disclosed as a substitute, not equivalent |

**Overall: PASS, with two disclosed BLOCKED items** (the actor's-own-place
edge case, and the absence of a true pixel/browser visual pass). Every
element the demo actually drew that is new in this PR's scope was rendered
for real and matches, on wording, structure, CSS-class parity, and live
trigger behavior for both of the demo's stated triggers. Nothing was reported
as passing from source-reading alone where a render was possible; where a
render was not possible (the hosted artifact itself; the actor's-own-place
scenario; a true browser paint), that is stated as BLOCKED rather than
inferred.
