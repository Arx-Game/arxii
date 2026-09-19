# Reviewer Agents

Project-specific subagent definitions (`.claude/agents/*.md` frontmatter format),
symlinked into `~/.claude/agents/` by `.devcontainer/post-create.sh`. `.claude/`
is gitignored, so `tools/agents/` is the tracked home — same arrangement as
`tools/skills/`.

## When to add one

**Every defect that reaches `main` or production gets a reviewer agent for its
class, in the same PR as the fix.** Not a follow-up issue, not a line in a doc
nobody reads at the right moment: an agent that can be dispatched at the moment
the mistake would be repeated.

The test for whether a defect qualifies is not severity, it is *recurrence
shape* — could a competent agent make this same mistake again next week while
following the rules as written? If yes, the rules as written are the problem,
and a reviewer that reads the actual diff is the fix.

An entry here should carry, concretely:

- **the failure it exists to catch**, with the real error text, so it is
  recognizable rather than abstract;
- **why the existing gates missed it** — a defect that CI could have caught
  wants a test, not an agent;
- **what to check**, as things to look for in a diff, not principles to hold.

Pair it with a mechanical check where one is possible: the agent catches the
shape, the linter catches the instance. `reviewing-migrations` (skill) +
`tools/lint_migration_ddl_dml.py` (hook) + `migration-reviewer` (agent) is the
worked example.

## Current agents

