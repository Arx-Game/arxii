# Beta Reset (#3055)

The alpha→beta early-access cutover needs a one-shot way to strip everything alpha testers
did through play from the world while keeping every CG/authoring-provenance row as the
pristine baseline (ADR-0206). PR 2 built the guarded wipe that performs this and PR 3 the
cutover policy layer around it; PR 1 (merged) built the acquisition-provenance ledger both
filter on (`CharacterTechnique.origin` /
`CharacterGift.origin` / `AcquisitionOrigin`, `CharacterTraitChange.source` /
`TraitChangeSource`, `CharacterDistinction.origin` / `DistinctionOrigin`,
`Discovery.discovered_by_tenure`, `CharacterAchievement.earned_by_tenure`).

## Command

`arx manage beta_reset` — management command only, never an admin surface. Defaults to a
dry-run (counts only, touches nothing); `--execute` performs the wipe, gated by four
independent guards that must all pass:

1. **`BETA_RESET_ENABLED`** — a hardcoded Python literal in
   `world/beta_reset/services.py`. Flipping it `False` at cutover is a reviewed PR;
   re-enabling it later requires another one.
2. **`ReleaseLatch`** (`world/beta_reset/models.py`) — a one-way DB row, independent of the
   constant above. Written once by `arx manage mark_beta_release --released-by <username>`
   (wraps `world.beta_reset.services.mark_released`, which refuses a second row). No
   "unmark" path exists.
3. **Typed confirmation phrase** — `--confirm "wipe the alpha world"`
   (`services.CONFIRMATION_PHRASE`), compared exactly; absent/wrong input never proceeds.
4. **Verified-fresh-backup precheck** — `--backup-verified-at <ISO timestamp>`, must be
   within `services.BACKUP_FRESHNESS_WINDOW` (24h). The command does not run or verify a
   backup itself — that's `infra/scripts/restore-rehearsal.sh`, run by hand first.

See ADR-0207 for why both the constant and the latch exist (either alone is bypassable).

## Scope

`world.beta_reset.services.SCOPE_TABLE` is the single source of truth: an ordered list of
`(model, filter_kwargs_or_None)` pairs, introspectable by tests and by PR 3. Two shapes:

- **Wholesale** (`filter_kwargs=None`) — every row in the table is play-state with no
  CG/authoring counterpart: scenes/journals, justice, secrets, NPC standing, economy
  ledgers (`CharacterPurse`/`CurrencyTransfer`/`Contract`/`DebtInstrument`/...),
  achievements earned, Discovery, legend/renown ledgers.
- **Provenance-filtered** — `CharacterTechnique`/`CharacterGift` (by `AcquisitionOrigin`),
  `CharacterTraitChange` (by `TraitChangeSource`), `CharacterDistinction` (by
  `DistinctionOrigin`): only rows whose discriminator is a play-time value are deleted; the
  CG/authoring value IS the pristine baseline.

Deletion runs in one transaction, in `SCOPE_TABLE` order — the order resolves real
`PROTECT` landmines (`FrameJobDetails.evidence` against `CrimeEvidence`;
`CombatEncounter.scene`/`TreatmentAttempt.scene` against `scenes.Scene`) — followed by
`world.societies.models.refresh_legend_views()`.

