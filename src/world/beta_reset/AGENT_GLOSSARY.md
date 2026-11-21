# Beta Reset glossary

**Pristine world**:
The state the game should be in the moment early access begins — every row that carries CG/authoring provenance intact, every row that carries play-time provenance gone. Derived at wipe time by filtering the acquisition-provenance ledger (ADR-0206), never captured as a stored snapshot.
_Avoid_: clean slate, fresh start, reset state

**Release Latch**:
The one-way `ReleaseLatch` database row that permanently blocks the beta-reset wipe from ever running again once early access has shipped, independent of the `BETA_RESET_ENABLED` code constant. Written once via `mark_released()`/`arx manage mark_beta_release`; there is no unmark path.
_Avoid_: reset flag, release flag, kill switch

**Cutover**:
The single moment early access begins — the point at which the beta-reset wipe runs (or is deliberately skipped) and the `ReleaseLatch` gets written. Not a window or a process; a specific operator-run event.
_Avoid_: launch, go-live, release date

**Play-provenance**:
Said of a row whose acquisition/change discriminator (`AcquisitionOrigin`, `TraitChangeSource`, `DistinctionOrigin`) records that it happened during play rather than at CG/authoring time. The beta-reset wipe deletes play-provenance rows and leaves CG/authoring-provenance rows on the same table untouched.
_Avoid_: play data, runtime data, dynamic data

**Roster character** (cutover):
An entry with STAFF or GM_TABLE `creation_provenance`, off the NPC shelf. At the cutover its tenures end, it returns to Available, and its progress is reset. Same meaning as the roster glossary's term.
_Avoid_: staff character, authored character

**Reserved original character**:
A player's own creation (`creation_provenance` PLAYER with a `created_by_account`) that survives the cutover progress-reset and can only be applied for again by that account. Carried by the two existing roster fields, with no separate flag.
_Avoid_: OC, `is_oc`, reserved OC flag

**Carried-over character**:
A tester's alpha character named with `--carry-over <character sheet id>` so it survives the cutover with its progress zeroed instead of being left to the unruled deletion step.
_Avoid_: kept character, grandfathered character

**Progress reset**:
`reset_character_progress`: steps one kept character's play-time provenance back out (trait values by ledger delta, play-origin techniques, gifts and distinctions, spend receipts, class level), leaving character-creation and authoring rows. Not the wipe, which strips whole tables world-wide.
_Avoid_: character wipe, rollback
