# ADR-0097: Kinship is a person-node graph with typed edges and a truth-vs-public-record split; reincarnation is a Soul entity

#2062 replaces the family-scoped `FamilyMember` tree (binary mother/father
FKs) with person-centric `Kinsperson` nodes and typed facts, because the
setting's cases all break the two-gendered-slots assumption: Tree-of-Souls
polycules (N parents, any composition), vampiric progeny (a progenitor edge
*coexisting* with biological parents), foster/adoptive/acknowledged kinds
with different legal weight, and Misbegotten whose parentage is an
absent-or-hidden fact gameplay reveals. Three deliberate shapes: (1) every
relationship readout is **derived by walking typed edges** — nothing like
"cousin" is ever stored — which kills both Arx 1 failure modes (silent
auto-derivation and unmarked in-laws: step-parents and in-laws derive from
`Union` edges, so blood-vs-marriage is never ambiguous) and makes ripple
consistency structural (an added brother IS an uncle on the next walk);
(2) facts carry `is_public_record` + `is_true`, with hidden facts anchoring
a `Secret` (consumer→primitive, ADR-0010) so who-knows/discovery rides the
existing machinery — a public-false edge is "what everyone believes,
wrongly", and `Secret.subject_aware=False` lets even the subject start
ignorant; (3) reincarnation is a first-class `Soul` with ordered
`SoulIncarnation` memberships rather than pairwise past-life edges, because
chains (PC ← Monique ← Covet) must be transitively consistent by
construction and knowledge must be per-life (learning your own membership
reveals the famous public life but not a hidden intermediate one). Rejected
alternatives: evolving mother/father in place (cannot represent N-parent or
progenitor-plus-parents cases); a per-viewer belief database (the
public-record/secret split covers every named case at a fraction of the
complexity); pairwise reincarnation edges (chains drift and dedup logic
grows unboundedly).

> Status: accepted · Source: #2062, ratified in dialogue with Apostate 2026-07-06/07 · Supersedes the pre-#2062 FamilyMember stub
