# Review evidence

- Reviewed revision: `9bebb8c713f01c82794ae328cb1f1dac0c24ee19`
- Reviewer: `demo-fidelity-reviewer agent (local), run against the five screenshots below and the branch diff before the migration was renumbered onto the latest main (the later commits change a test, docs and the migration number only)`
- Reviewer verdict: `PASS`
- Application/build identity: `feature-4441 branch built with just fe-build, served by arx manage runserver on :4011 against a throwaway Postgres database (rt_4441, since dropped)`
- Environment: `Linux devcontainer, headless Chromium through Playwright, Django runserver (no Evennia server process, so no websocket and no telnet socket), scratch Postgres schema built by tools/build_schema.py`
- Viewports/themes: `1100 px and 1280 px wide, light theme only (the sheet and scene pages ship one realm theme)`
- Approved design: `https://claude.ai/artifact/1926LF7noogf1hKijgL3v8 (the #4121 demo). It has no screen for this slice: it carries the scenario card "A rival's guard, opted in" and the Standoff card a player-character group must reuse`
- Visual review: `Completed`
- Visual verdict: `PASS`
- Screenshots: ![Profile panel before opting in](docs/reviews/standoffs-4441/1-before.png) ![Panel after opting in, reloaded](docs/reviews/standoffs-4441/3-reloaded.png) ![Another player's standoff card with the opted-in character as a group](docs/reviews/standoffs-4441/4-ysmay-scene.png) ![Panel locked during a standoff](docs/reviews/standoffs-4441/5-maud-locked.png) ![Card after a Read](docs/reviews/standoffs-4441/6-ysmay-after-read.png)
- Comparison notes: `The demo has no drawing of the sheet panel, so the panel is new surface with nothing to diverge from. The player-character group renders through the unchanged StandoffCard and matches the demo's group card: group name with a count, face-down tiles, the Look for select with Read, approaches, the terms line, Fight. After a Read the card shows the revealed drive tile. The grades read Impossible because the scratch database's check types come from test factories with no stats behind them; the reviewer flagged that the screenshots cannot show difficulty moving, which test_the_players_drives_ease_the_press_grade_and_nothing_else_rolls shows instead.`
- Tested interactions: `Opt in, pick a cause, add a drive at a chosen strength, reload and see all three kept (as the account playing the character); a second account opened the scene, saw the opted-in character as a group, clicked Read, and was told the drive; the first account's panel then locked with the reason. Refusal paths (not opted in, acting on yourself, a stranger on the sheet route) run in the journey tests.`
- Fixture/live boundary: `Live: the built frontend, the real REST and action dispatch endpoints, the real database. Seeded by a script that used the test factories: both accounts, both characters, the property catalog, the standoff config and the encounter (the GM's add-opponent step was a service call, not the GM screen). Not run: a live telnet socket.`
- Overall outcome: `PASS`

## Visual checklist

| Element | Expected | Result | Evidence |
|---|---|---|---|
| Profile panel heading and consent switch | A Standoffs section on the owner's Growth tab with one switch, off by default | MATCH | ![before](docs/reviews/standoffs-4441/1-before.png) |
| Cause select and drive rows | A cause picked from the creature causes and drives from the creature catalog with a strength, kept after reload | MATCH | ![reloaded](docs/reviews/standoffs-4441/3-reloaded.png) |
| Locked state | Every control disabled with the reason while the character stands in a standoff | MATCH | ![locked](docs/reviews/standoffs-4441/5-maud-locked.png) |
| Player-character group card | The demo's group card: name, count, face-down tiles, Read, approaches, terms, Fight | MATCH | ![card](docs/reviews/standoffs-4441/4-ysmay-scene.png) |
| Revealed drive after a Read | The drive tile shows the drive and its strength | MATCH | ![read](docs/reviews/standoffs-4441/6-ysmay-after-read.png) |

## Requirement ledger

| ID | Status | Evidence | Authorized decision |
|---|---|---|---|
| A01 | PASS | Opt-in switch off, then on, still on after a page reload: 1-before.png and 3-reloaded.png | |
| A02 | PASS | Cause Orders and drive Greedy at Major picked from the offered lists, still there after reload: 3-reloaded.png | |
| A03 | PASS | Second player's card lists the opted-in character as a face-down group, and a Read revealed Drive: Greedy (Major): 4-ysmay-scene.png and 6-ysmay-after-read.png | |
| A04 | PASS | While the group stands, the switch, cause, drive controls are disabled and say why: 5-maud-locked.png | |
| A05 | PASS | A player who never opted in, and the character acting on itself, are refused with no roll: test_a_player_who_has_not_opted_in_cannot_be_read_or_pressed and test_you_cannot_read_yourself in src/integration_tests/test_standoff_player_profile_journeys.py; the first fails when the opt-in check is removed | |
| A06 | PASS | Telnet parity: standoff profile, optin, cause, drive, drop and the read and press on a player run through the real command handler in the same journey file; a live telnet socket was not run | |
| A07 | PASS | The new migration only creates two empty tables; migration-reviewer found nothing | |

## Unresolved findings

- None
