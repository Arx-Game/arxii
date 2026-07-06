# 0095 — GM trust is `GMProfile.level`, capped by `GMLevelCap`, advanced only via `promote_gm`

**Status:** Accepted

Before #2000, a GM's trust lived in two places that never talked to each other:
`GMProfile.level` (a `GMLevel` enum field that every GM already carried, but nothing
read or wrote) and `PlayerTrust.gm_trust_level` (read by `combat.StakesLevelRequirement`
and the stories risk gates, but with no promotion path — no code ever wrote it either).
Both were dead: a GM's actual trust tier was unearned and unenforced no matter which
field you looked at. We made `GMProfile.level` canonical: per-level caps live on
`GMLevelCap` (`max_beat_risk`, `allow_custom_stakes`, `allow_global_scope_authoring`,
staff-tunable, seeded via `seed_default_gm_level_caps`), and the only way `level`
changes is `world.gm.services.promote_gm` — a staff-only, audited call that writes a
`GMLevelChange` row every time. `stories.BeatSerializer`'s risk gate,
`stories.StakeSerializer`'s custom-stakes gate, and
`combat.StakesLevelRequirement.minimum_gm_level` all now read `GMLevelCap` (or the
plain `GMLevel` ordering) through this one field instead of the abandoned
`PlayerTrust.gm_trust_level`.

**Rejected:** keeping `PlayerTrust.gm_trust_level` canonical — GM trust is a property of
running stories at all (an account-level permission ceiling that predates any specific
story), not of a specific story's participation trust; `PlayerTrust`/`TrustCategory`
correctly stay scoped to per-category *content* trust (a player's comfort/consent
signal within a story), and folding GM promotion into that model would have made the
`stories` app own an `gm` app concern. Also rejected: automatic feedback-driven
progression curves (auto-promoting on upvote/rating thresholds) — with no real
production data yet this is trivially gameable (a GM's own alt farming ratings), and
the evidence dashboard (`gm_evidence_summary`) already surfaces the same signals to a
human reviewer; automatic curves are deferred until there's a real track record to
calibrate against.
