# Testing: three layers, not coverage

The suite protects three things, in this order (#3657, ADR-3657):

1. **Journeys.** For each thing a player or staff member is trying to do, one
   test that drives it on the seam they reach it by and asserts what the game
   told them. `src/integration_tests/harness.py` (`JourneyCase`) is the one
   harness: `telnet()` types a line through the real command handler, `web()`
   runs a registry action through `dispatch_player_action`, `api()` is a
   signed-in REST client, `watch()` / `assertTold()` read what each character
   was told, and `connect_session()` / `session_frames()` give an account a
   browser (`websocket`) or MUD (`telnet`) session and read what was pushed to
   it in the form the Server puts on the wire (channel frames and lines go to
   account sessions, not characters).
   Journeys are PostgreSQL-only by construction.
2. **Fuzz.** Malformed, hostile and boundary input at those same seams, generated
   by Hypothesis (`src/integration_tests/fuzz/`, profiles `ci` and `dev`).
3. **Cross-system integration.** The cases where one system's change breaks
   another (a flow firing on an event, a service crossing an app boundary),
   kept because no per-app suite can see them.

New work gets a journey for each thing a player does and a Hypothesis property
for each rule. A unit test is written in one case only: as the evidence of a
bug fix, failing before the fix and passing after it. That test is marked
`@tag("regression")`, its docstring begins `Regression for #<issue>.`, and it
stays. An existing unit test is removed only when a mutation run shows the kept
tests catch every change it catches. Where they do not, a property or a journey
is written first, from the spec, the docstring or a ruling, and then the unit
test goes (#4248, ADR-4248).

## The files here

| File | What it is | Who edits it |
|---|---|---|
| `journeys.md` | The curated list of stories the suite protects: seam, covering test, gaps | people, in tandem with the change (CLAUDE.md "Docs Are Directives") |
| `journey-inventory.md` | Every surface the registries know (actions, commands, API routes, frontend routes) and the tests naming it | nobody: `uv run python tools/journey_inventory.py > docs/testing/journey-inventory.md` |
| `ledger/<app>.csv` | The confirmed ledger for an app, written in its removal tranche: the tool's columns plus `confirmed` (the grade a person settled on) and `note` (why, and which journey covers a removal). These files record the hand grades made before ADR-4248; a removal is now shown by a mutation run. A package ruled on over several tranches (`commands.csv`, `actions.csv`) carries every module; a row with an empty `confirmed` is still the tool's proposal, not a ruling | the tranche's PR |

## Recipes

```bash
# One app's journeys, fuzz and units on the parity tier (journeys are PG-only):
just test-parity integration_tests
HYPOTHESIS_PROFILE=dev just test-parity integration_tests.fuzz   # hunt harder, locally

# The mechanical first pass over an app's test modules (stderr: the summary):
uv run python tools/test_ledger.py world.conditions --csv docs/testing/ledger/conditions.csv

# Regenerate the inventory after adding an action, command, route or journey:
uv run python tools/journey_inventory.py > docs/testing/journey-inventory.md

# What no journey reaches (design input, never a gate; runs weekly on main too):
just coverage-journeys

# Which test group notices each small change to one function (never a gate):
just mutate src/world/magic/services/primum.py --functions points_to_power \
    --kept integration_tests.fuzz.test_primum_curve_fuzz \
    --units world.magic.tests.test_primum_math
```

## The ledger rubric

`tools/test_ledger.py` proposes one of these per module. The layers are how the
kept group and the unit group of a mutation run are chosen; a grade alone no
longer removes a test.

| Layer | Means | Kept |
|---|---|---|
| `J` | drives the real seam (`JourneyCase`, `execute_cmd`, `dispatch_player_action`) and asserts what the player saw; a pre-harness journey that calls `Cmd.func()` by hand is `J` too, with a note to move it | yes |
| `F` | Hypothesis at a seam | yes |
| `X` | reaches two or more other `world.*` packages' services | yes |
| `U-keep` | a unit test no journey is known to cover; the default when the signals are quiet | until a mutation run shows the kept tests catch what it catches |
| `R` | `builtin` (Django or DRF behaviour), `shape` (dict, queryset or instance shape), `dup` (a named journey already asserts the outcome), `mock-pinned` (the assertion is that a mock was called), `smoke` (factory builds, `__str__`, `Meta`) | no, once a mutation run confirms it |

A removal PR carries the mutation run that shows it: for each removed test, the
row of the run's `unit_tests.csv` whose `kept_missed` is 0. "Nothing calls it"
is never the reason. A test that caught no change in a run is not shown
redundant by that run, because it may not exercise the changed code.

## Mutation run

A mutation run answers one question about one source file: for each small
change to the code, which tests notice. `just mutate` (`tools/mutation_run.py`,
cosmic-ray underneath) makes one change at a time, such as `<=` to `<` or
`- 1` to `- 2`, runs two groups of tests against it, and restores the file. The
caller names both groups: `--kept` for journeys, properties and cross-system
tests, `--units` for unit tests. Each of the two takes one or more test labels.
The driver does not guess which test belongs where.

The report (`.mutation/<file>/report.md`, with `changes.csv` and
`unit_tests.csv`) sorts every change into one of three lists:

- **Guarded:** a kept test failed. A marked regression test counts here too.
- **Units only:** only a unit test failed. This is what removing those unit
  tests would leave unguarded.
- **Unguarded:** no test failed.

How to use it:

- **To retire unit tests**, write properties or journeys until the tests' rows
  in `unit_tests.csv` read `kept_missed` 0, then remove them in the same PR. The
  Primum curve is the worked example: 11 of 69 changes were caught only by four
  unit tests, three properties written from the docstrings brought that to 0,
  and the four tests went (#4248).
- **To strengthen a property**, read the unguarded list. Each line is either a
  change that cannot alter behaviour, which a person marks by reading it, or a
  missing rule. State a missing rule from the spec, the docstring or a ruling,
  never from what the code returns. A surviving change that no written rule
  covers is a question for the maintainer. An unguarded change can also be a
  rule the property states and its generator never reaches in 50 examples; pin
  that boundary with `@example`, or give the generator an arm of small values.
- **Choose the kept group widely.** With six journey modules the journeys caught
  2 of the 14 changes unit tests catch in `apply_condition`; with all 27 modules
  that name the function they caught 9.

What it cannot tell you: whether a test asserts the right value. A test that
pins a wrong number still fails when the code changes. The expected value still
has to come from a spec, a docstring or a ruling.

Limits. Each change costs one test start-up per group (12 to 19 seconds on
SQLite; 50 to 250 seconds for a journey group on Postgres), so narrow a run with
`--functions` or `--lines`, and use `--sample N` on a large function. Locally a
run is SQLite only, one at a time, and it changes the source file on disk while
it runs: do not commit, push or run other tests in that worktree until it
exits. A run that needs journeys uses the hand-started `Mutation run` workflow
(`.github/workflows/mutation.yml`), one function per run. It is never a required
check and never runs per push, because a job over 5 minutes does not belong on a
per-push trigger.

## Writing a journey

```python
from integration_tests.harness import JourneyCase


class AGreetingReachesTheRoom(JourneyCase):
    def test_the_room_hears_it(self) -> None:
        room = self.make_room("The Lantern")
        ysmay = self.make_player("Ysmay", room=room)
        hobb = self.make_player("Hobb", room=room)
        self.watch(hobb)
        told = self.telnet(ysmay, 'say Good evening.')
        self.assertIn('You say "Good evening."', told)
        self.assertTold(hobb, 'Ysmay says "Good evening."')
```

The expected lines come from the spec, the issue or the demo, never from the
code's own output. Assert the line the player needs next, not only the row
that changed (the `running-tests` rule: never assume player omniscience). A
command that raises fails the test with its own exception; the handler's
"there was an error" line is never a pass.
