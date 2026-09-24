# Review evidence, issue #3996, Character slots: start a new character from the Hall

- Reviewed revision: `74f18d9c3e162f6e45cb504be21422beb619b16a`
- Reviewer: the implementing agent over the seven captures, plus the migration-reviewer, blast-radius-reviewer and schema-shape-reviewer agents on the diff; the migration reviewer's finding (the backfill and the Hall compared provenance against uppercase strings while the stored values are lowercase) was fixed in 290c6d955 and the captures re-taken there; the blast-radius reviewer's findings (an entry-less pending application crashed the ledger, two staff creation sites left PLAYER provenance, the approval wrappers' refusals were untested) were fixed in 74f18d9c3, backend only, so the captures stand (no demo page: standard lane, one tile and one card menu on the existing Hall band)
- Reviewer verdict: PASS
- Application/build identity: the shipped `HallPage` (`frontend/src/home/HallPage.tsx`) mounted at its real route `/hall` inside the real application shell (Header, providers, `ProtectedRoute`), composing the shipped `CharactersBand`, `NewCharacterTile`, `CharacterActionsMenu` and `SlotActionDialog` with the application's real token cascade, served from the production build (`pnpm build`, Vite preview on localhost:4173)
- Environment: Chromium driven by Playwright (`frontend/e2e/evidence/character-slots-3996.spec.ts`) in the project devcontainer on Linux, deviceScaleFactor 1
- Viewports/themes: 1280x900 desktop (full-page captures) and 400x900 phone, light theme
- Approved design: the walkthrough in the spec on #3996 (screens 1 to 6): a tile after the cards reading `used of total` with Browse the roster and Create a character; when full the actions disabled and the holders listed with Freeze or Give up; a card menu with one action by provenance; a confirm dialog stating the consequence; no count for staff
- Visual review: completed. Seven captures of the rendered application were inspected against the spec's screen list, element by element
- Visual verdict: PASS
- Screenshots: ![Hall with a free slot](docs/reviews/3996/1-hall-free-slot.png) ![Hall with the slots full](docs/reviews/3996/2-hall-full.png) ![Card menu, Freeze](docs/reviews/3996/3-card-menu-freeze.png) ![Give up confirm](docs/reviews/3996/4-give-up-confirm.png) ![Frozen card and Thaw](docs/reviews/3996/5-frozen-card-thaw.png) ![Staff Hall, no count](docs/reviews/3996/6-staff-no-count.png) ![Phone width, full](docs/reviews/3996/7-phone-full.png)
- Comparison notes: the tile sits after the cards in the same grid with the band's plate chrome; the count is the bare pair `2 of 4` in the band's small-caps heading face with no label; the two actions are outline buttons linking to `/roster` and `/characters/create`; when full both render disabled and the holders list names each character with Freeze (original character) or Give up (roster character) beside it; the card menu is an ellipsis at the card's top-left whose one item follows provenance; the confirm dialog names the character and states the consequence in one sentence with Cancel and the action; the staff Hall shows the two actions and no count; the frozen card carries the word Frozen and its menu's Thaw item is disabled until the thaw date. No deviations from the spec's screens
- Tested interactions: the tile's links carry the two routes; the full state disables both actions; opening a card menu shows Freeze for PLAYER provenance and Give up for STAFF provenance; choosing Give up opens the dialog with "returns to the roster for other players"; a frozen entry shows Frozen and a disabled "Thaw from" item carrying the thaw date; the staff account sees no `of` text; at 400px the document has no horizontal overflow beyond the shell's known 10px
- Fixture/live boundary: the page, its components, the router, the app shell and the token cascade are the real shipped code. Every `/api/**` call was intercepted and answered by fixtures shaped like the serializers: the account (`/api/user/`, with `character_slots`), `/api/roster/entries/mine/` (two entries with the four new fields), and the three POST actions (answered with a frozen entry); everything else returned 404. The slot arithmetic, the enforcement at draft, application and approval, the provenance rule, freeze/thaw/give-up and the telnet line are proven by the backend tests named in the ledger, not by these captures
- Overall outcome: PASS

## Requirement ledger

| id | status | evidence | authorized decision |
| --- | --- | --- | --- |
| real-surface | PASS | The shipped Hall, band, tile, menu and dialog rendered at the real route from the production build (identity above). | |
| one-ledger | PASS | `world/roster/tests/test_character_slots.py`: tenures, drafts and applications each hold a slot; frozen and retired do not count; the activity slot counts HIGH and LOW; staff exempt; the override raises the total; `exclude_application` leaves one out. | |
| enforced-at-draft | PASS | `CanCreateCharacterSlotTests` in `world/character_creation/tests/test_services.py`: refused when full with the draft named, allowed with a free slot. | |
| enforced-at-application | PASS | `SlotGatesTests.test_apply_is_refused_on_the_activity_slot` in `test_character_slots.py`: a second requirement-bearing application returns 400 with `activity_slot_full`. | |
| enforced-at-approval | PASS | `SlotGatesTests`: approval refused when the slot filled after applying, application stays pending; approval counts its own application out. | |
| provenance-rule | PASS | `world/roster/tests/test_release_tenure.py`: PLAYER provenance freezes, STAFF cannot; a sheet without an entry is not an original character; the sweep never releases PLAYER provenance (`test_auto_release.py`). | |
| freeze-thaw | PASS | `test_slot_actions.py`: freeze returns FROZEN with a thaw date, thaw refused early and allowed after the cooldown; `3-card-menu-freeze.png`, `5-frozen-card-thaw.png`. | |
| give-up | PASS | `test_release_tenure.py` and `test_slot_actions.py`: the tenure ends, the entry returns to Available, refused for an original character, a stranger and a puppeted character; `4-give-up-confirm.png`. | |
| hall-tile | PASS | `1-hall-free-slot.png`, `2-hall-full.png`, `6-staff-no-count.png`; `NewCharacterTile.test.tsx` pins the count, the links, the disabled state, the holders and the draft link. | |
| card-menu | PASS | `CharacterActionsMenu.test.tsx`: Freeze for PLAYER, Give up for STAFF, Thaw after the date, disabled before it. | |
| payload | PASS | `AccountPayloadSlotsTests` and `web/tests/test_account_player_serializer_full_payload.py`: `character_slots` on the account payload, exempt staff carry `total: null`. | |
| telnet | PASS | `commands/tests/test_characters_command_slots.py`: the slot line for a player, none for staff; `charcreate`/`chardelete` absent from the account cmdset. | |
| migrations | PASS | 0158 adds the column (schema-only), 0159 carries `is_oc` onto provenance (data-only), 0160 drops the two columns (schema-only); reviewed against the reviewing-migrations checklist; disposition restructure, play-state table. | |
| responsive | PASS | `7-phone-full.png`: one column at 400px, no horizontal overflow beyond the shell's known 10px. | |
| no-errors | PASS | Seven Playwright tests pass with no page errors. | |
| fixture-boundary | PASS | Stated in full above: real page and shell, fixture API. | |

## Visual checklist

| Element | Expected | Result | Evidence |
| --- | --- | --- | --- |
| [1] Tile placement and chrome | After the cards, same plate chrome as a card | MATCH | `1-hall-free-slot.png` |
| [1] Count | Bare `2 of 4`, no label | MATCH | `1-hall-free-slot.png` |
| [1] Two actions | Browse the roster, Create a character, outline buttons | MATCH | `1-hall-free-slot.png` |
| [2] Full state | Both actions disabled, holders listed with Freeze / Give up | MATCH | `2-hall-full.png` |
| [3] Card menu | Ellipsis at the card's top-left, one item by provenance | MATCH | `3-card-menu-freeze.png` |
| [4] Confirm dialog | Names the character, states the consequence, Cancel and the action | MATCH | `4-give-up-confirm.png` |
| [5] Frozen card | The word Frozen on the card, Thaw disabled until the date | MATCH | `5-frozen-card-thaw.png` |
| [6] Staff Hall | Two actions, no count | MATCH | `6-staff-no-count.png` |
| [7] Phone | One column, nothing clipped beyond the shell's known overflow | MATCH | `7-phone-full.png` |
| [1-6] No help text | Labels only, no explanatory prose | MATCH | all captures |

## Divergences

None.

## Unresolved findings

None