**Not touched by the wipe, deliberately:** `CharacterSheet`/`Persona`/`RosterEntry`/
`RosterTenure`/`Organization`/`Covenant` (structural identity; the cutover policy layer ends
tenures and moves entries but never deletes them);
`GMProfile`/`AccountDB`/kudos/`Block`/`Friendship`/`Mute` (account-level data; `Rivalry` is gone since #3957 — rivalry is an IC relationship label now, and relationship rows are play state);
catalog/config models (`CrimeKind`, `AreaLaw`, `SecretCategory`, `Profession`,
`DistinctionPurseDrain`, `DistinctionStartingGrant`, tuning singletons); `CharacterCodexKnowledge` (no CG-vs-play
discriminator exists on it today — flagged, not guessed at); org economics
(`OrganizationTreasury` and friends — orgs themselves survive the reset).

## Delete order and the provenance sets

The wipe's scope is `SCOPE_TABLE` alone: the explicit list of what it deletes, in order.
`test_service.ScopeTableDeleteOrderTests` walks every PROTECT or RESTRICT relation onto a
`SCOPE_TABLE` table and fails when the table holding it is not deleted at or before that
step (itself or by cascade), because the wipe would then raise `ProtectedError`. That is how
the capstone-anchored `Thread` rows and their `ThreadLevelUnlock` receipts, journal capstones,
legend honors, listener harvests and event grandeur spends come to be listed ahead of their
targets. A protected reference onto a table the wipe reaches only by cascade (a `Clue` the
Secret wipe cascades into, with a pool entry, vision or answer pointing at it) is not in
that walk; it is covered by the seeded behavioural test in `test_cutover.py`, where the
cutover rolls everything back and the command raises a `CommandError` naming the blocking
model. The `PLAY_TIME_*` and `CG_AUTHORING_*` provenance sets in `services.py` together
cover every `AcquisitionOrigin`, `TraitChangeSource` and `DistinctionOrigin` member, enforced
by `test_progress.py`.

## Cutover policy layer (PR 3)

`world.beta_reset.cutover.run_beta_cutover` runs behind the same guards as the wipe, from the
same `arx manage beta_reset` command, in one transaction: first the policy steps, then
`wipe_pristine_world`. The dry-run prints what each step would do. Three kinds of kept
character, each treated the same way (every open tenure ends, an entry someone held returns to
the Available shelf, `reset_character_progress` runs):

- **Roster characters** (`creation_provenance` STAFF or GM_TABLE, off the NPC shelf).
- **Reserved original characters** (PLAYER provenance with a `created_by_account`). Only that
  account may apply for it again (`is_reserved_against` in `roster/services/activity.py`,
  checked by `RosterApplicationCreateSerializer` and `can_apply`); approval re-seats them on
  their own past tenure. No schema change (ADR-3055).
- **Carried-over characters** (`--carry-over <character sheet id>`, repeatable). An original
  character with no recorded author is reserved to the account that held it last; a sheet with
  no roster entry is progress-reset in place; a roster character, a story NPC or a missing id
  is refused (`CarryOverError`) before anything is touched.

Safeguards added on review: `execute_cutover` and `reset_character_progress` check the
enabled constant and the release latch themselves, so no direct call runs after release (the
typed phrase and backup precheck stay on the command path). Before `--execute` changes anything
it checks every kept character's ledger (`progress.ledger_problems`: each trait's rows chain and
end at the current value, a ledger row's value row still exists, the class-level receipts chain
up to the level); a character that fails is listed in the dry-run and refused by `--execute`,
which names it, unless `--allow-incomplete-ledger` is given. The policy steps and the wipe run in
one transaction, so a `ProtectedError` rolls everything back and the command raises a
`CommandError` naming the blocking model (`WipeBlockedError`). After the wipe the thread handler
is invalidated for every character that owned a capstone-anchored thread and max health is
recomputed for each kept character. The reset lowers the class level directly instead of through
`apply_class_level_advance`, which would re-run story auto-beats and could notify players.
`RosterApplication.approve` refuses an application onto an original character reserved to
another account (`ReservedForCreatorError`), so a rival application filed before the cutover
cannot be approved by any path; the dry-run counts those pending applications. The dry-run also
names the account each reserved character is reserved to, the trait rows that would be removed,
natural weapons that would go with their gifts, and states that its wipe counts are computed
before the policy steps run.

Alpha accounts and their kudos, blocks, mutes and friendships are never touched. An original
character with no recorded author that nobody names for carry-over is left exactly as it is.

`world.beta_reset.progress.reset_character_progress(sheet)` reverses play provenance for one
character, reading the play-time filters from `SCOPE_TABLE` (`scope_entry_for`): trait values
step back by the summed play-time `CharacterTraitChange` deltas (a row play created is removed,
the play-time change rows are deleted so a second run is a no-op), play-origin techniques,
gifts (with their natural weapon) and distinctions (through
`distinctions.services.delete_character_distinction`, the teardown `remove_distinction` shares)
are removed, the stat-point and maturation spend receipts are deleted, and the class level
returns to the lowest `level_before` among the Durance and Audere Majora receipts. It does not
reset anything it does not list or the character's path (`CharacterPathHistory`
carries no provenance).

## Tests

`world/beta_reset/tests/test_service.py` — journey tests against the service directly
(seed play + CG rows across every ledger, execute, assert the split; dry-run destroys
nothing; the latch blocks execution; the confirmation/backup/constant guards each refuse
independently; PROTECT-ordering for `NPCStanding`, `CombatEncounter`/`Scene`, journal
capstones and legend honors, capstone-anchored threads, listener harvests and event
grandeur spends). `test_service.py` also holds the delete-order walk.
`test_progress.py` — the per-character reset and the provenance-set partition.
`test_cutover.py` — the policy steps, the reservation gate over the API, carry-over, and the
command output. `test_command.py` — thin argument-gating tests via `call_command` for both
`beta_reset` and `mark_beta_release`.

## Retired after the cutover

The reset exists for one day. At the cutover a reviewed PR sets `BETA_RESET_ENABLED` to
False. The PR after it deletes the whole `world/beta_reset` package (both commands, the
services, the progress reset, the cutover layer and their tests) and drops the `ReleaseLatch`
table with one `DeleteModel` migration. The reservation rule for original characters
(`is_reserved_against` and its use in the application serializer, `RosterApplication.approve`
and `can_apply`) lives in the roster app and stays.
