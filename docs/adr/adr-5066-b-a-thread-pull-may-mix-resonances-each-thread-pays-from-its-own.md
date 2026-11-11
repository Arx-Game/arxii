# ADR-5066-B: A thread pull may mix resonances; each thread pays from its own

**Status:** accepted (maintainer rulings 2026-11-11, #5066). **Related:** ADR-5066 (a
movement power is an application of a capability, and each use is a cast), #4736 (burning
resonance), #4732 (drift and the focus roll), #1834 (a distinction's resonance potency).

A pull was one resonance: every pulled thread had to share the resonance the pull named, the
web dialog asked for that resonance before it listed threads, and `CombatPull` and
`SceneActionPullDeclaration` stored it. The maintainer dropped the limit for every pull,
declared or automatic, in a fight or a scene: a pull takes any of her threads, and each thread
pays its tier's cost from its own resonance (`pull_resonance_costs`), all resonances debited
under one lock or none (`spend_resonance_for_pull`). Neither row stores a resonance any more;
what each resonance paid is derived from the pull's threads, so corruption is still charged per
resonance. Four things were keyed on the one resonance, and each was ruled: a burn comes from
one pulled resonance the player names (a pull of one resonance burns it without naming it;
`burn_resonance`, `CombatPull.burned_resonance`); a distinction's resonance-scoped POWER bonus
folds in once per distinct pulled resonance; the drift focus roll adds its off-aura steps when
ANY pulled resonance's affinity differs from her dominant one; and the saved defensive pull
keeps only a tier (`CombatParticipant.defense_pull_resonance` is gone) and takes every related
thread of any resonance. **Rejected:** keeping the column as "the pull's single resonance, null
when mixed" (a second way to say what the threads already say, and empty exactly when it would
matter); refusing a burn on a mixed pull (it would quietly re-impose the limit on anyone who
strains); folding only the largest distinction bonus (an arbitrary pick among potencies she
holds equally).

> Verify against `src/world/magic/services/resonance.py` (`spend_resonance_for_pull`,
> `_lock_pull_resonances`, `preview_resonance_pull`, `_fold_distinction_pull_bonus`),
> `src/world/magic/services/threads.py` (`pull_resonance_costs`),
> `src/world/magic/types/pull.py` (`CastPullDeclaration.resonances`, `.burned_resonance`),
> `src/world/magic/services/techniques.py` (`_add_thread_spends`),
> `src/world/magic/services/drift.py` (`check_resonance_focus`) and
> `src/world/combat/services/auto_pull.py`.
