# Stories Authoring API + Minimal Functional UI — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (or superpowers:subagent-driven-development) to implement this plan task-by-task.

**Goal:** Make the merged authoring backbone usable end-to-end through the browser: expose the new authoring fields + GM/player text split via the API, add `promote`/`assign` actions, wire the existing run-control dialogs into the author page, add maturity/scope-assign/GM-notes UI, and pay down the GMQueue/StaffWorkload query debt.

**Architecture:** The backbone was strictly **additive** — `Beat` kept `predicate_type` and gained `kind`/`advances`/`risk`; `Transition`/`EpisodeDAG`/`MarkBeatDialog`/`ResolveEpisodeDialog`/progression-requirements are **unchanged** and must NOT be torn out. This work = (1) one additive model field (`Story.summary`) + migration; (2) additive serializer fields + role-gated visibility split (`description`/`consequences` GM-only, `summary` player-ok, maturity-gated); (3) two custom actions (`promote`, `assign`) reusing existing services; (4) behavior-preserving dashboard query refactor; (5) frontend: *augment* existing forms with the new fields, *add* promote/scope-assign/GM-notes UI + label split, *wire* existing run-control dialogs into `StoryAuthorPage`. All backend under the strict 3-layer pattern (`src/world/stories/CLAUDE.md`).

**Tech Stack:** Django + Evennia (`SharedMemoryModel`), DRF, factory_boy, Postgres; React + React Query + React Flow; Vitest + Playwright. App is `ty`-typed — full annotations required.

---

## Conventions (read once)

