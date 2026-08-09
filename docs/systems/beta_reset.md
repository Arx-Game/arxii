# Beta Reset (#3055)

The alpha→beta early-access cutover needs a one-shot way to strip everything alpha testers
did through play from the world while keeping every CG/authoring-provenance row as the
pristine baseline (ADR-0206). PR 2 built the guarded wipe that performs this; PR 1 (merged)
built the acquisition-provenance ledger it filters on (`CharacterTechnique.origin` /
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

**Not touched, deliberately:** `CharacterSheet`/`Persona`/`RosterEntry`/`RosterTenure`/
`Organization`/`Covenant` (structural identity — see the PR 2/PR 3 boundary below);
`GMProfile`/`AccountDB`/kudos/`Block`/`Friendship`/`Rivalry`/`Mute` (account-level data);
catalog/config models (`CrimeKind`, `AreaLaw`, `SecretCategory`, `Profession`,
`DistinctionPurseDrain`, tuning singletons); `CharacterCodexKnowledge` (no CG-vs-play
discriminator exists on it today — flagged, not guessed at); org economics
(`OrganizationTreasury` and friends — orgs themselves survive the reset).

## PR 2 / PR 3 boundary

PR 2's wipe does **not** step `CharacterTraitValue` back down after deleting a play-time
`CharacterTraitChange` row, even though that row records the exact delta. Replaying the
ledger backward to restore a derived value on a **kept** character is PR 3's "roster
characters progress-reset" scope. PR 2's own alpha test characters are deleted wholesale
at cutover by a separate step outside this command — `wipe_pristine_world` never touches
`CharacterSheet`/`Persona`/`RosterEntry`/`RosterTenure` at all — so any derived-value drift
this wipe leaves behind is moot for them. PR 3 is what makes a *kept* roster character's
sheet numbers consistent again after using this same provenance ledger.

## Tests

`world/beta_reset/tests/test_service.py` — journey tests against the service directly
(seed play + CG rows across every ledger, execute, assert the split; dry-run destroys
nothing; the latch blocks execution; the confirmation/backup/constant guards each refuse
independently; PROTECT-ordering for `NPCStanding` and `CombatEncounter`/`Scene`).
`world/beta_reset/tests/test_command.py` — thin argument-gating tests via `call_command`
for both `beta_reset` and `mark_beta_release`.
