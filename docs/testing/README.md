# Testing: three layers, not coverage

The suite protects three things, in this order (#3657, ADR-3657):

1. **Journeys.** For each thing a player or staff member is trying to do, one
   test that drives it on the seam they reach it by and asserts what the game
   told them. `src/integration_tests/harness.py` (`JourneyCase`) is the one
   harness: `telnet()` types a line through the real command handler, `web()`
   runs a registry action through `dispatch_player_action`, `api()` is a
   signed-in REST client, `watch()` / `assertTold()` read what each character
   was told. Journeys are PostgreSQL-only by construction.
2. **Fuzz.** Malformed, hostile and boundary input at those same seams, generated
   by Hypothesis (`src/integration_tests/fuzz/`, profiles `ci` and `dev`).
3. **Cross-system integration.** The cases where one system's change breaks
   another (a flow firing on an event, a service crossing an app boundary),
   kept because no per-app suite can see them.

A unit test is kept only when a journey cannot reach the logic: a parser with
branches, an error-path mapping, a pure function's edge. Everything else is a
removal candidate, graded by the ledger and confirmed by a person.

## The files here

| File | What it is | Who edits it |
|---|---|---|
| `journeys.md` | The curated list of stories the suite protects: seam, covering test, gaps | people, in tandem with the change (CLAUDE.md "Docs Are Directives") |
| `journey-inventory.md` | Every surface the registries know (actions, commands, API routes, frontend routes) and the tests naming it | nobody: `uv run python tools/journey_inventory.py > docs/testing/journey-inventory.md` |
| `ledger/<app>.csv` | The confirmed ledger for an app, written in its removal tranche: the tool's columns plus `confirmed` (the grade a person settled on) and `note` (why, and which journey covers a removal). A package ruled on over several tranches (`commands.csv`, `actions.csv`) carries every module; a row with an empty `confirmed` is still the tool's proposal, not a ruling | the tranche's PR |

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
```

## The ledger rubric

`tools/test_ledger.py` proposes one of these per module; a person confirms it.

| Layer | Means | Kept |
|---|---|---|
| `J` | drives the real seam (`JourneyCase`, `execute_cmd`, `dispatch_player_action`) and asserts what the player saw; a pre-harness journey that calls `Cmd.func()` by hand is `J` too, with a note to move it | yes |
| `F` | Hypothesis at a seam | yes |
| `X` | reaches two or more other `world.*` packages' services | yes |
| `U-keep` | a unit a journey cannot reach; the default when the signals are quiet | until a journey covers it |
| `R` | `builtin` (Django or DRF behaviour), `shape` (dict, queryset or instance shape), `dup` (a named journey already asserts the outcome), `mock-pinned` (the assertion is that a mock was called), `smoke` (factory builds, `__str__`, `Meta`) | no, once confirmed |

A removal PR lists, per removed module, the `J` or `X` test that still asserts
the behaviour. "Nothing calls it" is never the reason; "journey N asserts
this" is. Nothing is removed whose only remaining cover is mock-pinned.

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
