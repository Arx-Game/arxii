# ADR-0095: Casts roll the caster's personal check in every path

**Status:** Accepted (2026-07-06) · **Issue:** #2014

Every technique cast — standalone scene cast, combat round cast, clash
contribution, and battle technique resolution — resolves its check through
`resolve_cast_check_type` (`world/magic/services/anima.py`): the caster's
provisioned personal magic check (their anima-ritual stat+skill CheckType,
#1306) always wins; an `ActionTemplate.check_type` is a fallback for
unprovisioned casters, never an override. Before this, combat, clash, and
battle resolution (`BattleTechniqueResolver.__call__`,
`world/battles/resolution.py`) read `template.check_type` directly, so every
combat/battle cast rolled the shared willpower+occult fallback and a
charm-built caster's identity was erased the moment a fight started —
contradicting the recorded design ("every caster rolls *their own* magic
check", `src/world/magic/CLAUDE.md` §Standalone Casting) and the stat+skill
tenet. Rejected alternative: template-as-override precedence (an authored
template check beating the personal check) — #1320's catalog templates
deliberately share one check_type, so no authored content relies on
per-template divergence, and an override rule would silently re-homogenize
casters again. Calibration note: the Monte Carlo tuning simulator's synthetic
party is unprovisioned and unaffected; live provisioned PCs may see win-rate
drift.
