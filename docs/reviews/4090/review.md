# Review evidence

- Reviewed revision: `c89d7763167b3e8c594e5f0695bdf1d50cce97f2`
- Revision note: screenshots were taken at `ec5ecde90`. The three later commits (`4d244bf75`, `757aa76fb`, `c89d77631`) change no rendered surface: a row lock in the two breakthrough purchase services, a query-cache invalidation in `progression/queries.ts`, and tests. The controller checked the diff (`git diff --stat ec5ecde90 c89d77631`) before restamping.
- Reviewer: `demo-fidelity-reviewer` (local agent pass, dispatched before PR open on #4090)
- Reviewer verdict: PASS
- Application/build identity: real production bundle (`pnpm build` against this revision, served by `vite preview`/`vite dev`) rendered by real Chromium (Playwright); Django admin rendered via the real `admin.site` through the Django test client (same `ModelAdmin` classes, same URLconf production uses)
- Environment: devcontainer, headless Chromium (Playwright `@playwright/test` 1.58), SQLite-backed Django test client for admin
- Viewports/themes: 1024x768 (sheet), 900x700 (scene feed), default light theme (`data-theme` unset; the app's own `:root` tokens, same tokens `sheet.css`/`index.css` ship) — no dark-theme pass (see Unresolved findings)
- Approved design: https://claude.ai/artifact/LrpfjQQnxb8qDbaoyMx5tR — read in full via the `Artifact` tool at session start (not re-fetched a second time this pass; the saved local copy at `/tmp/claude-1000/-workspaces-arxii/aa2316ee-f3ed-4bc8-9c71-a19ac0fc7bf2/scratchpad/demo-4090.html` is the exact file that read saved, used below to render reference screenshots of the demo itself for a true image-to-image comparison)
- Visual review: completed. Two real renders were produced and compared at the element level by this reviewer's own vision: (1) the demo's own HTML/CSS, screenshotted directly from the saved artifact file via headless Chromium — `docs/reviews/4090/images/demo-screen{1,2,3}-reference.png`; (2) the branch's real built React app (character sheet) and real built React app (live game feed), driven through mocked `/api/**` + a mocked game WebSocket with the real component tree, no component stubbing beyond the network boundary — `docs/reviews/4090/images/screen*.png`. The Django admin authoring surfaces named in the demo's own "How the example is authored in admin" section are a **text table in the demo, not a visual mockup** (the demo draws no admin screenshot to compare against); that screen was verified by rendering the real admin add-forms via the Django test client and confirming the exact field names the demo's table cites appear in the rendered HTML — a render-existence check, not an image-to-image visual comparison, and is called out as such in that screen's section below rather than silently folded into the PASS.
- Visual verdict: PASS
- Screenshots: ![Screen 1, before the cast](docs/reviews/4090/images/screen1-before-cast.png) ![Screen 1, after a strong cast](docs/reviews/4090/images/screen1-after-strong-cast.png) ![Screen 2, after a weaker cast](docs/reviews/4090/images/screen2-weaker-cast.png) ![Screen 3, while the effect lasts](docs/reviews/4090/images/screen3-while-effect-lasts.png) ![Screen 3, after the effect ends](docs/reviews/4090/images/screen3-after-effect-ends.png) ![Demo Screen 1 reference](docs/reviews/4090/images/demo-screen1-reference.png) ![Demo Screen 2 reference](docs/reviews/4090/images/demo-screen2-reference.png) ![Demo Screen 3 reference](docs/reviews/4090/images/demo-screen3-reference.png)
- Comparison notes: see the screen-by-screen section below
- Tested interactions: scene feed — a pose delivered live over the mocked game WebSocket (always readable); a language-tagged `say` delivered fully garbled (`"..."`, zero comprehension), delivered clear (full sentence, raised comprehension), and delivered half-garbled (conversational-band comprehension); a cast-outcome (`mode: outcome`) narrator line rendered between two says. Character sheet — opening the real `/characters/:id` route, selecting the "Growth" section tab (a real click, not a mocked section), and reading the real `LanguagesSection` component's render of a condition-only row, a condition-plus-trained row, and the same rows after the condition's `temporary_sources` empties out. Admin — a real Django test-client `GET` of the `ConditionTemplate` and `Technique` admin add-forms (unauthenticated-then-superuser-login flow), reading the actual rendered input/select field names of the live inline formsets.
- Fixture/live boundary: every screenshot's `content`/`line` text and every `MyLanguage` row is a **hand-built fixture fed over a mocked `/api/**` route or a mocked WebSocket frame** — this reviewer did not run the real `comprehension_value`/`garble_text`/`render_line` pipeline end-to-end through a live Django backend inside a browser. What the fixtures prove is that the REAL rendering components (`PoseUnit`, `ActorLine`, `LanguagesSection`, `Glance`/`Tag` primitives, `sheet.css`) draw whatever comprehension/garble text they are given in the exact shape and style the demo specifies. What the fixtures do NOT independently prove visually is that the backend computes the RIGHT garble ratio / comprehension value / live-recompute-on-reread for a given condition — that half is verified by reading the diff against the cited line numbers below and by running the backend test suites specified in the spec's own "Test seams" section, all green on this revision (`world.species` 151 tests, `world.species.tests.test_language_comprehension` 19, `world.species.tests.test_language_progression` 24, `world.scenes.tests.test_language_interactions` 19, `world.conditions.tests.test_condition_modifier_totals` 9, `world.magic.tests.test_condition_power_eval`/`test_technique_power_eval_valuators`/`test_condition_application`/`test_team_damage_percent_lane` 52, `actions.tests.test_language_actions`/`test_language_speech`/`test_progression` + `commands.tests.test_progression_commands` + `actions.tests.test_gm_adjudication_actions` 197, `web.admin.tests.test_config_table_admins` 1 — all OK, SQLite fast tier). The admin screenshots are entirely server-rendered HTML from a SQLite Django test database with no seeded content rows (no `ModifierTarget`/`ConditionTemplate` rows for a real language exist in this test run — the "25 languages, no modifier target yet" state the spec itself describes); the admin check therefore verifies the FORM exists and offers the right fields, not that any content has been authored yet.
- Overall outcome: PASS

## Approved-design reference

Demo URL (issue-cited, read via `Artifact` tool this session):
`https://claude.ai/artifact/LrpfjQQnxb8qDbaoyMx5tR`

Issue #4090's spec block cites this URL at the top ("Demo (the approved design)")
and again in the Walkthrough section, and Decision 11 states "The demo is the
approved design." The saved local copy (`demo-4090.html`, read in full at session
start, not just its head) is treated below as the demo's content and is also used
to render true reference screenshots of the demo's own three screens
(`images/demo-screen{1,2,3}-reference.png`), rather than comparing the branch only
against a description of the demo.

## Environment / render method

- Frontend build: `pnpm build` at this revision (succeeded, `vite build` + `postbuild` collectstatic), served by `vite preview --port 4173` (default `playwright.config.ts`, the same config `ties.spec.ts` uses — production bundle, same as Django/TwistedWeb serves).
- Character sheet (Screen 3): a throwaway Playwright spec (`frontend/e2e/demo-4090-tmp.spec.ts`, written this pass, run, screenshots captured, then **deleted** — `git status --short` in the worktree is clean of it) navigated to the real `/characters/1` route with `/api/**` mocked (account, roster, character-sheet payload, `/api/species/my-languages/`) exactly in the shape `ties.spec.ts`'s `mockApi` already established as this repo's own demo-fidelity-evidence pattern, clicked the real "Growth" tab button, and screenshotted the real `<Heading>Languages</Heading>` + `<LanguagesSection/>` DOM node.
- Scene feed (Screens 1-2): the same throwaway spec reused this repo's existing `frontend/e2e/support/gameHarness.ts` (`mockRestRoutes`, `reachReadySession` — the harness `feed-sentences.spec.ts`/`feed-chips.spec.ts` already use for this exact class of review), which drives a real `/game` session to "In world" over a mocked WebSocket, then pushed `interaction` WS frames with `mode: 'pose'|'say'|'outcome'` and hand-set `content`/`line` text matching the demo's three states (zero comprehension, raised comprehension, conversational-band comprehension), and took full-page screenshots.
- Admin: a throwaway Django test method (`src/web/admin/tests/test_4090_tmp_render.py`, written, run via `just test-fast web.admin.tests.test_4090_tmp_render`, HTML dumped to `/tmp`, read, then **deleted** along with the dumped HTML) logged in as a superuser and `GET`'d `admin:arxii_conditiontemplate_add` and `admin:arxii_technique_add`.
- Backend logic: verified by reading the diff against `src/world/species/language_services.py`, `src/actions/definitions/communication.py`, `src/world/scenes/interaction_services.py`, `src/world/scenes/interaction_serializers.py`, `src/world/magic/services/de_valuation.py`, `src/world/magic/services/technique_power_eval.py`, `src/world/species/language_progression.py`, `src/actions/definitions/language.py`, and by running every SQLite fast-tier test path the spec's own "Test seams" section names (all green, counts above).
- Fixture-vs-live boundary: every frontend screenshot is fixture-driven (mocked REST/WebSocket). Every admin screenshot is a real Django admin add-form against a real (empty) SQLite test database — real Django/real `ModelAdmin`, fixture-free. No full end-to-end pass (a real cast, against a real backend, rendered live in a browser) was performed this review — see Unresolved findings.

## Screen 1 · scene feed · a strong cast turns garbled speech clear

Demo shows (`images/demo-screen1-reference.png`): two side-by-side feed panels.
Left, "Before the cast" — a readable pose from Envoy (bold name, avatar "EN",
timestamp), then a `say` that reads `Envoy says in Tongue A, "..."` for a listener
with zero fluency. Right, "After a strong cast" — the same pose, the SAME 8:15 say
now reading the full sentence clear, an italic Narrator outcome line ("Wren casts
Interpreter's Charm: Excellent Success."), then a new clear say at 8:17.

Branch renders (`images/screen1-before-cast.png`, `images/screen1-after-strong-cast.png`):
the real `PoseUnit`/`ActorLine` components, driven over the mocked `/game` WebSocket,
produce byte-identical structure: bold actor name leading the body text (`ActorLine`,
`frontend/src/scenes/components/ActorLine.tsx:20-31`), a muted rounded bubble per
row (`my-1.5 max-w-[85%] rounded-lg bg-muted/40 px-3 py-2`,
`frontend/src/scenes/components/PoseUnit.tsx:480`) — the exact Tailwind classes the
demo's own CSS comments cite verbatim, confirming the demo artist drew directly
from this component rather than inventing new classes. The garbled say renders
literally `Envoy says in Tongue A, "..."`; the clear say renders the full sentence;
the outcome line renders in the demo's exact italic/muted style with no avatar or
header (`PoseUnit.tsx:421`, `mode === 'outcome'` branch).

`garble_text(text, keep_ratio=0.0)` returns the literal string `"..."`
(`src/world/species/language_services.py:30-31`), and `render_line` builds
`f'{name} {verb}{spoken_in}, "{content}"'` (`src/world/scenes/line_rendering.py:68-70`)
— `Envoy says in Tongue A, "..."` word-for-word, confirmed by direct read rather than
assumed. The pose row carries no `language`, so it is never garbled
(`src/actions/definitions/communication.py` — `PoseAction` never calls
`_resolve_spoken_language`), matching the demo's map item 1 and the new garble-scope
test cited in the spec.

The demo's `.garble`/`.clear-word` CSS classes exist only on the demo page itself
(decorative spans on its own illustrative markup) — the real backend returns plain
text with literal `...` substitutions and the real frontend renders it as plain
text with no extra color/markup for the garbled portion specifically. This is NOT
a gap: nothing in the spec's Decisions, Walkthrough, or demo map items calls for a
distinct visual treatment of the garbled words themselves (only that they read as
`...`), and the demo's own map items never cite a `.garble`-equivalent requirement
as `in spec`. Noted, not flagged.

Comparison: matches, including the exact actor-name-bold / bubble / outcome-italic
idiom the demo describes.

Verdict: MATCHES.

## Screen 2 · scene feed · a weaker cast leaves gaps, and the effect ends

Demo shows (`images/demo-screen2-reference.png`): left, "After a weaker cast" — the
same say half-garbled (`"The north ... opens at ... second bell, so ... the lamp
oil ... your hood up."`), an outcome line reading "Success" (not "Excellent
Success"). Right, "Scene finished, log reread" — the scene has ended, the condition
swept, and every previously-clear say now reads `"..."` again on reread; the pose
and outcome line stay untouched.

Branch renders (`images/screen2-weaker-cast.png`): the half-garbled say and
"Success" outcome line render exactly as fixtured, in the same bubble/outcome
idiom confirmed on Screen 1. `BAND_KEEP_RATIO`/`fluency_band` decide the keep ratio
by comprehension band (`src/world/species/language_constants.py`, read via
`language_services.py` imports); `garble_text`'s seeded RNG
(`speech_seed`/`zlib.crc32`, `language_services.py:51-53`) is deterministic per
line, matching the demo's "every channel drops the same words" claim.

**Not independently screenshotted this pass: the right panel ("Scene finished, log
reread").** This is the `SceneDetailPage` reread surface
(`frontend/src/scenes/pages/SceneDetailPage.tsx`), which pulls in combat, rituals,
GM-adjudication, and a dozen other cross-cutting panels; standing up a faithful
mock for it was judged disproportionate to this review's scope and was not
attempted, rather than attempted and silently passed. That surface's correctness —
old lines garbling again once the condition's `DurationType.SCENE` sweep removes it
— is verified instead by direct code read (`_comprehension_map`/
`_comprehension_for_sheet`, `interaction_serializers.py:596-617`, calling the SAME
`comprehension_values` the live path calls, "Controller ruling F2" per its own
docstring — never a parallel re-derivation) and by
`world.scenes.tests.test_language_interactions` (19 tests, green) and
`world.conditions.tests.test_condition_modifier_totals` (9 tests, green), which the
spec's own "Test seams"/"Testing" sections name as the oracle for this exact
journey (condition applied -> reread clear -> scene ends -> reread garbled again,
Decision 2). This is disclosed as a scope limitation, not inferred as a visual
pass.

Comparison: left panel matches on rendering; right panel's garble-again-on-reread
behavior is source/test-verified only, not visually screenshotted this pass.

Verdict: MATCHES WITH NOTED GAP (left panel visually confirmed; right panel code/test-verified only, not screenshotted).

## Screen 3 · character sheet, Languages · the temporary level is marked and named

Demo shows (`images/demo-screen3-reference.png`): left, "While the effect lasts" —
`Common (speaking): Fluent`; `Tongue A: Fluent [Temporary] / from Understood
Tongue` (no trained text at all — a condition-only row); `Tongue B: Fluent
[Temporary] / from Understood Tongue · trained Broken` (a trained row the
condition raised). Right, "After the effect ends" — `Common (speaking): Fluent`;
`Tongue B: Broken`; Tongue A is gone entirely.

Branch renders (`images/screen3-while-effect-lasts.png`,
`images/screen3-after-effect-ends.png`), the REAL `LanguagesSection` component
mounted at the real `/characters/1` route, "Growth" tab, fed the exact `MyLanguage`
rows the demo's caption describes: pixel-for-pixel the same three-row structure,
the same "Temporary" accent tag, the same gloss text, down to the exact punctuation
(`· trained Broken`) and the exact omission of "trained" text on the condition-only
row. The after-effect screenshot drops Tongue A and returns Tongue B to `Broken`,
matching the demo's right panel exactly.

This is the one screen where the spec's own Decision 6 text ("trained none") and
the shipped behavior diverge, by instruction in this review's dispatch: a
controller ruling (Q1 on #4090 Task 11) overrode Decision 6's literal wording to
match the demo, which the code's own comment confirms verbatim:
`frontend/src/character_sheets/components/LanguagesSection.tsx:16-24` — "a
condition-only row (no trained fluency at all) just names the condition, with no
'trained' text (Ruling Q1 on #4090 Task 11 — matches the approved demo, Screen
3)." This is a ratified, cited divergence-that-the-build-got-right, not a defect,
per this review's own dispatch instructions and is not re-litigated here.

Styling check (CSS "reaches the page," not "class name appears somewhere"): the
two new rules this feature needs — `.refsheet-glance .refsheet-tag` (tag margin
and vertical alignment) and `.refsheet-gloss` (the muted, smaller gloss line) —
live in `frontend/src/character_sheets/sheet.css:529-536`
(`git diff origin/main...HEAD`), and `sheet.css` is imported directly by
`CharacterSheetPage.tsx:29` (`import '@/character_sheets/sheet.css';`), the exact
page this feature renders on — not an inline partial for a different page, not a
stylesheet linked only from a template this page never extends. Confirmed two
ways: (1) the real screenshots above show the tag positioned and sized as the demo
specifies, and (2) a committed unit test
(`frontend/src/character_sheets/components/LanguagesSection.test.tsx`, "reaches
the Temporary tag and the gloss with a real sheet.css rule, not just a class
name") parses `sheet.css`'s actual rule selectors and asserts the rendered
`Temporary` tag element and gloss element both match a real selector from that
file — the mechanical companion to this exact finding shape, already built in
this diff rather than left for this review to propose.

Comparison: matches on structure, wording, punctuation, and styling.

Verdict: MATCHES.

## Screen 4 · what finalize writes

No new model, no migration (`src/world/migrations/0193_languagetrainingconfig_and_more.py`
only adds the Amendment's `LanguageTrainingConfig` singleton, not a language-row
model) — matches the demo's own "No new model and no migration" caption. Every row
in the demo's table was verified against the diff: `Interaction` (outcome) via
`create_cast_outcome_pose` (pre-existing, unchanged); `ConditionInstance` via
`apply_technique_conditions` (pre-existing, unchanged); `Interaction` (say)
unchanged; `MyLanguageRow` (read, not stored) extended with `effective_fluency`,
`effective_band`, `temporary_sources` (`src/world/species/types.py`, confirmed in
`frontend/src/generated/api.d.ts:35010-35019`); listener comprehension (read, not
stored) is the new `comprehension_value`/`comprehension_values`
(`src/world/species/language_services.py:68-100`), batched via `_fluency_map` as
documented above.

Verdict: MATCHES (verified against code; this screen is a data table, not a visual surface).

## Admin · how the example is authored in admin

The demo's own ADMIN section (and the Walkthrough's admin reference) is a **text
table describing model/field mappings, not a visual mockup** — there is no admin
screenshot in the demo to compare pixels against. What follows is therefore a
render-existence check (did staff actually get these fields, as named), not an
image-to-image visual comparison, consistent with this report's Visual review
disclosure above.

| Demo row | Verified |
|---|---|
| `ModifierCategory` "language" | Admin registered, pre-existing, unchanged this PR (`src/world/mechanics/admin.py:41-42`) |
| `ModifierTarget` per language (`target_trait`) | Admin registered, pre-existing, unchanged this PR (`src/world/mechanics/admin.py:55-56`) |
| `ConditionTemplate` + inline `ConditionModifierEffect` (`modifier_target`, `value`, `scales_with_severity`) | Pre-existing, unchanged this PR (`src/world/conditions/admin.py:87-104, 257-265`). Rendered live this pass: `GET admin:arxii_conditiontemplate_add` returned 200 and the rendered HTML contains `id_conditionmodifiereffect_set-__prefix__-modifier_target`, `-value`, `-scales_with_severity`, `-stage` — the inline genuinely reaches the page, not just registered |
| `Gift` (Minor kind) | Pre-existing, unchanged this PR |
| `Technique` + inline `TechniqueAppliedCondition` (`condition`, `minimum_success_level`, `base_severity`, `severity_per_extra_sl`) | Pre-existing, unchanged this PR (`src/world/magic/admin.py:312-325, 521`). Rendered live this pass: `GET admin:arxii_technique_add` returned 200 and the rendered HTML contains `condition_applications-__prefix__-condition`, `-base_severity`, `-severity_per_extra_sl`, `-minimum_success_level` |
| Pricing exclusion shown as "not combat power" | New this PR, verified by diff + green tests: `src/world/magic/services/de_valuation.py:187-215, 285-292`, `src/world/magic/types/technique_power.py:38-49,105,119-120`, designated by `target_trait.trait_type == TraitType.LANGUAGE`, never by name |
| `LanguageTrainingConfig` singleton (Amendment) | New this PR, admin registered (`src/world/species/admin.py`), Tuning-tier `required_content.py` entry added, rendered live via the repo's own generic admin-smoke test (`web.admin.tests.test_config_table_admins`, green, 1 test covering both changelist and add-form for this model) |

Verdict: MATCHES (render-existence verified for every row the demo's table names; no visual mockup exists for this screen to compare against — disclosed, not inferred).

## Variety within one container / Scenarios through the shape / Levers / Shape

These sections are the demo's own worked examples and "holds"/"adds" verdicts on
hypothetical content (Interpreter's Charm, Gift of Every Tongue, Borrowed Ears,
Slow Understanding), not a screen the branch renders — they describe how the one
mechanism (`ConditionModifierEffect` toward a language's `ModifierTarget`) covers
each case. Spot-checked against code: the "stages" row (Slow Understanding) —
"the fold counts effects on the condition's current stage" — matches
`comprehension_values`' use of the condition's current stage via the same
`get_condition_modifier_total`-style walk `ConditionModifierEffectInline`/
`ConditionStageInline` already support (`src/world/conditions/admin.py:75-104`).
The "No bulk admin action" row (Decision 5, this review's named ruled-divergence)
correctly has no code anywhere in the diff adding one — confirmed by `git diff
origin/main...HEAD --stat` showing no new admin action in `conditions/admin.py` or
`species/admin.py`.

Verdict: N/A (not a rendered screen; spot-checked against code, no divergence found).

## Divergences the build got right

1. **Decision 6's literal "trained none" text vs. the demo's bare "from
   <Condition>" with no trained text at all** — overridden by controller ruling Q1
   on #4090 Task 11, per this review's own dispatch instructions and the code
   comment cited in the Screen 3 section above. The build matches the DEMO here,
   correctly, not the spec's literal Decision-6 prose.
2. **No "new this round" bulk-add admin action** (spec Decision 5) — the demo drew
   one as a "new this round" idea; the ratified spec explicitly rejected it
   ("Existing inline suffices"). No code anywhere in the diff adds one. Correct.
3. **Modifier numbers are examples** (+20 per severity, 15/8 dp per session, etc.)
   — per this review's dispatch instructions, these are never gated; the real
   values are staff-authored in admin (`ConditionModifierEffect.value`,
   `LanguageTrainingConfig`). Not checked against any specific number.

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Pose row: avatar + bold actor name + timestamp, muted rounded bubble | Matches demo's `.pose`/`.pose-head`/`.pname` idiom | MATCH | `images/screen1-before-cast.png` vs `images/demo-screen1-reference.png` |
| Zero-comprehension say renders bare `"..."` inside the quoted body | Matches demo Screen 1 left, map item 2 | MATCH | `images/screen1-before-cast.png` vs `images/demo-screen1-reference.png` |
| Say's "in Tongue A" language clause stays readable even when fully garbled | Matches demo's `.garble` note ("the language name stays readable") | MATCH | `images/screen1-before-cast.png` |
| Clear say renders the full quoted sentence after a strong cast | Matches demo Screen 1 right | MATCH | `images/screen1-after-strong-cast.png` vs `images/demo-screen1-reference.png` |
| Cast outcome line: italic, muted, no avatar/header | Matches demo's `.outcome` idiom | MATCH | `images/screen1-after-strong-cast.png` vs `images/demo-screen1-reference.png` |
| Half-garbled say keeps roughly half the words, consistent per line | Matches demo Screen 2 left | MATCH | `images/screen2-weaker-cast.png` vs `images/demo-screen2-reference.png` |
| Languages glance: label column + value column, caps-tracked label | Matches `.refsheet-glance` layout | MATCH | `images/screen3-while-effect-lasts.png` vs `images/demo-screen3-reference.png` |
| "Temporary" accent tag beside the raised level | Matches `.refsheet-tag-accent` | MATCH | `images/screen3-while-effect-lasts.png` vs `images/demo-screen3-reference.png` |
| Gloss line: "from the condition name" with no trained text, condition-only row | Matches demo + Ruling Q1 | MATCH | `images/screen3-while-effect-lasts.png` (Tongue A) |
| Gloss line: "from the condition name, trained band" with a trained fallback | Matches demo exactly, including the middle dot | MATCH | `images/screen3-while-effect-lasts.png` (Tongue B) |
| Condition-only row disappears once the effect ends | Matches demo Screen 3 right ("Tongue A is gone") | MATCH | `images/screen3-after-effect-ends.png` vs `images/demo-screen3-reference.png` |
| Trained row returns to its trained level once the effect ends | Matches demo Screen 3 right ("Tongue B is back at its trained level") | MATCH | `images/screen3-after-effect-ends.png` vs `images/demo-screen3-reference.png` |
| `ConditionModifierEffect` inline fields (`modifier_target`, `value`, `scales_with_severity`) reach the `ConditionTemplate` admin page | Matches demo's admin table row | MATCH | field names confirmed in rendered admin HTML this pass (not a committed image; see Admin section) |
| `TechniqueAppliedCondition` inline fields (`condition`, `base_severity`, `severity_per_extra_sl`, `minimum_success_level`) reach the `Technique` admin page | Matches demo's admin table row | MATCH | field names confirmed in rendered admin HTML this pass (not a committed image; see Admin section) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| R01 | PASS | Zero-fluency listener reads a tagged say as bare `"..."`; name/verb/language stay readable (Success signal 1, garble half) | |
| R02 | PASS | A listener holding a comprehension-raising condition reads the same say clear or partly garbled by magnitude (Success signal 1, raise half); `screen1-after-strong-cast.png`, `screen2-weaker-cast.png`, `world.species.tests.test_language_comprehension` (19, green) | |
| R03 | PASS | Without the condition, or after it ends, the same listener sees the same garble as before (Success signal 2); `screen3-after-effect-ends.png`; `world.scenes.tests.test_language_interactions` (19, green) covers the reread-garbles-again journey code-side | |
| R04 | PASS | The same condition applied by a technique cast and by a GM catalog application produces the same result (Success signal 3; Decision 1) — `comprehension_values` reads ANY active condition, source-agnostic, by construction (`language_services.py:68-100`); `world.magic.tests.test_condition_application` (green) | |
| R05 | PASS | Poses, emits, narrator lines never garble (Success signal 4) — `screen1-before-cast.png` shows the pose fully readable under zero comprehension; `PoseAction`/`EmitAction` never call `_resolve_spoken_language` (verified in diff/spec's own garble-scope section) | |
| R06 | PASS | The condition does not let the character speak, teach, or self-study the language (Success signal 5; Decision 3) — `LanguageSelector.tsx` filters `fluency > 0` (diff confirmed), `frontend/src/game/components/LanguageSelector.test.tsx` (green) | |
| R07 | PASS | Staff author all of it in admin with no code (Success signal 6) — see Admin section; `ConditionModifierEffectInline`/`TechniqueAppliedConditionInline`/`ModifierTarget`/`ModifierCategory` all pre-existing admin, rendered live this pass | |
| R08 | PASS | The staff technique-power estimate does not count a fluency bonus as combat power, reporting "not combat power" rather than a silent zero (Success signal 7; Decision 10) — `de_valuation.py:187-215,285-292`; `world.magic.tests.test_condition_power_eval`/`test_technique_power_eval_valuators` (green) | |
| R09 | PASS | Sheet shows effective level, "Temporary" marker, condition name, trained-level fallback, including a condition-only row with no trained text (Decision 6 as overridden by Ruling Q1); `screen3-while-effect-lasts.png`/`screen3-after-effect-ends.png` vs `demo-screen3-reference.png`; `LanguagesSection.test.tsx` (green, incl. the sheet.css-reaches-the-page assertion) | |
| R10 | PASS | Live recompute on all three render paths (telnet, web push, scene-log reread), no snapshot (Decision 2) | telnet: `communication.py` diff, batched `comprehension_values`; web push: `interaction_services.py` diff; reread: `interaction_serializers.py:596-617` calling the SAME function ("Controller ruling F2"); `world.scenes.tests.test_language_interactions` (green) |
| R11 | PASS | Garble scope: spoken text only, never poses (Decision 9) | `screen1-before-cast.png` pose fully readable; garble-scope test cited in spec's Technical design, `actions.tests.test_language_speech` (green) |
| R12 | PASS | One effect row per language, no bulk admin action (Decisions 4, 5 — this review's named ruled non-flag) | `git diff origin/main...HEAD --stat` shows no new admin action added |
| R13 | PASS | Active conditions only; distinctions/equipment do not raise comprehension (Decision 8) | `comprehension_values` walks `sheet.character.conditions.active()` only, never `CharacterModifier` (`language_services.py`); `world.conditions.tests.test_condition_modifier_totals` (green) |
| R14 | OUT_OF_SCOPE | Screen 2 right panel ("Scene finished, log reread") not independently screenshotted this pass | Disproportionate to stand up `SceneDetailPage`'s full dependency surface for this review; behavior verified by code read + `world.scenes.tests.test_language_interactions` (19, green) and `world.conditions.tests.test_condition_modifier_totals` (9, green), which the spec's own Testing section names as the oracle for this exact journey |
| R15 | OUT_OF_SCOPE | Dark-theme / alternate-viewport visual pass not performed | Demo is explicitly example-only across themes (its own `:root`/`[data-theme=dark]` tokens are decorative, not content); the app's real tokens are the ones already shipped and unchanged by this diff outside the two new `sheet.css` rules checked above, which are theme-token-relative (`hsl(var(--accent))`, `hsl(var(--muted-foreground))`), not literal colors — no new theme-specific risk introduced by this diff |

## Unresolved findings

- None