| Agent | Dispatch it when | The defect it came from |
|---|---|---|
| `migration-reviewer` | A branch's diff touches `src/world/migrations/`, immediately after `arx manage makemigrations`, and when reviewing a PR that adds one. | A migration mixing schema and data operations broke the production converge (2026-09-04). CI only ever migrates an empty database. |
| `demo-fidelity-reviewer` | Before opening the PR for any issue whose spec carries a demo link, and when reviewing such a PR. It must produce the committed evidence report consumed by `open-pr.sh`. | The Upbringing Builder shipped with none of its approved demo's admin form rows, header chips, submit row or right-hand rail, and no CSS rule for any of its own class hooks (#3667). Nineteen tests passed; a human found it on production. |
| `mock-fidelity-reviewer` | A diff calls a framework hook or another object's method, and when it adds or changes tests that stand a `Mock`/`MagicMock` in for a real collaborator. | `Account.at_post_login` called the Server-side `ServerSession.at_login()` with no arguments, aiming at the Portal-side `SecureWebSocketClient.at_login()` — a different object in a different process. Every login raised TypeError and lost its cmdset payload and character list. All three tests covering the hook passed a bare `MagicMock` as the session, so all three stayed green for months (2026-09-09 Sentry quota incident, digest #3736). |
| `derived-classifier-reviewer` | A diff adds or changes a function that derives a category, relationship, eligibility or safety decision from model fields, and when reviewing one. | `is_technique_hostile` read `EffectType.base_power` as "offensive", but Defense carries base_power 10 because it *scales* with power — so all 54 authored Defense techniques classified as hostile and shields routed as attacks (#3682, ADR-0281). Shipped in #779; every test passed for four months because they all ran on factory defaults. |
| `typeclass-creation-reviewer` | A diff calls `.objects.create(`/`.objects.create_user(`/`.objects.get_or_create(` (or instantiates directly) on `AccountDB`, `ObjectDB`, or `ScriptDB` — and any diff, runbook or shell recipe that *repairs* such a row by writing `db_typeclass_path` instead of replaying first-save setup. | `seed_test_account` created its e2e account via `AccountDB.objects.create_user()`, the bare Django manager method. That instantiates plain `AccountDB`, not its typeclass proxy, so Evennia's `post_save` signal (registered per proxy class) never fired `at_first_save()` — `db_cmdset_storage` stayed empty and the account could log in but couldn't run a single command, even `help` (#3789). Then the documented repair for such rows — `.update(db_typeclass_path=...)` — fixed the typeclass and nothing else, so the production staff account (made by the deploy's own `createsuperuser --noinput`) loaded as the typeclass, printed its character list, and answered `Command '@ic Apostate' is not available.` (#3812). Mechanical half: the `typeclassed-accounts` ops probe now checks both symptoms, and `at_server_start` heals them. |
| `blast-radius-reviewer` | A diff adds a `raise`, guard, validation or newly-required argument INSIDE an existing function with many call sites, and when reviewing one. | A reachability guard added inside `create_interaction` (~15 call sites) broke two callers the branch never ran: an existing scenes test, found two tasks later by accident, and `create_cast_outcome_pose`, found only by the final whole-branch review - it raised `UnreachableError` on every concealed cast and every Narrator-authored room-heard cast, reached from a REST resolver where nothing catches it, so it was an uncaught 500 whenever concealment worked as designed. Twelve tests were red in two files the branch never ran (#3787). |
| `schema-shape-reviewer` | A diff adds a model, field, foreign key, or constraint, and when reviewing a PR that does. | Not a production defect — three review rounds on the same PR (#3787) caught three proposed shapes (a bridge table reinventing an existing self-FK, two denormalized columns) that each looked defensible in isolation. Schema mistakes are unusually costly to unwind, so the pairing is proactive rather than waiting for one to reach production (#3815). |
| `outcome-delivery-reviewer` | A diff writes a player-facing outcome row (`Interaction`, a resolution-theater payload, or anything shaped like it), and when reviewing one. Paired with `tools/lint_undelivered_interaction.py`. | Three writers (`_create_result_interaction`, `_resolve_treatment_request`, `create_cast_outcome_pose`) persisted a resolved social-check/treatment/cast outcome and delivered it to nobody live - no WebSocket push, no telnet line - while every other production caller delivered. Tests asserted the row existed; a REST refetch and a scene-log reread both made it look fine. The issue itself was filed as a `needs-design` question asking whether to show the outcome at all; the ruling was that delivery is never optional, only the audience is (#3807). |
| `enumerated-set-reviewer` | A diff adds a member to a family the code also enumerates BY HAND elsewhere — a `*_visibility` field, a `TextChoices` member, a permission flag, a payload section key — and when reviewing one. | #3906 added a fifth per-section visibility tier, `standing_visibility`, defaulting to FRIENDS, but `_viewer_access_level` kept its own hand-written tuple of the other four. On every default sheet those four are SELF, so the resolver short-circuited to the PUBLIC rank without ever reading the allow list and a genuine friend was resolved as a stranger — the feature's whole purpose, broken on the default configuration for every character. It failed OPEN, so nothing raised; the seven new tests covered the owner and the stranger and never the FRIENDS tier between them; and the screenshot evidence fed the page a payload directly, so it never ran the resolver (#3923). Mechanical half: the tiers are now derived from the model via `CharacterSheet.visibility_field_names()`, with a test pinning that derivation against the `_visibility` naming convention. |
| `portal-code-deploy-reviewer` | A diff touches code the Evennia Portal loads (`src/server/portal/`, the websocket or telnet protocol classes, the Portal-read keys in `settings.py`), and when reviewing one. Paired with the deploy role's Portal fingerprint and the post-deploy `ws_idle_probe.py` task. | The #3803 websocket keepalive is a class attribute on the Portal's protocol class. It went to production in two consecutive stand-ups, both through `systemctl reload` = `evennia reload`, which restarts only the Server; the Portal kept its pre-fix code and production kept dropping idle sockets at 125.6 s. Unit tests proved the class, the health check polled the Server, and every gate was green (#3863). |
| `puppet-singular-access-reviewer` | A diff reads `request.user.puppet`/`.character` (or wraps one in a helper) and treats the result as a single object, especially in a view, serializer, or permission class. | Evennia's `Account.puppet`/`.character` return a **list** whenever `MULTISESSION_MODE` is not 0 or 1 — this game runs mode 3. `world/missions/views.py`'s journal endpoint hit this first (Sentry ARX2-7, `AttributeError: 'list' object has no attribute 'pk'`); `world/skills/views.py`'s `TrainingAllocationViewSet` hit the identical shape afterward, undetected until `just scan-prod-logs` found it (#3935, ADR-0304). The established fix — `world.roster.services.selection.character_for_request`/`selected_character` — already existed in the codebase both times. |
