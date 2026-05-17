# Stories Authoring API + Minimal Functional UI — Design

**Date:** 2026-05-16
**Status:** Validated design, ready for implementation planning
**Topic:** The next step after the authoring backbone — make it usable: full-stack authoring + run-control UI, GM/player text split, dashboard query cleanup
**Relates to:** `docs/plans/2026-05-15-stories-authoring-framework-design.md` (backbone; this realizes its deferred follow-ups I-1/I-2 + recorded follow-ups #2/#3), `docs/systems/stories.md`, `src/world/stories/CLAUDE.md` (3-layer pattern)
**Branch:** new branch off fresh `origin/main` (backbone merged as `#446` / `671ed42b`)

---

## 1. Why this exists

The authoring backbone (`#446`) shipped a correct runtime engine + seams but is only
runnable at the service/test layer — there is no product surface to author or run a
story (follow-up **I-1**), no clean GM-vs-player text boundary (**I-2**), and the
`GMQueueView`/`StaffWorkloadView` carry a queries-in-loop debt (follow-ups **#2/#3**,
senior-dev-corroborated). This step makes the backbone **usable end to end through the
browser** and pays down the view query debt while we are in those files anyway.

**Success criterion:** logged in as a staffer/GM persona, in the browser: open the
Story section → list/open/create stories → author name + GM pitch + player recap →
add Chapters → Episodes → Beats → assign a PC/covenant → promote Pitch→Outline→Plot
→ resolve episodes / mark beats → watch the story land in WAITING_FOR_GM / RESTING —
including making **on-the-fly structural edits mid-session** (new beats, new branches)
as players go sideways. Minimal *functional* UI (not visually polished).

**Approach (chosen: B).** Minimal CRUD authoring page whose edit flow is tuned for
in-session speed (one-click add-beat / add-branch from the current node, inline forms,
current-progress state shown inline for context). Edits persist via the standard
3-layer API; the runtime picks them up at the next resolve — **no real-time push**
(rejected approach C; the GM is the human applying the change and players never see
the DAG). This exploits design the backbone already shipped: the non-linear-sketchpad
rule (no ordering/reachability validation), nullable transition targets, and
resolve-time DAG reads make a grafted-on mid-session branch valid immediately with
zero new machinery.

---

## 2. The GM-vs-player text contract (refined I-2)

`Beat` already has the clean split (`internal_description` GM-only vs
`player_hint`/`player_resolution_text` player-facing, role-gated by the backbone's
`serialize_story_log(story, requester_role)`). This step extends the *same* explicit,
enforced contract to Story/Chapter/Episode. This **supersedes** the earlier
"reuse description/summary as a dual-use pitch" idea — dual-use makes the visibility
rule unenforceable.

| Field | Role | Player-visible? | Frontend label |
|---|---|---|---|
| `description` | GM authoring intent / pitch / "here's what I'm thinking" | **Never**, any maturity | **"Internal GM Description"** (+ "not player-visible" helper) |
| `consequences` (Chapter/Episode) | Spoilery outcome notes | **Never** | GM-only (grouped with Internal Description) |
| `summary` | **"The Story So Far"** — player-facing running recap: what has happened + light signal of what's ahead | Yes, via role-gated log, maturity-gated | **"The Story So Far"** (+ "shown to players to catch them up" helper) |
| `resting_conclusion` (Episode) | Player-facing rest text (backbone) | Yes (already player-facing) | "Resting conclusion (player-facing)" |
| Beat `internal_description` / `player_hint` / `player_resolution_text` | Already split | Per existing role-gating | unchanged (reference pattern) |

- **`summary` is a GM-maintained living field** — the GM keeps it current as the story
  advances. It is **not** auto-generated from beats/resolutions and **not**
  versioned/historied (the narrative messages + story log already hold the mechanical
  record). Hand-written curated recap; YAGNI on automation.
- **One small additive migration:** add **`Story.summary`** (`TextField(blank=True)`,
  player-facing) so the split is consistent across all three node levels — Chapter and
  Episode already have `summary`. This is the *only* model/migration change in this
  step.
- **Enforcement = the clear-cut distinction in code:** extend `serialize_story_log`
  and player-facing serializers so the player role *never* receives
  `description`/`consequences`/GM node text — only `summary` / `resting_conclusion`,
  and only when maturity/progress permits (a Pitch-stage node → players see nothing
  for that node). GM/staff serializers expose both halves.

---

## 3. Backend authoring + run-control API

All under the app's strictly-enforced 3-layer pattern (`stories/CLAUDE.md`):
`BasePermission` subclass → input serializer `validate()`/`validate_<field>` → thin
view → service; typed `StoryError` with `user_message`, never `str(exc)`;
`get_queryset` scoping for defense-in-depth.

- **Expose authoring fields on existing CRUD** (additive serializer fields + scoped
  write perms — reuse the `IsStoryOwnerOrStaff` family): `maturity` on
  Story/Chapter/Episode; `resting_conclusion`/`is_ending` on Episode; the GM/player
  text fields per §2; `kind`/`advances`/`risk` already on `BeatSerializer` (risk>0
  staff-only gate already enforced — keep).
- **Episode maturity promotion = custom action** `POST /api/episodes/{id}/promote/`
  (carries the PLOT-gate): input serializer mirrors `promote_episode_maturity` so
  `MaturityPromotionError` → 400; thin view calls the existing service. Story/Chapter
  `maturity` = plain writable field (backbone gives them no promotion gate).
  Demotion stays unvalidated (backbone rule).
- **Scope assignment = custom action** `POST /api/stories/{id}/assign/`
  `{scope, character_sheet|covenant|gm_table}`: serializer validates the scope+target
  combo; view calls the existing `create_character_progress` /
  `create_group_progress` / `create_global_progress`. The backbone's
  `StoryNotAssignedError` guard is what this action lifts.
- **Run-control = wire existing endpoints** (near-zero new backend): the backbone
  already shipped `POST /api/stories/{pk}/resolve-episode/`, `POST /api/beats/{pk}/mark/`,
  and the session-request/AGM actions, with frontier resolution already wired into
  `resolve_episode`. This step exposes them in the UI; it does not rebuild them.
- **Nimble add = zero new backend.** "Quick-add beat / add-branch from this episode"
  is the standard Beat/Transition create endpoints with `episode`/`source_episode`
  pre-filled by the UI; the no-reachability rule makes the result immediately valid.

Net backend: additive serializer fields, two custom actions (`promote`, `assign`),
one additive `Story.summary` field+migration, the §2 visibility enforcement. No new
runtime machinery.

---

## 4. The minimal functional UI

Reshape the stale Phase-4 `StoryAuthorPage` (built for the old predicate-beat model)
to the backbone model — and revive/rewire the existing Phase-4/5 components rather
than greenfield.

- **Story section / list:** staffer-or-GM lands, sees their stories (owner/GM-scoped
  by existing perms) — open / edit / **create**.
- **Story editor:** `title`; **"Internal GM Description"** + **"The Story So Far"**
  (labeled per §2); `maturity` selector; **scope-assign control**
  (Personal+CharacterSheet / Group+covenant-or-table / Global → `assign` action);
  a **GM Notes tab** (the story-scoped `StoryNote` ledger — append + timestamped list,
  GM/staff-only); a nested **Chapters → Episodes → Beats** tree.
- **Chapter/Episode rows:** inline title + the two text fields; `maturity` (Episode
  shows a **Promote** button → `promote` action, surfacing the PLOT-gate 400 inline);
  `resting_conclusion`/`is_ending` on Episode; add/edit/remove; add children.
- **Beat editor:** `kind` / `advances` (tangent toggle) / `risk` (risk>0 disabled for
  non-staff, matching the server gate) + predicate sub-config +
  `internal_description`/`player_hint`/`player_resolution_text`.
- **Run-control (folded in, mostly reshaping existing Phase-4/5 dialogs):**
  Promote, **Resolve-episode**, **Mark-beat**, Contribute — driven from the same
  page; the editor shows **current progress state inline** (where the assigned PC is,
  WAITING_FOR_GM/RESTING) so a GM improvises mid-session with context.
- **DAG editing (folded in):** interactive React Flow — drag-to-add transitions,
  add/reposition nodes (reshape Phase-5's drag-to-add to the backbone model).
- **Data flow:** React Query hooks against §3 endpoints, invalidate-on-mutate;
  types via the existing `just gen-api-types` pipeline.

Out of the UI: the resolution *engines* (beats still resolve via GM-mark
placeholder), real-time push, per-node notes, visual polish.

---

## 5. Dashboard query cleanup (folded follow-ups #2/#3)

While in `stories/views.py` for §3:

- **`GMQueueView`:** replace the per-story loop calling `get_eligible_transitions`
  (queries-in-loop) with a scoped/bounded `get_queryset` + batched transition/beat
  state resolution (annotate or bounded `Prefetch(to_attr=...)`), bounded query count
  regardless of story count.
- **`StaffWorkloadView`:** scope/bound the unbounded `.values()` scans the same way;
  keep `.values()` only for genuine wire-aggregation.
- **`_build_gm_queue_for_story`:** collapse the 6 list accumulators into a
  `@dataclass` (removes the `# noqa: PLR0913`); behavior-preserving.

No behavior change — guarded by existing `test_views_gm_queue` /
`test_views_staff_workload` plus new `assertNumQueries` tests locking the bounded
count so the queries-in-loop pattern cannot silently return. Aligns with CLAUDE.md
"No Queries in Loops" / identity-map principles.

---

## 6. Cross-cutting: permissions, errors, testing, boundary

- **Permissions:** authoring + run-control = story owners / active GMs / staff;
  players never reach this surface. Risk>0 still staff-only (PoC ladder; full
  trust→risk ladder remains deferred). Demotion unvalidated; promotion PLOT-gated.
- **Errors:** the 3-layer pattern — validation in input serializers
  (`MaturityPromotionError`, scope/`StoryNotAssignedError`, risk gate surface as 400
  via serializer `validate()`), thin views, typed exceptions' `user_message` only.
- **Testing:** backend `APITestCase` per endpoint/field — auth matrix, promote
  happy + PLOT-gate-reject, assign + progress-creation + UNASSIGNED-guard, run-control
  wired to the backbone runtime (frontier lands correctly), GM/player visibility
  (player role never sees `description`/`consequences`; Pitch node hidden), risk gate
  intact; dashboard `assertNumQueries`. Frontend Vitest unit tests for changed
  components/hooks; Playwright e2e smoke for the author-and-run flow rendering
  crash-free. Completion gate = backbone discipline: full fresh-DB `world.stories`
  (no `--keepdb`) + cross-app + `ruff`/`ty` + `pnpm typecheck`/`lint`/`build` +
  `just gen-api-types` regenerated.
- **Explicitly out of scope** (stay deferred): resolution engines (Mission/Challenge,
  Situation/Encounter+Sessions); consequence/reward computation; GM-leveling / real
  trust→risk ladder; covenant entity; real-time push; per-node notes; visual polish.

---

## 7. Net change surface

- **Models/migration:** exactly one additive field — `Story.summary` + its migration.
- **Backend:** additive serializer fields; 2 custom actions (`promote`, `assign`);
  §2 visibility enforcement in `serialize_story_log` + player serializers; §5 view
  refactor. Run-control endpoints already exist (wire only).
- **Frontend:** reshape `StoryAuthorPage` + revive/rewire Phase-4/5 dialogs and
  drag-to-add DAG to the backbone model; new labeled text fields, scope-assign,
  GM Notes tab, inline progress state, nimble quick-add.
- **Tests:** new API + visibility + assertNumQueries + frontend unit/e2e.
