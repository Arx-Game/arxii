# Covenant of the Court: a leader and their retinue, as a third covenant type

A powerful character whose strength is partly tied to a covenant **role** but who has no peers can
still hold one by forming a **Court** — a third covenant type alongside the Covenant of the Durance
and the Covenant of War, modelling a single powerful leader and the servants/apprentices/acolytes
sworn to them across a wide power gulf — by design at least one power tier (ADR-0046) separates the
Court leader from their servants — explicitly **not** a co-adventuring party (e.g. "the Court of
Shadows" serving the Shadowlord; the "henchperson to a remote master" fantasy). We add it as a new
`CovenantType` value (`COURT`) on the existing `Covenant` model and **reuse** the existing pieces — the
`CovenantRank` authority ladder already models one leader (founder, tier 1) over Member-tier
underlings, and role power is already per-character and peer-independent (`CovenantRoleBonus` scales on
the holder's own level), so the leader's role still specializes by resonance/thread through the one
engine (`resolve_effective_role`, ADR-0055); Court-specific roles are authored `CovenantRole` rows
scoped by covenant_type. We rejected a new model, a new hierarchy field, and a plain `Organization` —
the first two already exist, and a Court needs covenant-only machinery (sworn oath, role power,
thread/resonance specialization, Legend), so a covenant type avoids a parallel implementation
(ADR-0016). It is **not** `MentorBond`, which is a combat-adjacency level-clamp for a co-present,
in-band pair — the opposite of a never-level-adjacent master. ADR-0042's min-2 floor **stands**: a
Court is a leader + ≥1 retained member (and auto-dissolves if all leave); we deliberately do not carve
a covenant-of-one exception. Role/rank orthogonality (ADR-0043) is what makes it work — the master
holds high role power *and* top rank authority while servants hold lesser roles — and no
`is_leadership` flag returns.

> Status: accepted · Source: design discussion 2026-06-27 · Confidence: verify against code — new `CovenantType.COURT`; reuses `CovenantRank` + `resolve_effective_role` (`world/covenants`)
