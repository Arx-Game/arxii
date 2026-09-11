# #3759 demo-fidelity review

**Reviewer:** `demo-fidelity-reviewer` agent (vision-capable review of rendered
screenshots against the approved demo, same session).
**Reviewed commit:** `a5d1c9b422814763368dd752f3c44c210a1e70fd` (HEAD of
`feature-3759-narrative-play-reader-and-history-thread` at review time; branch
diverges from `origin/main` at `8a14fd9773a47fe599b0d51693bec1ecaf515ec9`).
**Date:** 2026-09-11.

## Approved-design reference

- Demo URL (from the issue body): `https://claude.ai/code/artifact/519a72ba-c685-405e-9b09-9107729184d9`.
  This session's tool set did not include an `Artifact` `read` action, so the
  demo was instead read from its own stated primary source: the **republished
  masthead copy already present in this session's scratch state**
  (`3759-demo.html`, byte-identical to `docs/design-proposals/narrative-play/arx-wide-reader.html`
  at commit `c183f4277` on `origin/codex/narrative-play-designs`, confirmed by
  `diff` against a fresh `git show c183f4277:...` extraction — see "How the
  demo was obtained" below). This is the same interactive demo fragment the
  issue links, with the scope-disambiguation table the issue's Walkthrough
  describes, not a different or lesser artifact.
- Companion written spec: `arx-play-specification.md` at the same commit
  (cited by section number in the issue body); read via `gh issue view 3759
  --json body`.
- Two of the demo commit's own **pre-rendered screenshots** (taken by the
  demo's own author against the *unmodified* interactive fragment) are
  committed alongside this report as the approved-design reference images:
  - `review-evidence/demo-reference-desktop.png` — Threads view, dark theme,
    "The broken seal" thread expanded.
  - `review-evidence/demo-reference-reference-mode.png` — reference mode
    (historical whisper), dark theme.

### How the demo was obtained

`git show c183f4277:docs/design-proposals/narrative-play/arx-wide-reader.html`
against `origin/codex/narrative-play-designs` returned the identical 75-line
fragment (byte-for-byte `diff`-clean) already present in this session's
scratch directory as the republished masthead page's embedded copy. The
republished masthead page itself carries the scope table the issue's
Walkthrough describes ("Its own masthead has a scope table disambiguating
what #3759 owns versus sibling issues") and states explicitly: *"the framed
demo's markup, styles and script are unchanged from the approved commit."*
Both the raw fragment and the republished masthead were read in full (not
just the head) before this review began. The scope table's ownership rows are
quoted inline below wherever they gate a finding.

## Build under review, and how it was rendered

**This is a real-browser render of the actual production React components,
not a template read and not a mockup.** Playwright (chromium, `@playwright/test`
1.58.2) drove a Vite dev server (`pnpm exec vite`, port 5183) serving this
worktree's unmodified `frontend/src/game/components/{ThreadedNarrativeReader,
PlaySidebar,HistoryNavigator,GameWindow,GameLayout}.tsx` and their full import
tree (`PoseUnit`, `SceneMessages`, `ReactionStrip`, `PersonaAvatar`, real
Tailwind/shadcn CSS via `frontend/src/index.css`) exactly as `/game` imports
them — no component was reimplemented, stubbed, or hand-copied for this
review.

- **Environment:** worktree `feature-3759-narrative-play-reader-and-history-thread`
  at the commit above; Node v24.4.1; `pnpm exec vite` dev server (not the
  production build/preview — chosen so a throwaway harness entry could be
  served without touching the app's real `main.tsx`/`App.tsx`/routes).
- **Viewport:** 1440x900 (desktop), the viewport both the demo's own
  `arx-wide-reader-desktop.png` reference and its README's own validation
  matrix use as the primary desktop size.
- **Theme:** **light only.** The harness mounted the real components but did
  **not** wire `next-themes`' `ThemeProvider` (the harness intentionally kept
  provider surface area minimal), so no `.dark` class was ever applied.
  **Dark-theme fidelity of #3759's own components was NOT verified in this
  review — see the BLOCKED verdict below; this is not inferred as a pass.**
  Narrow/mobile viewports were likewise not exercised (see "Scope
  boundary" below).

### Fixture-vs-live boundary (read this before trusting any screenshot)

**No live Django backend was used.** `window.fetch` was monkey-patched before
React mounted to intercept every `apiFetch()` call
(`/api/roster/entries/mine/`, `/api/play/conversations/`, `/api/play/search/`,
`/api/play/context/`, `/api/play/read/`, `/api/backgrounds/`, catch-all) and
return canned, hand-built JSON shaped to match `playTypes.ts`'s real
interfaces (`ConversationSummary`, `PlaySearchResult`, `ThreadSummary`,
`Interaction`). A real Redux store (`store.ts`'s actual `gameSlice` reducer)
was preloaded with one active session via the slice's own `startSession`/
`setActiveSession`/`setSessionScene` actions — not a hand-rolled fake state
shape. The `interactions` fixture reuses the demo's own author names
("Mirelle, Silas, Aureth, Sabella, Rook") and passage text verbatim, scaled
down from the demo's 500 poses / 20 threads / one 250-reply thread to **~154
poses across 20 `thread_id`-grouped threads, with one 40-pose thread** as a
practical substitution for the full production scale (no live backend to seed
real 500-pose history against). This reduction is large enough that one
scale-dependent claim below (**F1**) is called out explicitly as reproduced
from source code, not inferred from the fixture's shape alone.

The harness source (`frontend/src/reviewHarnessMain.tsx`), its Vite HTML entry
(`frontend/review-harness.html`), a throwaway Playwright config
(`frontend/playwright.harness.config.ts`), and the capture spec
(`frontend/e2e/_review-harness.spec.ts`) were **deleted after the screenshots
were captured** — they are not part of this commit; only this report and the
`review-evidence/` images are. `git status --short` was re-checked after
deletion to confirm only `docs/design-proposals/` remains untracked.

### Tested interactions

- Threads view: default render; clicked a thread header to collapse it;
  clicked "Load earlier history" twice (confirmed additional thread groups
  become reachable — see F1).
- Chronological toggle: clicked "Chronological", screenshotted, clicked
  "Threads" to return.
- History tab: clicked the sidebar's History nav button; screenshotted the
  browse-only state; typed `seal` into the search field and submitted;
  screenshotted the result.
- Reference mode: clicked a real rendered search-result row (not a harness
  shortcut) to invoke the production `onOpenReference` callback exactly as
  `HistoryNavigator.tsx` wires it; screenshotted. Clicked "Return to live";
  confirmed the live Threads view and the History sidebar's search state both
  survived the round trip (Decision #4/#5).

### Screenshot paths (committed)

All under `docs/design-proposals/narrative-play/review-evidence/`:
`01-threads-view.png`, `02-threads-view-toggled.png`,
`03-chronological-view.png`, `04-history-tab-browse.png`,
`05-history-tab-search-results.png`, `06-reference-mode.png`,
`07-returned-to-live.png`, `08-after-load-earlier.png` (built), plus
`demo-reference-desktop.png`, `demo-reference-reference-mode.png` (approved
design, from the demo commit itself).

## Scope boundary (per the demo's own scope table)

Per the republished demo's "What on this page is #3759's responsibility"
table, this review compares **only** the rows marked `#3759` against the
build: thread list collapse/expand + "Collapse loaded"/"Latest activity",
pose fold, load earlier/later replies within a thread, History tab
search/browse, and the reference-mode reader + Return to live. Rows marked
`#3758` (Here tab, Conversations tab, sidebar placement/prose controls, the
scene-title header/breadcrumb, `GameLayout` itself), `#3760` (composer bar,
reply-to parent chip, the draft-preserved tray's *content*), and `#3761`
(OOC channel rows) are **not** scored here even though the harness had to
render *something* in their place to produce a complete page (labeled
inline in the screenshots as "harness stand-in").

---

## Screen 1: Threads view (main reader) — collapse/expand, pose fold, load earlier/later replies

**Demo shows** (`demo-reference-desktop.png`; fragment `renderReader()`,
lines ~41 of the demo HTML): every thread's header always visible in one
oldest-roots-first list — root author, pose count, and a ~84-character
excerpt of the opening pose ("Rook · 250 poses · 'There is a difference
between knowing a thing and being able to prove it.' Silas dr…"); an unread
badge when present; a top toolbar reading "Threads · oldest roots first" with
**"Collapse loaded"** and **"Latest activity"** buttons; each open thread
shows, **inside itself**, "Load earlier replies · N before this page" above
its visible poses and "Load later replies" below when more exist; each pose's
header shows author, a clock time, and **"Opening pose" / "Reply in `<thread
title>`"**.

**Build renders** (`01-threads-view.png`, `02-threads-view-toggled.png`,
`08-after-load-earlier.png`): only **one** thread group ("Rook", 20 poses, "3
new" badge) is visible on first render, because `historyStart` slices the
**flat, ungrouped** `interactions` array to its last 20 items by array
position *before* grouping by `thread_id`
(`ThreadedNarrativeReader.tsx:269-270`) — any thread whose most recent pose
falls outside that tail window renders nothing at all, not even a collapsed
header row. Clicking "Load earlier history" twice does surface more thread
groups (4 after two clicks — confirmed programmatically), so the content is
reachable, just not up-front the way the demo shows it. The toolbar reads "1
conversation" / **"Expand loaded threads" / "Collapse loaded threads" /
"Mark conversation read" / "Chronological"** (`ThreadedNarrativeReader.tsx:800-829`)
— no "Latest activity" equivalent exists anywhere in the component (`grep`
for "Latest activity" in the file returns nothing). The one visible thread
header shows only the root author's name, pose count, and unread badge — no
excerpt text, no timestamp (`ThreadedNarrativeReader.tsx:963-969`). No
per-thread "Load earlier/later replies" control exists at all — the only
paging affordances are a whole-list "Load earlier history" / "Jump to latest"
pair at the very bottom of the page (`ThreadedNarrativeReader.tsx:1043-1076`).
Each pose (via `PoseUnit.tsx:364-380`) shows avatar, name, and a real
locale-formatted timestamp — no "Opening pose"/"Reply in `<title>`" label
anywhere in the frontend tree (`grep -rn "Reply in " frontend/src` returns no
matches).

### Findings

- **F1 (thread-list windowing hides most threads by default) — DEFECT,
  moderate.** Demo: all threads always listed, oldest-first, collapsed by
  default except the most recent. Build: only threads with a pose in the
  last-20-by-array-position slice appear at all; the rest are invisible
  until "Load earlier history" is clicked repeatedly. This is a structural
  gap, not a fixture artifact — confirmed directly from source
  (`historyStart = interactions.length - INITIAL_PAGE_SIZE`,
  `ThreadedNarrativeReader.tsx:269`) independent of the screenshot. It also
  means the anti-reinvention ledger's own "`PlayThreadsView`... ABSENT...
  groups client-side over the already-fetched `interactions` array only"
  finding is **still true of the reader component** even though
  `PlayThreadsView`/`fetchPlayThreads` were built server-side in this branch
  (`play_views.py:404`, `playQueries.ts:40-49`) — the reader's `groups`
  `useMemo` (`ThreadedNarrativeReader.tsx:271-295`) never calls
  `fetchPlayThreads`; it still groups the flat `interactions` prop. Propose
  as the mechanical companion: a Vitest assertion that, given N threads each
  with exactly one pose spread evenly across a synthetic long timeline, all N
  thread headers render on first mount (no "Load earlier" click required) —
  this fails today and would have caught F1 mechanically.
- **F2 (no per-thread load earlier/later replies) — DEFECT, moderate.** This
  is an explicitly `#3759`-owned demo row ("Load earlier/later replies within
  a thread"). The build has no equivalent; only whole-list pagination exists.
- **F3 (thread header excerpt/timestamp copy dropped) — DEFECT, low.**
  Approved copy (the opening-pose excerpt, the per-thread timestamp) is
  simply not rendered.
- **F4 (pose "Opening pose"/"Reply in `<title>`" label dropped) — DEFECT,
  low.** The spec's own anti-reinvention ledger treats this label as the
  intentionally-flat (non-chip) presentation of thread context that #3759
  should **keep**, not replace with per-pose parent persistence — but the
  build has no such label at all, not even the flat text form.
- **F5 ("Latest activity" affordance absent) — DEFECT, low.** No equivalent
  jump-to-most-recently-active-thread control exists; the bottom-of-list
  "Jump to latest" is a different, coarser mechanism (global array tail, not
  a specific thread).

Collapse/expand itself (F-none): **MATCH** — clicking a thread header
correctly collapses it to a single summary row with a "›" chevron, matching
the demo's collapse behavior (compare `01-threads-view.png` vs
`02-threads-view-toggled.png`). Pose fold ("Show less"/"Show full pose"):
**MATCH** — present and functional, matching the demo's per-pose fold.

### Visual checklist (Threads view, against `demo-reference-desktop.png`)

| Element in the demo | Verdict | Note |
|---|---|---|
| Brand header ("Arx II · The world, in your words") | N/A | #3758 shell scope, not scored |
| Scene breadcrumb + title + meta ("THE LOWER BOROUGHS · SILAS" / "The last light at the Gilded Hart" / "Room conversation · N poses · N threads") | N/A | #3758 shell scope |
| Toolbar: "Threads · oldest roots first" label | GAP | build shows "N conversation(s)" instead |
| Toolbar: "Collapse loaded" button | MATCH | present as "Collapse loaded threads" |
| Toolbar: "Latest activity" button | GAP | F5, absent |
| Toolbar: "Expand loaded"/equivalent | MATCH | build adds "Expand loaded threads" (demo has no direct equivalent but this is additive, not a loss) |
| All thread headers visible, oldest-first, collapsed by default | GAP | F1 |
| Thread header: root author · pose count · excerpt | GAP | F3 — excerpt missing |
| Thread header: unread badge | MATCH | "3 new" badge renders |
| Per-thread "Load earlier replies · N before this page" | GAP | F2, absent |
| Per-thread "Load later replies" | GAP | F2, absent |
| Pose header: author · time · "Opening pose"/"Reply in `<title>`" | GAP | F4 — role label missing (avatar/name/time present) |
| Pose body paragraphs | MATCH | renders correctly |
| Pose footer: "Show less"/"Show full pose" fold | MATCH | present, functional |
| Pose footer: "Reply" button | N/A | #3760 scope (composer/draft lifecycle); reader only renders the affordance if present — present via `onReply`, not screenshotted separately here |
| Composer bar (persona/mode/audience, Send) | N/A | #3760 scope |

**Screen verdict: MATCHES WITH SIGNIFICANT NOTED GAPS.** Collapse/expand and
pose-fold are correct. The default thread-list visibility (F1), per-thread
reply paging (F2), thread-header excerpt copy (F3), pose role label (F4), and
"Latest activity" (F5) are real, reproducible gaps against rows the demo's
own scope table assigns to #3759.

---

## Screen 2: Chronological reading mode

**Demo shows:** nothing — the scope table marks this row
`textonly`: *"Spec §5: the prototype only demonstrates Threads; Chronological
is written-spec behavior to build."* There is no demo image to compare pixel
composition against; the written spec (§5, "an explicit reading preference
... shares content and read state ... but keeps its own anchor") is the only
approved reference for this screen.

**Build renders** (`03-chronological-view.png`): a flat, time-ordered list;
each pose prefixed with "In a thread" / "Standalone"; same toolbar row (now
showing a "Threads" button in place of "Chronological"); "Load earlier
history" still present at the bottom. Toggling between the two views
(`02-threads-view-toggled.png` → `03-chronological-view.png` → back)
preserved read/collapse state per Decision #2 ("shares content and read state
with Threads").

### Visual checklist

Since the demo shows no image for this screen, the checklist is against the
written spec's §5 requirements only:

| Requirement (§5) | Verdict |
|---|---|
| Explicit toggle, not default | MATCH — "Chronological"/"Threads" toggle button |
| Flat, single timeline | MATCH |
| Shares content/read state with Threads | MATCH (collapse-all state carried across the toggle in testing) |
| Own anchor (independent of Threads' anchor) | **NOT VISUALLY VERIFIABLE** — anchor persistence is a scroll-restore behavior, not a static visual; out of this screenshot-based review's reach (would need a scroll-then-toggle-then-reload sequence with real measured layout, which jsdom-free but still harness-fixture rendering could partially exercise, not attempted here for time) |

**Screen verdict: BLOCKED on full requirement coverage, PASS on everything
visually checkable.** There is no approved-design image for this screen (by
the demo's own admission), so no MATCH/GAP call can be made against a visual
reference — only against written-spec text, which this report is not
authorized to treat as a substitute "approved design" beyond the literal
requirements it states. What was checked (toggle presence, flat layout,
shared state) is correct.

---

## Screen 3: History tab — search, date range, results

**Demo shows** (fragment `renderSide()` history branch): "Find a
conversation" heading, a labeled search input ("Search retained history",
placeholder "Try seal or Aldren"), a note ("Sample history · includes earlier
than 90 days"), and result rows (title, date, matching excerpt).

**Build renders** (`04-history-tab-browse.png`, `05-history-tab-search-results.png`):
"History" heading with a clock icon, descriptive copy ("Find authorized
scenes, whispers, and communications"), a search input + submit button, From/To
date pickers, a **Type** selector (All accessible / Scenes / Whispers) — this
is new relative to the demo and matches the scope table's `#3759` row +
spec's "kind... filters" requirement — a "Show all my accessible history"
toggle, and a "RECENT CONVERSATIONS" section with result rows. Typing `seal`
and submitting correctly surfaced the one matching fixture row ("Whisper -
Mirelle and Silas") with an excerpt, matching the demo's own "Try seal or
Aldren" example almost verbatim in content (fixture reused the demo's own
whisper text).

### Visual checklist

| Element in the demo | Verdict | Note |
|---|---|---|
| "Find a conversation" heading | MATCH | build: "History" + descriptive copy (richer, not a loss) |
| Search input, labeled | MATCH | `#history-search`, `sr-only` label present |
| "Sample history · includes earlier than 90 days" note | GAP | no equivalent 90-day default note shown to the user (the 90-day default exists functionally per `ninetyDaysAgo`, Decision #4, but is not surfaced as copy) |
| Date range | MATCH | build adds explicit From/To pickers (demo shows only the note, no pickers) — additive |
| Type/kind filter | MATCH | build adds this; explicitly required by spec §4, absent from the (intentionally simplified) demo |
| Result rows: title, date, excerpt | MATCH | title + excerpt match; build shows "Retained"/unread count instead of a raw date on browse rows (functionally equivalent, cosmetically different) |
| "No matching retained conversations" empty state | **NOT EXERCISED** | not tested in this pass |

**Screen verdict: MATCHES, with one minor copy gap (90-day note not
surfaced) and several legitimate, spec-required additions (Type filter, date
pickers) beyond the intentionally-simplified demo.**

---

## Screen 4: Reference mode — "Reading history" strip, read-only reader, Return to live

**Demo shows** (`demo-reference-reference-mode.png`): the scene heading
itself swaps to the reference's own title/date ("Whisper · Mirelle and
Silas" / "18 May · previous scene"); an amber "Reading history · read-only"
strip with a "Return to live" button; **no toolbar at all**
(`q('[data-toolbar]').hidden=!!h` in the fragment); a **flat**, chrome-free
list of the referenced poses (author name + paragraph, no thread grouping, no
fold controls, no reply buttons); a bottom tray reading "Draft preserved for
**Room** · 69 characters".

**Build renders** (`06-reference-mode.png`): an amber "Reading history ·
Whisper - Mirelle and Silas" strip with "Return to live" — **MATCH** on this
specific element, including the same conversation title text. Below it,
however, the reader still renders the **full interactive Threads-view
chrome**: the same toolbar row ("Expand loaded threads / Collapse loaded
threads / **Mark conversation read** / Chronological") and the same
thread-group wrapper (a "Mirelle" header with a collapse chevron and "3
poses" count) around the three referenced poses, each still carrying its own
"Show less" fold control. The bottom tray reads a generic "Draft preserved
for your live conversation" (no destination name, no character count — the
scope table attributes the tray's *content* to #3760, so this specific text
difference is not scored against #3759).

### Findings

- **F6 (reference mode is not chrome-free / read-only-presented) — finding
  requiring disposition, moderate.** The pose *content* itself is correctly
  read-only (no Reply buttons render — `onReply` is `undefined` in reference
  mode per `GameWindow.tsx:425-429`'s prop wiring), and Return to live works
  correctly (see Screen 5). But the **toolbar's "Mark conversation read"
  button is not gated by `readOnly` anywhere in
  `ThreadedNarrativeReader.tsx`** (confirmed by direct inspection — no
  `readOnly` check wraps the toolbar JSX at lines 800-829) and remains live
  and clickable while browsing historical content, which would fire a real
  `POST /api/play/read/` mutation from inside what Decision #5 calls "read
  only" mode. The demo avoids this entirely by hiding its whole toolbar in
  reference mode. This is not automatically a defect — the spec's own text
  says "The written specification takes precedence wherever the prototype
  simplifies behavior," and nothing in the written spec explicitly forbids a
  richer read-only chrome — but a live *mutating* control surviving into a
  mode the spec itself calls read-only is exactly the kind of question this
  review exists to surface for a human call, not resolve unilaterally.
  Propose as the mechanical companion: a Vitest assertion that no element
  with a `POST`-triggering `onClick` (specifically `handleMarkConversationRead`)
  is reachable via `getByRole('button')` when `readOnly` is `true`.

### Visual checklist

| Element in the demo | Verdict | Note |
|---|---|---|
| Scene heading swaps to reference title/date | N/A | scene heading region is #3758 shell scope; the amber strip (which IS #3759's) carries the title correctly |
| "Reading history · read-only" strip | MATCH | build: "Reading history · `<title>`" (drops the literal word "read-only" from the strip text, but the state itself is read-only) |
| "Return to live" button | MATCH | present, functional (see Screen 5) |
| No toolbar visible | **DIVERGE** | F6 — build's full toolbar (including a live "Mark conversation read" mutation) still renders |
| Flat, chrome-free pose list (no thread grouping, no fold) | **DIVERGE** | F6 — build reuses the grouped/foldable Threads-view presentation |
| Draft-preserved tray with destination + char count | N/A | #3760 scope (tray content); build shows a generic message instead |

**Screen verdict: MATCHES on the core "Reading history" strip / Return-to-live
mechanics (both #3759's mandate), DIVERGES on presentation chrome (F6) in a
way that also touches a stated read-only decision and needs a human
disposition rather than an assumed pass.**

---

## Screen 5: Return to live (round-trip correctness)

**Demo shows:** the reader restores the prior live scroll anchor (not a jump
to latest), per Decision #5.

**Build renders** (`07-returned-to-live.png`): returning from reference mode
correctly restored the live Threads view (the "Rook" thread, still
collapsed exactly as it was left before opening the reference) **and** the
History sidebar's own search state (`seal` query, results still shown) was
preserved across the round trip — both match Decision #4 ("each [sidebar
mode] owns a remembered scroll position") and Decision #5 ("Return to live
restores the prior live anchor"). Pixel-level scroll-offset parity (vs. a
raw jump) was not independently measured (both states were scrolled to the
top of a short fixture), so this is a structural, not pixel-precise,
confirmation.

**Screen verdict: MATCH** on everything checkable at this fixture's scale.

---

## Verdict summary

| Screen | Verdict |
|---|---|
| 1. Threads view (reader) | MATCHES WITH SIGNIFICANT NOTED GAPS — F1 (default thread-list windowing), F2 (no per-thread load earlier/later), F3 (thread header excerpt dropped), F4 (pose role label dropped), F5 ("Latest activity" absent) |
| 2. Chronological view | BLOCKED on full requirement coverage (no demo image exists for this screen, by the demo's own scope table); PASS on everything checkable against the written spec |
| 3. History tab (search/browse) | MATCHES, one minor copy gap (90-day note), several legitimate spec-required additions |
| 4. Reference mode | MATCHES on strip/Return-to-live mechanics; DIVERGES on chrome (F6, needs human disposition — a live mutating control in a stated read-only mode) |
| 5. Return to live (round trip) | MATCH |
| Dark theme | **BLOCKED — not verified in this pass** (harness did not wire `next-themes`; do not infer a pass) |
| Narrow/mobile viewport | **NOT TESTED** — `GameLayout`'s resize/pane-toggle behavior is #3758's scope per the spec's Design section; 1440x900 desktop only was exercised here |
| CSS/styling reaches the page (Finding-1-shaped check) | PASS — every screenshot shows fully-styled Tailwind/shadcn output (avatars, borders, spacing, badges); no admin.css-style "class present, no rule reaches" defect found |

## Mandatory-criterion PASS/FAIL/BLOCKED

| Criterion | Verdict |
|---|---|
| Thread collapse/expand | PASS |
| Pose fold/expand | PASS |
| Chronological mode exists, explicit toggle, shares state | PASS |
| Load earlier/later replies **within a thread** | **FAIL** (F2 — absent) |
| All threads visible/orderable by default (not hidden behind pagination) | **FAIL** (F1) |
| History search + date range + results | PASS |
| History kind/participant filters (spec §4) | PASS |
| Reference mode: reading-history strip + Return to live | PASS |
| Reference mode: read-only presentation (Decision #5) | **FAIL on chrome purity** (F6 — pose content is read-only; toolbar including a mutating control is not) |
| Return-to-live restores prior live anchor + sidebar state | PASS |
| Dark theme parity | **BLOCKED — not verified** |
| Styling actually reaches the rendered page | PASS |

## Unresolved findings requiring a human call

1. **F1** — thread-list default visibility windowing (moderate, code-confirmed independent of fixture scale).
2. **F2** — no per-thread load earlier/later replies (moderate, explicitly #3759-owned demo row).
3. **F6** — reference mode's toolbar (incl. a live "Mark conversation read" write) is not suppressed, unlike the demo's chrome-free read-only presentation (moderate, touches Decision #5).
4. **F3/F4/F5** — dropped copy/affordances (low severity each, but real, reproducible, and against explicitly `#3759`-scoped demo rows).
5. **Dark theme** — genuinely unverified, not a claimed pass.

---

## Wave 9 remediation -- follow-up verification (2026-09-11)

**Reviewer:** `demo-fidelity-reviewer` agent (real-browser Playwright render,
same session, same methodology as the original review above).
**Reviewed commit:** `dcbdae37527d0af160fb5740934bc8ad149512a4` (HEAD of
`feature-3759-narrative-play-reader-and-history-thread` at follow-up review
time; branch diverges from `origin/main` at
`c2c7c7a9e217dc7cb3ac3e3d2906ce5da5c1e4c7`). This commit is the tip of the
Wave 9 remediation series (`a8b9a9238`..`dcbdae375`) that claims to fix F1-F6
from the original review above, reviewed twice by independent adversarial
reviewers against source behavior only (never rendered).

**Purpose:** confirm the Wave 9 fixes actually render correctly in a real
browser -- source-code/unit-test confirmation is not a visual review (see the
top-level instructions this report answers to). This section does **not**
repeat or overwrite the six original findings above; it re-renders the
specific screens those findings named and records what the browser now
shows.

### Environment (unchanged from the original review)

- **Worktree:** `feature-3759-narrative-play-reader-and-history-thread`,
  anchored via `cd` + `pwd` + `git status --short` before any work (tree was
  clean at both the start and end of this follow-up).
- **Viewport:** 1440x900 desktop (same as the original review and the
  demo's own reference screenshots).
- **Theme:** light only -- same limitation as the original review; **dark
  theme remains BLOCKED/unverified**, not re-checked here, not inferred as a
  pass.
- **Render method:** Playwright (chromium) driving a real `pnpm exec vite`
  dev server (port 5183), mounting the REAL production components exactly as
  `/game` imports them -- `GameLayout`, `GameWindow`, `PlaySidebar`,
  `HistoryNavigator`, `ThreadedNarrativeReader`, and their full import tree
  (`PoseUnit`, `SceneMessages`, real Tailwind/shadcn CSS via
  `frontend/src/index.css`) -- with a real Redux store (`store/store.ts`'s
  actual `gameSlice`/`authSlice` reducers, seeded via `setAccount`/
  `startSession`/`setActiveSession`/`setSessionScene`) and a real
  `QueryClientProvider`. No component was reimplemented or stubbed. Unlike
  the original review, this harness mounted `GameLayout`/`GameWindow`/
  `PlaySidebar` directly (the same components `GamePage.tsx` composes)
  rather than the full `GamePage.tsx` composition root -- `GamePage.tsx`
  itself pulls in combat/battle/dream/journal/inventory/travel/mission/
  ceremony/event sidebar panels unrelated to this follow-up's scope, and the
  five components above are the same ones the original review's own stated
  import-tree scope named.

### Fixture-vs-live boundary

**No live Django backend.** `window.fetch` was monkey-patched before React
mounted, intercepting `/api/interactions/`, `/api/play/conversations/`,
`/api/play/search/`, `/api/play/context/`, `/api/play/poses/`,
`/api/play/read/`, `/api/backgrounds/`, `/api/roster/entries/mine/`, and a
catch-all (returns `[]`) for every other endpoint the full component tree
probes (reaction-emoji catalog, nominations, etc.) -- same pattern as the
original review, same reasoning (no live backend to seed real history
against). The fixture is hand-built, purpose-designed for this follow-up
(not reused verbatim from the original review's fixture), reusing the same
demo-approved character names (Mirelle, Silas, Aureth, Sabella, Rook):

- **Live scene feed** (`scene:700`): 4 real `thread_id`-bearing threads
  spread across a 21-day timeline -- `thread-alpha` (3 poses, oldest),
  `thread-beta` (6 poses), `thread-gamma` (4 poses, **root pose deliberately
  seeded with MU\* color codes and markdown** -- `|wMirelle turned
  sharply.|n **The broken seal** on the door cracked...` -- to drive the I-1
  markup-stripping check), `thread-delta` (28 poses, the last and thus most
  recently active thread, deliberately sized past `THREAD_PAGE_SIZE=20` to
  exercise "Load earlier replies") -- plus 4 standalone (`thread_id: null`)
  legacy poses interspersed between and after the threads.
- **Retained whisper conversation** (`whisper:9001`, 3 poses): reachable via
  a real `HistoryNavigator` search for "seal" and via the browse list, both
  wired through the real `fetchPlaySearch`/`fetchPlayConversations`/
  `fetchPlayContext` functions (not reimplemented) against the mocked fetch
  -- used to drive reference mode via an actual rendered search-result click,
  exactly as the original review's methodology required.

### Tested interactions

- Threads view default render (no clicks) -- full-page screenshot.
- Clicked "Latest activity" -- confirmed it expands/scrolls to `thread-delta`
  (the most recently active real thread).
- Clicked `thread-delta`'s own "Load earlier replies · 8 before this page"
  button -- confirmed the button disappears and all 28 rounds (1-28) become
  visible, i.e. the widen actually works, not just that the control renders.
- Expanded `thread-gamma` (the markup-seeded thread) by clicking its header
  -- read the header excerpt and every pose's role-label text via
  `innerText`/`allInnerTexts` and asserted none contain `|w`, `|n`, or `**`.
- Navigated to History tab, searched "seal", clicked the real rendered
  search-result row (not a harness shortcut) to invoke `onOpenReference`
  exactly as `HistoryNavigator.tsx` wires it -- confirmed the "Reading
  history" strip appears and asserted (`toHaveCount(0)`, not just visual
  absence) that no "Mark conversation read" button exists anywhere on the
  page in that state.

### Screenshot paths (committed)

All under `docs/design-proposals/narrative-play/review-evidence/`:
`09-wave9-threads-view.png` (default render), `10-wave9-latest-activity.png`
(after clicking Latest activity), `11-wave9-load-earlier-replies.png` (after
clicking Load earlier replies on thread-delta), `12-wave9-thread-gamma-
expanded.png` (markup-seeded thread expanded), `13-wave9-legacy-pose-
plain.png` (same scroll state, confirming the trailing legacy pose), `14-
wave9-reference-mode-toolbar-check.png` (reference mode via a real search
result click).

### Findings, per item

**1. Multiple thread headers visible on first render, collapsed by default
except the most recent -- F1.**
`09-wave9-threads-view.png` shows all 4 real thread headers
(`Silas · 3 poses`, `Sabella · 6 poses`, `Mirelle · 4 poses` [thread-gamma],
`Mirelle · 28 poses` [thread-delta]) present on first render, in
oldest-roots-first order, with only `thread-delta` (the most recently
active) expanded -- the other three show a `›` chevron and no visible poses.
Programmatically confirmed too: `section[data-thread-id]` count is 4 on
first render (no "Load earlier history" click needed), matching the fixture's
4 real threads exactly.
**Verdict: PASS.**

**2. An expanded thread with many poses shows a bounded default window with
a working "Load earlier replies" control -- F2.**
`09-wave9-threads-view.png` / `10-wave9-latest-activity.png` show
`thread-delta` (28 poses) expanded with a bounded window (rounds 9-28, 20
poses -- `THREAD_PAGE_SIZE`) and a "Load earlier replies · 8 before this
page" button above them. Clicking it (`11-wave9-load-earlier-replies.png`)
removes the button and reveals rounds 1-8 ("Opening pose" through "Reply in
Round 1..." for round 8) -- the control is not just present, it actually
works.
**Verdict: PASS.**

**3. Thread headers show an excerpt + timestamp -- F3.**
Every collapsed header in `09-wave9-threads-view.png` shows an opening-pose
excerpt and a locale timestamp, e.g. `Silas leaned against the doorframe,
watching the rain streak the glass. · 8/1/2026, 12:00:00 PM`.
**Verdict: PASS.**

**4. Poses show "Opening pose"/"Reply in `<title>`"/"Standalone" role
labels, and the label text is plain (markup-stripped) -- F4 + I-1.**
`12-wave9-thread-gamma-expanded.png` shows `thread-gamma`'s header excerpt
as `Mirelle turned sharply. The broken seal on the door cracked and hissed a
thin trail… · 8/11/2026, 12:00:00 PM` -- the root pose's `|w`/`|n` color codes
and `**bold**` markdown are gone from the plain-text excerpt, even though
the pose's own rendered BODY correctly still shows "The broken seal" in
**bold** (the markup renders normally in the actual message body via
`FormattedContent`; only the plain-text excerpt/label strip it, which is the
correct, narrower fix). The role labels read "Opening pose" for the root
pose and "Reply in Mirelle turned sharply. The broken seal on the door
cracked…" for its three replies. Programmatic assertion (`not.toMatch(/\|w
|\|n|\*\*/)` over every label in the thread, plus the header excerpt)
passed.
**Verdict: PASS.**

**5. A "Latest activity" button exists and expands/scrolls to the
most-recently-active real thread -- F5.**
The button is visible in the toolbar in every Threads-view screenshot.
Clicking it (before `10-wave9-latest-activity.png`) was asserted
programmatically to leave `thread-delta`'s `section` visible with
`aria-expanded="true"`, then `scrollIntoView`'d it. (`thread-delta` was
already the default-expanded thread, since it's genuinely the most recent --
this fixture couldn't visually distinguish "jumped to" from "already there"
in a static screenshot; the programmatic assertion is the load-bearing check
here, not the screenshot alone.)
**Verdict: PASS.**

**6. In reference mode, "Mark conversation read" is not present in the
toolbar at all -- F6.**
`14-wave9-reference-mode-toolbar-check.png` shows the amber "Reading history
· Whisper - Mirelle and Silas · read-only" strip and "Return to live", and
**no toolbar row of Expand/Collapse/Mark-read buttons at all** -- only "0
conversations" and a bare "Chronological" toggle (the whisper fixture is 3
un-replied/legacy poses, so `realThreadGroups.length === 0`, which correctly
gates out the whole Expand/Collapse/Latest-activity/Mark-read button group,
not just Mark-read specifically). Programmatic assertion
(`getByRole('button', { name: 'Mark conversation read' })` →
`toHaveCount(0)`) passed -- the control isn't hidden by CSS, it isn't in the
DOM.
**Verdict: PASS.**

**7. A single-pose (un-replied) pose renders without a collapsible card
wrapper.**
Every legacy pose in `09-wave9-threads-view.png` (Aureth, Rook, Sabella,
and the trailing Rook pose after `thread-delta`) renders as a plain
"Standalone"-labeled block with no header row, no chevron, and no
`aria-expanded` control -- sitting directly among the thread cards, not
visually distinguished by a border/card treatment the way real threads are.
Programmatically confirmed: the first legacy row's `section` and
`[aria-expanded]` descendant counts are both 0.
**Verdict: PASS.**

### Verdict summary (Wave 9 follow-up)

| # | Item | Verdict |
|---|---|---|
| 1 | Multiple thread headers visible by default, collapsed except most recent (F1) | **PASS** |
| 2 | Bounded default window + working per-thread "Load earlier replies" (F2) | **PASS** |
| 3 | Thread header excerpt + timestamp (F3) | **PASS** |
| 4 | Pose role label present AND markup-stripped (F4 + I-1) | **PASS** |
| 5 | "Latest activity" button exists and works (F5) | **PASS** |
| 6 | "Mark conversation read" absent (not just disabled) in reference mode (F6) | **PASS** |
| 7 | Single un-replied pose renders without a card wrapper | **PASS** |
| Dark theme | Not re-checked this pass | **BLOCKED -- still unverified, not inferred as a pass** |

**All 6 original findings (F1-F6) are confirmed fixed by real-browser
render, not just by source inspection or the two prior adversarial
source-only reviews.** No new visual defect was found in the surfaces this
follow-up specifically re-checked. Dark-theme parity remains the one
standing BLOCKED item from the original review -- this follow-up did not
re-verify it and does not claim to.

### Mechanical companions (proposed, per the shape of what was checked)

- A Vitest test asserting that, given N threads each with exactly one pose
  spread evenly across a synthetic long timeline (the original review's own
  F1 proposal), all N thread headers render on first mount with no "Load
  earlier" click required -- would catch a regression of F1 mechanically.
- A Vitest test seeding a pose's content with `|w`/`|n`/`**` markup and
  asserting the thread-header excerpt and every role-label `<p>` text never
  contains those literal substrings -- would catch a regression of I-1
  mechanically (this follow-up's browser-level assertion is the same check,
  just not yet ported into the unit suite).
- The Vitest assertion for F6 (`getByRole('button', { name: /mark
  conversation read/i })` absent when `readOnly` is `true`) already exists
  -- `ThreadedNarrativeReader.test.tsx:1971`, "never renders 'Mark
  conversation read' while reading a historical reference (#3759 review
  finding F6)" -- confirmed present, not proposed here; this follow-up's
  browser-level assertion is the same check at the render layer, not a
  substitute for it.
