# Stories Authoring Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Clear the low/no-design follow-ups deferred by the merged stories authoring API/UI branch (#447): items (a)–(e) + M-1/M-2/M-3 + the I-A twin, all recorded in `docs/plans/2026-05-15-stories-authoring-framework-design.md` ledger §"stories-authoring-api-ui — discovered follow-ups (2026-05-17)".

**Architecture:** Pure cleanup on `feature/stories-authoring-cleanup` (already created off fresh main, HEAD = #447 merge `2810d7bd`). Backend: one shared predicate (DRY), behavior-neutral renames/constants/comments, one new gate role (owner-privileged), one new payload field. Frontend: two small error-handling correctness fixes plus the banner consuming the new field. No migrations (all fields already exist).

**Tech Stack:** Django + DRF + Evennia (`SharedMemoryModel`), `ty` type checker, ruff; React + React Query + Vitest. Tests via `arx test` only; FE gate is `pnpm -C frontend build` (NOT just typecheck).

**Command-shape discipline (inject into every subagent prompt):** create/replace files with the Write tool (never `cat`/heredoc); no `cd &&`/`;` compounds (use `git -C`, `pnpm -C`); no `$()`/backticks; no PowerShell-in-bash; forward-slash `/c/...` paths; tests via `echo "yes" | uv run arx test <target>`; capture long output via `just test-scratch` not `> file`.

---

## Conventions for every task

- **Branch:** `feature/stories-authoring-cleanup` (never main; no worktree).
- **Backend tests:** `echo "yes" | uv run arx test world.stories.tests.<module>` (the `-k` flag is broken in this runner — run whole modules). Final regression runs the whole `world.stories` suite **without `--keepdb`**.
- **FE tests:** `pnpm -C frontend test -- --run <path>`; FE build gate `pnpm -C frontend build`.
- **Lint/type after backend edits:** `uv run ruff check <file>` and (for `views.py`/typed modules, NOT `serializers.py` — ty-excluded) `uv run ty check src/world/stories/views.py`.
- **`StoryStatus` lives in `world.stories.types`, NOT `world.stories.constants`** (verified). `ProgressStatus` lives in `world.stories.constants`.
- Commit after each task with a `fix(stories): …` / `refactor(stories): …` message ending:
  `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>`

---

### Task 1: (a) Extract the shared PLOT-promotion-readiness predicate (DRY)

The PLOT gate (`resting_conclusion` non-empty AND (an outbound transition OR `is_ending`)) is duplicated between `services/maturity.py::promote_episode_maturity` and `serializers.py::PromoteEpisodeInputSerializer.validate()`. Extract one predicate; both call it. Behavior-neutral.

**Files:**
- Modify: `src/world/stories/services/maturity.py:15-31`
- Modify: `src/world/stories/serializers.py:1222-1255`
- Test (existing, must stay green): `src/world/stories/tests/test_services_maturity.py`, `src/world/stories/tests/test_views_episode_promote.py`

**Step 1: Add the shared predicate in `services/maturity.py`** (place directly above `promote_episode_maturity`):

```python
def episode_meets_plot_gate(episode: Episode) -> bool:
    """Whether an episode satisfies the PLOT-maturity gate.

    Single source of truth for the PLOT promotion rule, shared by
    ``promote_episode_maturity`` (service, raises) and
    ``PromoteEpisodeInputSerializer.validate`` (Layer-2, 400). The rule:
    non-empty ``resting_conclusion`` AND (an outbound transition OR
    ``is_ending``). Independent of direction — callers decide when the gate
    applies (upward move *to* PLOT only).
    """
    if not episode.resting_conclusion.strip():
        return False
    return episode.outbound_transitions.exists() or episode.is_ending
```

**Step 2: Rewrite the gate body in `promote_episode_maturity`** so the PLOT branch becomes:

```python
    is_promotion = _RANK[target] > _RANK[StoryMaturity(episode.maturity)]
    if target == StoryMaturity.PLOT and is_promotion and not episode_meets_plot_gate(episode):
        raise MaturityPromotionError
    episode.maturity = target
    episode.save(update_fields=["maturity", "updated_at"])
    return episode
```

**Step 3: Rewrite `PromoteEpisodeInputSerializer.validate()`** to call the shared predicate. Import at top of the local-import convention used in the file — add `from world.stories.services.maturity import episode_meets_plot_gate` as a deferred import inside `validate()` (matches the file's "defer service imports" convention; check neighbours and mirror). New body:

```python
    def validate(self, attrs: Any) -> Any:  # type: ignore[override]
        from world.stories.services.maturity import (  # noqa: PLC0415
            episode_meets_plot_gate,
        )

        episode: Episode = self.context["episode"]
        target: str = attrs["target"]

        current_rank = self._RANK[StoryMaturity(episode.maturity)]
        is_promotion = self._RANK[StoryMaturity(target)] > current_rank
        if (
            target == StoryMaturity.PLOT
            and is_promotion
            and not episode_meets_plot_gate(episode)
        ):
            msg = MaturityPromotionError().user_message
            raise serializers.ValidationError({"target": msg})
        return attrs
```

Leave `_RANK` on the serializer as-is (it also encodes promotion direction at that call site; YAGNI — don't over-extract).

**Step 4:** `uv run ruff check src/world/stories/services/maturity.py src/world/stories/serializers.py`

**Step 5:** `echo "yes" | uv run arx test world.stories.tests.test_services_maturity world.stories.tests.test_views_episode_promote` — expected: all pass (behavior-neutral; existing tests cover both call sites for both the gated-fail and the promote-success paths).

**Step 6: Commit** `refactor(stories): extract shared episode_meets_plot_gate predicate (DRY) [ledger (a)]`

---

### Task 2: (b) Fix misleading `episode` variable + remove dead branch in `IsLeadGMOnStoryOrStaff`

**Files:**
- Modify: `src/world/stories/permissions.py:528-539`
- Test (existing, must stay green): `src/world/stories/tests/test_view_actions_permissions.py`

**Step 1: Replace the non-Story branch.** Current:

```python
        if isinstance(obj, Story):
            story = obj
        else:
            # Walk episode -> chapter -> story.
            episode = getattr(obj, "chapter", None)  # noqa: GETATTR_LITERAL
            if episode is None:
                # obj is an Episode; it has a chapter attribute.
                episode_obj = obj
                story = episode_obj.chapter.story
            else:
                story = episode.story
```

Replace with (the docstring says this guards Episode and Chapter objects — an Episode has `.chapter.story`, a Chapter has `.story`):

```python
        if isinstance(obj, Story):
            story = obj
        elif isinstance(obj, Episode):
            story = obj.chapter.story
        else:
            # Chapter (or anything else exposing .story).
            story = obj.story
```

Ensure `Episode` is imported in `permissions.py` (grep; the file already imports `Story` — add `Episode` to the same `from world.stories.models import …` line if absent).

**Step 2:** `uv run ruff check src/world/stories/permissions.py`

**Step 3:** `echo "yes" | uv run arx test world.stories.tests.test_view_actions_permissions` — expected: all pass (behavior unchanged: Episodes and Chapters still resolve to the same story; the removed branch was unreachable).

**Step 4: Commit** `refactor(stories): isinstance-route IsLeadGMOnStoryOrStaff; drop dead branch [ledger (b)]`

---

### Task 3: (c) Soften the `_collect_gm_queue` docstring ("byte-identical" → accurate)

**Files:**
- Modify: `src/world/stories/views.py:2083-2092`

**Step 1:** Replace the final sentence of the `_collect_gm_queue` docstring. Current last line:

```
    many stories the GM leads. The produced buckets are byte-identical to the
    old loop's output (response shape/keys/values/order unchanged).
```

Replace with (mirrors the accurate wording already in `_first_active_progress_by_story` / `_collect_per_gm_queue_depth`):

```
    many stories the GM leads. The produced buckets are set-identical to the
    old loop's output (response shape/keys/values unchanged); intra-GROUP
    progress is now deterministically pk-ordered where the old ``.first()``
    returned an unspecified DB order, so no test asserts that ordering.
```

**Step 2:** `uv run ruff check src/world/stories/views.py` and `uv run ty check src/world/stories/views.py` (docstring-only; must stay green).

**Step 3: Commit** `docs(stories): soften _collect_gm_queue docstring to set-identical [ledger (c)]`

---

### Task 4: (d) Replace raw `status="active"` literals with `StoryStatus.ACTIVE`

**Files:**
- Modify: `src/world/stories/views.py` import block, lines `2099` and `2253`
- Test (existing, must stay green): `src/world/stories/tests/test_views_gm_queue.py`, `src/world/stories/tests/test_views_staff_workload.py`

**Step 1: Add the import.** `StoryStatus` is in `world.stories.types` (NOT constants). `views.py` already imports `from world.stories.types import (AnyStoryProgress, …)` — add `StoryStatus` to that existing parenthesised import, keeping alphabetical order.

**Step 2: Replace both literals.** In `_collect_gm_queue` (~line 2099):

```python
        Story.objects.filter(
            primary_table__gm=gm_profile,
            status=StoryStatus.ACTIVE,
        ).distinct()
```

In `_build_staff_per_gm_inputs` (~line 2253):

```python
        Story.objects.filter(
            primary_table__gm__isnull=False,
            status=StoryStatus.ACTIVE,
        )
```

`StoryStatus.ACTIVE == "active"` (verified) so the query is byte-identical.

**Step 3:** `uv run ruff check src/world/stories/views.py` and `uv run ty check src/world/stories/views.py`.

**Step 4:** `echo "yes" | uv run arx test world.stories.tests.test_views_gm_queue world.stories.tests.test_views_staff_workload` — expected: all pass including the `assertNumQueries` locks (no query change).

**Step 5: Commit** `refactor(stories): StoryStatus.ACTIVE over raw "active" literal [ledger (d)]`

---

### Task 5: (M-2) Security comment on the Create serializers (ungated echo is deliberate)

**Files:**
- Modify: `src/world/stories/serializers.py` — `StoryCreateSerializer` (~233), `ChapterCreateSerializer` (~333), `EpisodeCreateSerializer` (~417)

**Step 1:** Add a comment directly above the `class Meta:` `fields` list in each of the three Create serializers. Use exactly this wording (adjust the field list per serializer):

`StoryCreateSerializer` (fields include `description`, `summary`):
```python
        # SECURITY (deliberate exception to the A3 _gm_text_gate): the
        # create serializers echo `description` / `summary` UNGATED. Safe
        # today: Story-create is staff-only and Chapter/Episode-create echo
        # only the requester's own just-submitted text — no third-party GM
        # text is disclosed. If a future change lets a non-staff user create
        # a node from someone else's draft, add gating here.
```

`ChapterCreateSerializer` (`description`, `summary`) — same comment.

`EpisodeCreateSerializer` (`description`, `summary`, `resting_conclusion`, `is_ending`) — same comment but name all four: `description` / `summary` / `resting_conclusion` / `is_ending`.

**Step 2:** `uv run ruff check src/world/stories/serializers.py`

**Step 3: Commit** `docs(stories): document deliberate ungated echo on create serializers [ledger M-2]`

---

### Task 6: (M-1) Treat Story owners as privileged in `_gm_text_gate`

A non-staff Story *owner* who is not the lead GM currently cannot read back their own GM `description`/`consequences` after a PATCH (friction, not a leak). Add owners to the privileged set in the gate.

**Files:**
- Modify: `src/world/stories/serializers.py` — `_gm_text_gate` (127-166, the `if role not in (...)` block)
- Test: `src/world/stories/tests/test_serializers_visibility_split.py` (add a test)

**Step 1: Write the failing test** in `test_serializers_visibility_split.py` (mirror the existing test class's factories/setup — read the file first; use `setUpTestData`, evennia_extensions factories, never `create_object` directly):

```python
def test_story_owner_sees_gm_text_on_own_pitch_story(self):
    """A non-staff, non-lead-GM owner of a PITCH story still sees
    description and a non-blanked summary on the detail endpoint."""
    # story owned by a plain account (not staff, not the primary_table GM),
    # maturity=PITCH, description + summary populated.
    # Authenticate as that owner; GET the story detail.
    # assert response.data["description"] == <the GM text>
    # assert response.data["summary"] == <the summary, NOT "">
```

**Step 2:** `echo "yes" | uv run arx test world.stories.tests.test_serializers_visibility_split` — expected: the new test FAILS (owner currently treated as player → description popped, summary blanked).

**Step 3: Implement.** In `_gm_text_gate`, after `role = (... classify_story_log_viewer_role ...)`, change the privilege check. Current:

```python
    if role not in (VIEWER_ROLE_STAFF, VIEWER_ROLE_LEAD_GM):
        data.pop("description", None)
        data.pop("consequences", None)
        if node_maturity == StoryMaturity.PITCH:
            data["summary"] = ""
    return data
```

Replace with (owner of this story is privileged for their own story's GM text):

```python
    is_owner = (
        user is not None
        and getattr(user, "is_authenticated", False)  # noqa: GETATTR_LITERAL — AnonymousUser safe
        and story.owners.filter(pk=user.pk).exists()
    )
    if role not in (VIEWER_ROLE_STAFF, VIEWER_ROLE_LEAD_GM) and not is_owner:
        data.pop("description", None)
        data.pop("consequences", None)
        if node_maturity == StoryMaturity.PITCH:
            data["summary"] = ""
    return data
```

(`story.owners` is a M2M to AccountDB — verified; `user` is the AccountDB. One `.exists()` query, only on the non-staff/non-lead path.)

**Step 4:** `echo "yes" | uv run arx test world.stories.tests.test_serializers_visibility_split` — expected: new test PASSES, all existing visibility tests still PASS (player/no-access/no-request still gated; staff/lead-GM unchanged).

**Step 5:** `uv run ruff check src/world/stories/serializers.py`

**Step 6: Commit** `fix(stories): story owners see their own GM text via _gm_text_gate [ledger M-1]`

---

### Task 7: (e) Expose the true `ProgressStatus` on the my-active payload; banner consumes it

The `ProgressStateBanner` reads `StoryEpisodeStatus` (`on_hold` proxy) and cannot distinguish WAITING_FOR_GM vs RESTING. All three progress models have `status` (`ProgressStatus`, default ACTIVE). Add it to the only payload the banner consumes (`GET /api/stories/my-active/`) — NOT a new serializer/endpoint (YAGNI).

**Files:**
- Modify: `src/world/stories/types.py` — `MyActiveStoryEntry` TypedDict
- Modify: `src/world/stories/views.py` — `_serialize_progress_entry` (~1637-1661)
- Modify: `frontend/src/stories/types.ts` — `MyActiveStoryEntry` interface (~137-153)
- Modify: `frontend/src/stories/components/ProgressStateBanner.tsx`
- Test: `src/world/stories/tests/test_views_my_active.py`; `frontend/src/stories/__tests__/ProgressStateBanner.test.tsx`

**Step 1: Backend failing test** — in `test_views_my_active.py` add an assertion (read the file; extend the existing happy-path test or add one) that each entry carries `progress_status` equal to the progress row's `.status`, and that a WAITING_FOR_GM progress yields `"progress_status": "waiting_for_gm"`.

**Step 2:** `echo "yes" | uv run arx test world.stories.tests.test_views_my_active` — expected: FAIL (`KeyError`/missing `progress_status`).

**Step 3: Backend implement.**
- `src/world/stories/types.py`: add `progress_status: str` to `MyActiveStoryEntry` (with a `# ProgressStatus value` comment, mirroring the existing `status` comment).
- `src/world/stories/views.py` `_serialize_progress_entry`: add `"progress_status": progress.status,` to the returned dict.

**Step 4:** `echo "yes" | uv run arx test world.stories.tests.test_views_my_active` — expected: PASS. Then `uv run ty check src/world/stories/views.py` (literal must still match the TypedDict — direct `return {...}` is fine).

**Step 5: FE failing test** — in `ProgressStateBanner.test.tsx` (read it first; mirror its render/mock harness) add a case: a dashboard entry with `progress_status: 'waiting_for_gm'` renders the **attention** treatment, and one with `progress_status: 'resting'` renders the **muted** treatment, even when `status` (StoryEpisodeStatus) is the same value for both.

**Step 6:** `pnpm -C frontend test -- --run src/stories/__tests__/ProgressStateBanner.test.tsx` — expected: FAIL.

**Step 7: FE implement.**
- `frontend/src/stories/types.ts`: add `progress_status: string;` to `MyActiveStoryEntry` with a `/** ProgressStatus value: active|waiting_for_gm|resting|completed */` doc comment.
- `ProgressStateBanner.tsx`: when the matched entry has `progress_status`, derive `BannerState` from it FIRST (`waiting_for_gm → 'attention'`, `resting → 'muted'`, `completed → 'muted'`, `active →` fall through to the existing `STATUS_TREATMENT[status]` logic), keeping the existing `STATUS_TREATMENT` map as the fallback. Update the component docstring's "DATA SOURCE" note to record that `progress_status` is now the authoritative pointer state (the `on_hold` proxy is now only the ACTIVE-state refinement).

**Step 8:** `pnpm -C frontend test -- --run src/stories/__tests__/ProgressStateBanner.test.tsx` — expected: PASS. Then `pnpm -C frontend build` (real gate) — expected: clean.

**Step 9: Commit** `feat(stories): expose ProgressStatus on my-active; banner distinguishes waiting/resting [ledger (e)]`

---

### Task 8: (M-3) Guard `.join` on `character_sheet`/`gm_table` in `ScopeAssignDialog`

**Files:**
- Modify: `frontend/src/stories/components/ScopeAssignDialog.tsx:136-163`
- Test: `frontend/src/stories/__tests__/ScopeAssignDialog.test.tsx`

**Step 1: Write the failing test** — add a case driving `handleError` with a 400 whose body is `{ "character_sheet": "CHARACTER scope requires a character_sheet." }` (a **bare string**, as the backend emits) and assert the inline error shows that string verbatim (no crash). With the current unguarded `body.character_sheet?.join(' ')`, calling `.join` on a string throws inside `.then()` → `.catch()` degrades to the generic message; the test asserting the verbatim message FAILS.

**Step 2:** `pnpm -C frontend test -- --run src/stories/__tests__/ScopeAssignDialog.test.tsx` — expected: FAIL (generic message, not the server string).

**Step 3: Implement.** Replace the message-derivation block so `character_sheet`/`gm_table`/`non_field_errors` use the same `Array.isArray` guard the `scope` key already uses:

```typescript
              const body = data as AssignDRFError;
              const pick = (v: string | string[] | undefined): string | undefined =>
                Array.isArray(v) ? v.join(' ') : v;
              const message =
                pick(body.scope) ||
                pick(body.character_sheet) ||
                pick(body.gm_table) ||
                pick(body.non_field_errors) ||
                body.detail ||
                'Assignment failed. Please try again.';
              setInlineError(message);
```

Widen the `AssignDRFError` field types to `string | string[]` for `scope`, `character_sheet`, `gm_table`, `non_field_errors` (the backend emits bare strings for the manual combo/re-assign errors and arrays for DRF PK-list errors).

**Step 4:** `pnpm -C frontend test -- --run src/stories/__tests__/ScopeAssignDialog.test.tsx` — expected: PASS. `pnpm -C frontend build` — clean.

**Step 5: Commit** `fix(stories-fe): Array.isArray-guard ScopeAssignDialog error fields [ledger M-3]`

---

### Task 9: (I-A twin) `markBeat` attaches the failed `.response`

`MarkBeatDialog.onError` reads `'response' in err` then `err.response.json()` — but `api.markBeat` throws a plain `Error` with no `.response`, so that branch is dead and server field errors never surface.

**Files:**
- Modify: `frontend/src/stories/api.ts:504-512` (`markBeat`)
- Test: `frontend/src/stories/__tests__/MarkBeatDialog.test.tsx`

**Step 1: Write the failing test** — mirror the real-contract pattern from `queries.authoring.test.tsx` (per the I-A fix). Drive `MarkBeatDialog` (or `markBeat` directly through the dialog's mutation) against a mocked 400 whose body is a DRF field-error object; assert the dialog renders the field error (i.e. `onError`'s `response.json()` branch ran). Currently FAILS (dead branch → generic toast).

**Step 2:** `pnpm -C frontend test -- --run src/stories/__tests__/MarkBeatDialog.test.tsx` — expected: FAIL.

**Step 3: Implement** — change `markBeat`'s error path to mirror `promoteEpisode`/`saveTransitionWithOutcomes` exactly:

```typescript
  if (!res.ok) {
    // Preserve the response so MarkBeatDialog can surface field errors.
    const err = new Error('Failed to mark beat') as Error & {
      response?: Response;
    };
    err.response = res;
    throw err;
  }
  return res.json() as Promise<BeatCompletion>;
```

**Step 4:** `pnpm -C frontend test -- --run src/stories/__tests__/MarkBeatDialog.test.tsx` — expected: PASS. `pnpm -C frontend build` — clean.

**Step 5: Commit** `fix(stories-fe): markBeat attaches failed .response for MarkBeatDialog [ledger I-A twin]`

---

### Task 10: Final regression, ledger update, push, PR

**Step 1: Update the ledger.** In `docs/plans/2026-05-15-stories-authoring-framework-design.md` §"stories-authoring-api-ui — discovered follow-ups (2026-05-17)", mark (a),(b),(c),(d),(e) and M-1,M-2,M-3 and the I-A twin as **RESOLVED by feature/stories-authoring-cleanup** with a one-line note each (matching the existing "RESOLVED by the stories-authoring-api-ui branch" annotation style).

**Step 2: Lint/type sweep:** `uv run ruff check src/world/stories/` ; `uv run ruff format --check src/world/stories/` ; `uv run ty check src/world/stories/views.py`.

**Step 3: Full backend regression (fresh DB — matches CI):** `echo "yes" | uv run arx test world.stories` (NO `--keepdb`). Expected: `OK`. If wall-clock risk, run in background and wait for completion (do not poll with sleep loops).

**Step 4: FE gate:** `pnpm -C frontend test -- --run src/stories` then `pnpm -C frontend build` (tsc -b + vite — the real gate; typecheck alone is insufficient). Expected: all green.

**Step 5: Commit the ledger** with `-f` (docs/plans is gitignored): `git -C <repo> add -f docs/plans/2026-05-15-stories-authoring-framework-design.md docs/plans/2026-05-17-stories-authoring-cleanup.md` then `git -C <repo> commit -m "docs(stories): mark cleanup ledger items resolved"` (+ Co-Authored-By trailer).

**Step 6: Adversarial review** — REQUIRED SUB-SKILL: superpowers:requesting-code-review. Dispatch the code-reviewer over `origin/main..HEAD` for the whole branch. The review prompt MUST explicitly include the query-count / SharedMemoryModel-identity-map angle (the `story.owners.filter(...).exists()` added in Task 6 and the `progress.status` access in Task 7 are the only new query surfaces — confirm they add no per-row query and don't regress the `assertNumQueries` locks). Fix Critical/Important before pushing.

**Step 7: Push** `git -C <repo> push -u origin feature/stories-authoring-cleanup`. Report the branch + a PR summary for manual PR creation (no `gh` CLI; PRs via GitHub web). Then superpowers:finishing-a-development-branch.

---

## Out of scope (do NOT build)

- The big sequenced follow-ups (Mission/Challenge engine, Situation/Encounter+Sessions, Consequence/reward computation, GM leveling, Covenant entity) — each is its own brainstorm (framework-design §10).
- Any schema/migration change (every field used here already exists).
- Reworking `compute_story_status` / `StoryEpisodeStatus` — Task 7 only *adds* the authoritative `progress_status` alongside it; it does not replace the existing proxy plumbing.
- Per-DAG-reachability frontier refinement (framework-design discovered-follow-up #4) — deferred, design-bearing.