- Branch: `feature/stories-authoring-api-ui` (already created off `origin/main`/#446; design committed at `02502edb`). Never main. No worktree.
- No `cd && <cmd>` compounds. Git: `git -C C:/Users/apost/PycharmProjects/arxii <cmd>`.
- Backend tests: `uv run arx test <full.module.path> --keepdb` (Bash timeout 600000ms). **Do NOT use `-k`** (this runner mis-parses it as a module path — run whole modules). Fresh-DB gate: `echo "yes" | uv run arx test world.stories` (no `--keepdb`).
- Backend test base: `APITestCase`, `@classmethod setUpTestData(cls)`; auth via `self.client.force_authenticate(user=...)`; fixtures `AccountFactory`/`GMProfileFactory(account=...)`/`GMTableFactory(gm=...)`/`StoryFactory(owners=[...])`/`ChapterFactory`/`EpisodeFactory`/`BeatFactory`.
- 3-layer pattern is **strictly enforced**: permission class → input serializer `validate()` (FK via `PrimaryKeyRelatedField`) → thin view (`ser.is_valid(raise_exception=True)`, no `try/except ValidationError`) → service (`if ... raise ValueError(msg)`, no `assert`). Typed `StoryError.user_message`, never `str(exc)`.
- `# noqa` only with justification (CLAUDE.md policy). `ruff check`/`ruff format`/`ty` clean per changed file.
- Frontend: `pnpm -C frontend typecheck` / `lint` / `test` / `build`; `just gen-api-types` after any backend schema change; Vitest via `renderWithProviders` (QueryClient+MemoryRouter), mock `../queries` and `sonner`; Playwright = crash-free shell smoke.
- Commit per task with the message in its final step.

Relevant skills: @superpowers:test-driven-development, @superpowers:verification-before-completion, @superpowers:receiving-code-review.

---

## PHASE A — Backend: model field + serializer exposure + visibility split

### Task A1: Add `Story.summary` + migration

**Files:** Modify `src/world/stories/models.py` (`Story`, after `description` ~L84); Create migration `0031_story_summary.py`; Test `src/world/stories/tests/test_story_summary_field.py`.

**Step 1 — failing test:**
```python
# test_story_summary_field.py
from django.test import TestCase
from world.stories.factories import StoryFactory

class StorySummaryFieldTests(TestCase):
    def test_story_has_blank_summary_default(self):
        s = StoryFactory()
        self.assertEqual(s.summary, "")
    def test_summary_is_persisted(self):
        s = StoryFactory(); s.summary = "The Story So Far text"; s.save(); s.refresh_from_db()
        self.assertEqual(s.summary, "The Story So Far text")
```
**Step 2:** `uv run arx test world.stories.tests.test_story_summary_field --keepdb` → FAIL (`'Story' object has no attribute 'summary'`).
**Step 3 — implement:** add to `Story` after `description`:
```python
    summary = models.TextField(
        blank=True,
        help_text=(
            "Player-facing 'The Story So Far' — GM-maintained running recap "
            "of what has happened and what may lie ahead. Surfaced to players "
            "via the role-gated story log, maturity-gated. NOT auto-generated."
        ),
    )
```
Then: `uv run arx manage makemigrations stories` (custom command; expect one migration `0031_*`; the phantom-Evennia `--check` exit-1 noise is benign — verify via `git status` that only a `0031_*.py` was created). `uv run arx manage migrate` may fail on the **pre-existing** unrelated `checks` dev-DB state — that's known and OK (the test runner builds a fresh DB; do not flush the dev DB).
**Step 4:** `uv run arx test world.stories.tests.test_story_summary_field --keepdb` → PASS (2).
**Step 5 — commit:**
```bash
git -C C:/Users/apost/PycharmProjects/arxii add src/world/stories/models.py src/world/stories/migrations/0031_*.py src/world/stories/tests/test_story_summary_field.py
git -C C:/Users/apost/PycharmProjects/arxii commit -m "feat(stories): add player-facing Story.summary field + migration"
```

### Task A2: Expose authoring fields on Story/Chapter/Episode serializers

**Read first:** `src/world/stories/serializers.py` `StoryDetailSerializer` (~L125), `StoryCreateSerializer` (~L173), `ChapterDetailSerializer` (~L244), `EpisodeDetailSerializer` (~L320), `EpisodeCreateSerializer` (~L342). **Files:** Modify `serializers.py`; Test `tests/test_serializers_authoring_fields.py`.

**Step 1 — failing test** (APITestCase): assert GET `/api/stories/{id}/` returns `summary` & `maturity`; PATCH can set them; GET `/api/episodes/{id}/` returns `maturity`/`resting_conclusion`/`is_ending` and PATCH sets them; same for Chapter `maturity`. Use `reverse("story-detail", kwargs={"pk": ...})` etc., staff auth.
**Step 2:** run module → FAIL (fields absent / 200 lacks keys).
**Step 3 — implement:** add to `Meta.fields` (and keep `read_only_fields` minimal):
- `StoryDetailSerializer`: `+ "summary", "maturity"`. `StoryCreateSerializer`: `+ "summary"` (creation may set the recap; `maturity` defaults PITCH — not in create).
- `ChapterDetailSerializer`: `+ "maturity"`. `EpisodeDetailSerializer`: `+ "maturity", "resting_conclusion", "is_ending"`.
- `EpisodeCreateSerializer`: leave as-is (authoring of those happens via detail PATCH / promote).
Match existing serializer style exactly (no new `validate` here).
**Step 4:** run module → PASS. Also run `uv run arx test world.stories.tests.test_views_story_log world.stories.tests.test_serializers_beat_risk --keepdb` → still PASS.
**Step 5 — commit:** `feat(stories): expose maturity/summary/resting_conclusion/is_ending on serializers` (paths: serializers.py + new test).

### Task A3: Role-gated GM↔player text visibility split

**Design contract:** player role must NEVER receive `description`/`consequences` on Story/Chapter/Episode; `summary` is player-ok but **blanked when the node's `maturity == PITCH`** for player viewers. GM/staff get everything. `Beat` already split by `serialize_story_log`; this covers the **detail serializers** (the leak path: a participant player GET-ing `/api/stories/{id}/`, `/api/chapters/{id}/`, `/api/episodes/{id}/`).

**Read first:** `permissions.py::classify_story_log_viewer_role` (~L959) and `_story_log_user_has_access` (~L994); `StoryViewSet.get_queryset` (~L263) to see who can retrieve.

**Files:** Modify `serializers.py` (Story/Chapter/Episode **Detail** serializers); Test `tests/test_serializers_visibility_split.py`.

**Step 1 — failing test** (APITestCase, `setUpTestData` builds: staff, lead-GM account+profile+table, a player account with a CharacterSheet, a CHARACTER-scope `Story(character_sheet=player_sheet, primary_table=table)`, a Chapter, a PITCH Episode and a PLOT Episode):
- staff GET story/chapter/episode → sees `description`, `consequences`, `summary`.
- player GET → `description` and `consequences` absent/empty; `summary` present for PLOT-maturity node; `summary` empty for PITCH-maturity node.
- lead-GM GET → sees all (like staff).
**Step 2:** run → FAIL (player sees description).
**Step 3 — implement:** add a role-aware `to_representation` to each Detail serializer (mirror the project pattern — compute role via `classify_story_log_viewer_role(request.user, <story>)`, where `<story>` is `obj` / `obj.story` / `obj.chapter.story`). If role is `"player"` (not staff/lead_gm): pop `description` and `consequences` from the representation; if the node `maturity == StoryMaturity.PITCH`, also set `summary` to `""`. Keep it a thin override calling `super().to_representation()` then filtering — no business logic in the view. Import `classify_story_log_viewer_role`, `StoryMaturity` per existing import style. Handle missing request context (no request → treat as no-access → safest: omit GM fields).
**Step 4:** run → PASS; re-run `test_views_story_log`, `test_serializers_authoring_fields`, `test_serializers_beat_risk` → PASS.
**Step 5 — commit:** `feat(stories): role-gate description/consequences (GM-only) vs summary (player) on detail serializers`.

---

## PHASE B — Backend: promote + assign actions

### Task B1: `POST /api/episodes/{id}/promote/`

**Read first:** `views.py` `EpisodeViewSet` + its existing `resolve`-style `@action` (and `EpisodeViewSet.resolve` for the exact action/permission/try-except pattern the app permits); `services/maturity.py::promote_episode_maturity`; `permissions.py::IsEpisodeStoryOwnerOrStaff` / `IsLeadGMOnEpisodeStoryOrStaff`; `exceptions.py::MaturityPromotionError`.

**Files:** Modify `views.py` (`EpisodeViewSet` add `promote` action), `serializers.py` (add `PromoteEpisodeInputSerializer`); Test `tests/test_views_episode_promote.py`.

**Step 1 — failing test** (APITestCase): owner/lead-GM can promote OUTLINE→PLOT when episode has `resting_conclusion` + (outbound transition OR `is_ending`) → 200, `episode.maturity == "plot"`; missing requirements → 400 with `MaturityPromotionError.user_message`; demotion PLOT→OUTLINE → 200 (unvalidated); non-owner player → 403; bad target value → 400. `reverse("episode-promote", kwargs={"pk": ep.pk})`.
**Step 2:** run → FAIL (no such action/route).
**Step 3 — implement (3-layer):**
- `PromoteEpisodeInputSerializer`: a `target` `ChoiceField(choices=StoryMaturity.choices)`; `validate()` receives `episode` via context, constructs the post-state and mirrors `promote_episode_maturity`'s rule so a disallowed PLOT promotion raises `serializers.ValidationError({"target": MaturityPromotionError().user_message})` (do NOT call the service in validate — only validate; assign `msg` first per EM101).
- `EpisodeViewSet.promote`: `@action(detail=True, methods=[HTTPMethod.POST])`, `permission_classes=[IsLeadGMOnEpisodeStoryOrStaff]` (match the exact class the app uses for episode writes — confirm from views.py). Body: get object, `ser = PromoteEpisodeInputSerializer(data=request.data, context={"episode": episode}); ser.is_valid(raise_exception=True)`, call `promote_episode_maturity(episode, ser.validated_data["target"])`, return the `EpisodeDetailSerializer` data. No `try/except`.
**Step 4:** run module → PASS; re-run `world.stories.tests.test_services_maturity --keepdb` → PASS.
**Step 5 — commit:** `feat(stories): episode maturity-promotion endpoint (PLOT-gate via serializer)`.

### Task B2: `POST /api/stories/{id}/assign/`

**Read first:** `views.py` `StoryViewSet` + an existing custom action on it (e.g. assign-to-table / detach) for the action+permission pattern; `services/progress.py` `create_character_progress`/`create_group_progress`/`create_global_progress`; `exceptions.py::StoryNotAssignedError`; `permissions.py::IsStoryOwnerOrStaff`/`IsLeadGMOnStoryOrStaff`.

**Files:** Modify `views.py` (`StoryViewSet.assign`), `serializers.py` (`AssignStoryInputSerializer`); Test `tests/test_views_story_assign.py`.

**Step 1 — failing test:** owner/lead-GM POST `{scope:"character", character_sheet:<id>}` → 200, `story.scope=="character"`, a `StoryProgress` exists; `{scope:"group", gm_table:<id>}` → group progress; `{scope:"global"}` → global progress; mismatched combo (e.g. `scope:"character"` without `character_sheet`, or with `gm_table`) → 400; non-owner → 403. `reverse("story-assign", kwargs={"pk": story.pk})`.
**Step 2:** run → FAIL.
**Step 3 — implement (3-layer):**
- `AssignStoryInputSerializer`: `scope` `ChoiceField(StoryScope.choices)` (exclude `UNASSIGNED` — assigning *to* unassigned is invalid); `character_sheet`/`gm_table` as `PrimaryKeyRelatedField(queryset=..., required=False, allow_null=True)`. `validate()` enforces the scope↔target invariant (CHARACTER⇒character_sheet only; GROUP⇒gm_table; GLOBAL⇒neither) with assigned `msg`.
- `StoryViewSet.assign`: `@action(detail=True, methods=[POST])`, `permission_classes=[IsLeadGMOnStoryOrStaff]` (confirm exact class); validate; in a `transaction.atomic()` set `story.scope`, `story.save(update_fields=["scope"])`, call the matching `create_*_progress`. The service raises `StoryNotAssignedError` only if still UNASSIGNED — not expected here since we set scope first; keep service call after the scope set. Return `StoryDetailSerializer`.
**Step 4:** run module → PASS; re-run `world.stories.tests.test_services_progress_scope_guard --keepdb` → PASS.
**Step 5 — commit:** `feat(stories): scope-assign endpoint (sets scope + creates progress)`.

---

## PHASE C — Backend: dashboard query cleanup (folds #2/#3)

### Task C1: `_build_gm_queue_for_story` → dataclass accumulator

**Read first:** the full `GMQueueView` + `_build_gm_queue_for_story` in `views.py` (the 6-list-accumulator + `# noqa: PLR0913`).
**Files:** Modify `views.py`; Test extend `tests/test_views_gm_queue.py`.

**Step 1 — failing test:** add `test_gm_queue_query_count_is_bounded`: build a GM table with **N=5** ready stories; `with self.assertNumQueries(<bound>):` GET `/api/stories/gm-queue/`; assert `< some constant independent of N` (first run: record the count, set the bound to that; then in Step 3 reduce the loop and tighten the bound — TDD here is: write the assertion at the *target* bound; it fails now because the per-story loop issues O(N) queries).
**Step 2:** run → FAIL (query count exceeds target / scales with N).
**Step 3 — implement:** introduce `@dataclass GMQueueBuckets` (fields: the existing list names) replacing the 6 positional accumulators (removes `# noqa: PLR0913`); hoist the per-story `get_eligible_transitions`/beat lookups out of the loop via batched queries (annotate or one bounded `Prefetch(to_attr=...)` over the candidate stories' episodes/transitions/beats) so total queries are bounded regardless of story count. Behavior-preserving: the response JSON shape is unchanged.
**Step 4:** run `world.stories.tests.test_views_gm_queue --keepdb` → ALL PASS (existing + new bound).
**Step 5 — commit:** `refactor(stories): bound GMQueue queries; dataclass accumulator (follow-up #2/#3)`.

### Task C2: `StaffWorkloadView` bounded scans + query-count lock

**Read first:** full `StaffWorkloadView` in `views.py`.
**Files:** Modify `views.py`; Test extend `tests/test_views_staff_workload.py`.

**Step 1 — failing test:** `test_staff_workload_query_count_bounded` — N WAITING_FOR_GM/stale stories; `assertNumQueries(<bound>)` GET `/api/stories/staff-workload/`; bound independent of N.
**Step 2:** run → FAIL.
**Step 3 — implement:** replace the unbounded per-model `.values()` loops with scoped, batched aggregate queries (keep `.values()` only for genuine wire-aggregation; add `select_related` only where instances serialize related fields). Response shape unchanged.
**Step 4:** `uv run arx test world.stories.tests.test_views_staff_workload --keepdb` → ALL PASS.
**Step 5 — commit:** `refactor(stories): bound StaffWorkload scans + assertNumQueries lock`.

---

## PHASE D — API types + frontend data layer

### Task D1: Regenerate API types

**Step 1:** `just gen-api-types` (regenerates `src/schema.json` + `frontend/src/generated/api.d.ts`). If `spectacular --validate` emits the known pre-existing project-wide warnings, that's fine — confirm `Story`/`Episode`/`Chapter`/`Beat` schemas now include the new fields and the `promote`/`assign` paths exist.
**Step 2:** `pnpm -C frontend typecheck` → note any type breakage from the regenerated schema (expected: places using `Story`/`Episode` types may need the new optional fields — fix in D2).
**Step 3 — commit:** `chore(stories): regenerate API types for authoring fields + promote/assign` (paths: `src/schema.json`, `frontend/src/generated/api.d.ts`).

### Task D2: Frontend API client + hooks for promote/assign/story-notes

**Read first:** `frontend/src/stories/api.ts`, `queries.ts`, `types.ts` (mirror existing client/hook/invalidation patterns exactly).
**Files:** Modify `api.ts`, `queries.ts`, `types.ts`; Test `frontend/src/stories/__tests__/queries.authoring.test.ts`.

**Step 1 — failing test:** Vitest asserting `promoteEpisode(episodeId, {target})`, `assignStory(storyId, body)`, `listStoryNotes({story})`, `createStoryNote({story, body})` exist and call the right endpoints (mock fetch/axios layer per existing test pattern).
**Step 2:** run `pnpm -C frontend test stories` → FAIL.
**Step 3 — implement:** add the four api functions (`POST /api/episodes/{id}/promote/`, `POST /api/stories/{id}/assign/`, `GET /api/story-notes/?story=`, `POST /api/story-notes/`) and `useMutation`/`useQuery` hooks with cache invalidation mirroring `useMarkBeat`/`useCreateStory` (invalidate `story(id)`, `storyList`, `gmQueue`, relevant lists). Extend `types.ts` only where the generated schema doesn't cover (it should cover most).
**Step 4:** run → PASS; `pnpm -C frontend typecheck` → clean.
**Step 5 — commit:** `feat(stories-fe): api+hooks for promote, assign, story-notes`.

---

## PHASE E — Frontend authoring forms (AUGMENT, do not replace)

> The predicate-beat UI is **not stale** — keep it. These tasks ADD fields.

### Task E1: BeatFormDialog — add kind / advances / risk

**Read first:** `frontend/src/stories/components/BeatFormDialog.tsx` (full). **Files:** modify it; Test `__tests__/BeatFormDialog.test.tsx` (extend).
**Step 1 — failing test:** dialog renders a `kind` select (Situation/Encounter/Task/Requirement), an `advances` toggle (labeled "Advances the plot (off = Tangent)"), a `risk` number input that is **disabled when the current user is not staff** (mock the user/role per the test util) and submits `kind`/`advances`/`risk` in the create/update body.
**Step 2:** `pnpm -C frontend test BeatFormDialog` → FAIL.
**Step 3 — implement:** add the three controls alongside the existing predicate config (do not remove predicate fields). Risk field disabled + helper "Only staff may set risk above 0" when non-staff (read role from the existing auth/user hook the app uses; if none in scope, gate by a `canSetRisk` prop the parent passes from the user context). Include them in the submit payload (types already regenerated).
**Step 4:** run → PASS; `pnpm -C frontend typecheck`/`lint` clean.
**Step 5 — commit:** `feat(stories-fe): beat kind/advances/risk in BeatFormDialog`.

### Task E2: Episode/Chapter/Story forms — maturity + resting_conclusion/is_ending + labeled text split

**Read first:** `EpisodeFormDialog.tsx`, `ChapterFormDialog.tsx`, `StoryFormDialog.tsx`. **Files:** modify the three; Tests: their `__tests__` specs.
**Step 1 — failing tests:** Episode form shows `resting_conclusion` textarea + `is_ending` checkbox + read-only `maturity` display; Story & Chapter forms relabel the `description` field as **"Internal GM Description"** (helper: "Not shown to players") and add a **"The Story So Far"** field bound to `summary` (helper: "Player-facing recap — keep current as the story advances"); all submit the new fields.
**Step 2:** run → FAIL.
**Step 3 — implement:** add controls + labels/helper text; submit `summary`/`resting_conclusion`/`is_ending`. `maturity` is display-only here (promotion is Task E3). Match existing form/validation idiom.
**Step 4:** run → PASS; typecheck/lint clean.
**Step 5 — commit:** `feat(stories-fe): GM/player text split + episode resting_conclusion/is_ending in forms`.

### Task E3: Maturity Promote control

**Files:** Create `frontend/src/stories/components/PromoteMaturityButton.tsx`; Test `__tests__/PromoteMaturityButton.test.tsx`; wire into `StoryAuthorPage`/episode row.
**Step 1 — failing test:** button shows current maturity; clicking promotes via `usePromoteEpisode`; on 400 it surfaces the `MaturityPromotionError` message inline (not a generic toast-only).
**Step 2:** run → FAIL.
**Step 3 — implement:** small component using the D2 hook; render the server 400 `target`/`detail` message inline; success invalidates the story/episode queries.
**Step 4:** run → PASS.
**Step 5 — commit:** `feat(stories-fe): episode maturity promote control`.

### Task E4: Scope-assign control

**Files:** Create `ScopeAssignDialog.tsx`; Test; wire into `StoryAuthorPage` story header.
**Step 1 — failing test:** dialog lets you pick scope + (CharacterSheet | covenant | GM table) and calls `useAssignStory`; mismatched combos disabled/validated; success reflects new scope.
**Step 2:** FAIL. **Step 3:** implement (reuse any existing CharacterSheet/table pickers; minimal). **Step 4:** PASS. **Step 5 — commit:** `feat(stories-fe): scope-assign dialog`.

### Task E5: GM Notes tab

**Files:** Create `GMNotesPanel.tsx` (list `/api/story-notes/?story=` + append form); Test; add as a tab/section in `StoryAuthorPage` (and/or `StoryDetailPage` per minimal — author page is sufficient).
**Step 1 — failing test:** renders timestamped author+body list; submitting appends via `useCreateStoryNote`; GM/staff-only (component assumes the page is already GM-gated).
**Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS. **Step 5 — commit:** `feat(stories-fe): GM Notes tab consuming /api/story-notes/`.

---

## PHASE F — Frontend run-control + DAG wiring (mostly WIRING existing components)

> `MarkBeatDialog` (success/failure is correct for GM-marked), `ResolveEpisodeDialog`, `ContributeBeatDialog`, `EpisodeDAG` (drag-to-add) are **model-compatible** — do not rewrite. Wire them into the author page and add maturity/progress context.

### Task F1: Surface current progress state in StoryAuthorPage

**Read first:** `StoryAuthorPage.tsx`, `EpisodeDAG.tsx`, `BeatRow.tsx`/`BeatList.tsx`.
**Files:** modify `StoryAuthorPage.tsx` (+ a small `ProgressStateBanner.tsx`); Test.
**Step 1 — failing test:** when a story has progress, the author page shows where the PC/group is and any WAITING_FOR_GM/RESTING status inline (read from the existing progress/story endpoints).
**Step 2:** FAIL. **Step 3:** implement a thin banner using existing progress queries. **Step 4:** PASS. **Step 5 — commit:** `feat(stories-fe): inline progress state on author page`.

### Task F2: Wire run-control dialogs into the author page

**Files:** modify `StoryAuthorPage.tsx`/episode+beat rows to mount the existing `ResolveEpisodeDialog`/`MarkBeatDialog`/`ContributeBeatDialog` (gated by `beat.can_mark` / lead-GM as those dialogs already do); Test.
**Step 1 — failing test:** from an episode/beat row on the author page the GM can open Resolve/Mark dialogs (rendered, calls the existing hooks). No new dialog logic — just mounting + the existing `can_mark` gating.
**Step 2:** FAIL. **Step 3:** mount existing components; pass the props they already expect. **Step 4:** PASS. **Step 5 — commit:** `feat(stories-fe): run-control dialogs available from the author page`.

### Task F3: Nimble quick-add (+Beat / +Branch from a node)

**Files:** modify `StoryAuthorPage.tsx`/`EpisodeDAG.tsx` to add one-click "+ Beat" (opens `BeatFormDialog` with `episode` preset) and "+ Branch" (opens existing `TransitionFormDialog` with `source_episode` preset); Test.
**Step 1 — failing test:** clicking "+ Beat" on an episode opens the beat dialog with that episode preset; "+ Branch" opens the transition dialog with source preset. No backend change (uses existing create endpoints; backbone's no-reachability rule makes the result valid immediately).
**Step 2:** FAIL. **Step 3:** implement the affordances. **Step 4:** PASS. **Step 5 — commit:** `feat(stories-fe): nimble +Beat/+Branch quick-add for in-session authoring`.

---

## PHASE G — Integration, e2e, docs, regression gate

### Task G1: Playwright e2e smoke
**Files:** `frontend/e2e/stories-author.spec.ts` (new) following the existing crash-free-shell pattern (`#root` not empty, no `pageerror`, filter API noise). Cover `/stories/author` shell + that the author tree/DAG/forms mount.
**Steps:** write spec → `pnpm -C frontend build` then `pnpm -C frontend test:e2e stories-author` → PASS → commit `test(stories-fe): e2e smoke for author page`.

### Task G2: Docs
**Files:** `docs/systems/stories.md` (new endpoints `episodes/{id}/promote/`, `stories/{id}/assign/`, `Story.summary`, the GM/player visibility contract, the bounded dashboards), `docs/systems/INDEX.md`, regenerate `docs/systems/MODEL_MAP.md` via `uv run python -c "import tools.introspect_models as m; m.write_model_map()"` (NOT the bare script — it only prints). Append to the design follow-ups: mark I-1, I-2, #2, #3 **resolved** in `docs/plans/2026-05-15-stories-authoring-framework-design.md` (gitignored → `git add -f`). Commit `docs(stories): document authoring API/UI + resolve follow-ups I-1/I-2/#2/#3`.

### Task G3: Completion gate (controller-run; do not background in a subagent)
1. `echo "yes" | uv run arx test world.stories` (fresh DB, no `--keepdb`) → all green.
2. `echo "yes" | uv run arx test world.stories world.gm world.character_sheets` → green.
3. `ruff check src/world/stories && ruff format --check src/world/stories` → clean (the pre-existing custom-linter "invalid noqa" ruff warnings are not ours).
4. `pnpm -C frontend typecheck && pnpm -C frontend lint && pnpm -C frontend build && pnpm -C frontend test` → clean; `pnpm -C frontend test:e2e` smoke green.
5. `just gen-api-types` leaves the tree clean (no undocumented schema drift).
6. If green, the success criterion holds: in the browser a staffer/GM authors a story (name + Internal GM Description + The Story So Far) → chapters → episodes → beats (kind/advances/risk) → assigns a PC → promotes → resolves → sees WAITING_FOR_GM/RESTING, and can quick-add beats/branches mid-session. Final commit if any gate fixes were needed: `test(stories): green regression for authoring API/UI`.

---

## Out of scope (unchanged from design — do NOT build)

Resolution engines (Mission/Challenge, Situation/Encounter+Sessions — beats still resolve via GM-mark); consequence/reward computation; GM-leveling / real trust→risk ladder; covenant entity; real-time push; per-chapter/episode notes; visual polish; ripping out the predicate-beat model (it is additive substrate, not stale).

## Notes baked in
- Backbone is **additive**: keep predicate_type/Transition/DAG/MarkBeat/Resolve as-is; this plan augments + wires.
- One migration only (`0031_story_summary`). `makemigrations --check` phantom-Evennia exit-1 is benign (custom command); the real gate is the fresh-DB suite + the project's "Check Django migrations" pre-commit hook.
- Every new endpoint follows the strict 3-layer pattern; visibility split lives in serializer `to_representation`, never in views.
