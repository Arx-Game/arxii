# Species glossary

Domain-local vocabulary for `world.species`. Root terms live in
`AGENT_GLOSSARY_MAP.md`.

- **Species** — a playable kind (Human, Khati, Infernal, …) or a subspecies
  under a `parent` (Khati → Vulpi/Cani). The parent link is taxonomy for
  grants/palette inheritance, NOT ancestry of an individual character —
  ancestry is the roster kinship graph. _Avoid:_ race (legacy term).
- **Species palette** — the `forms.SpeciesFormTrait.allowed_options` set for
  a (species, trait) pair: which colors/variants that species can normally
  take in CG. Empty = all options. Colors outside every supernatural palette
  but inside Human's are how human blood shows on a supernatural child.
- **Required trait** — `SpeciesFormTrait.is_required=True`: a species
  identity marker (horns + tail for True Infernals, wings for Daeva, fangs
  for vampires) that CG must fill. Species identity is protected by required
  structural traits, never by rationing colors.
- **Chimeric species** — a unique authored `Species` row (with its own codex
  entry) for a true halfbreed, possible only when both parents are Grand+
  (level 16+). Authored per pairing by staff; never computed. _Avoid:_
  halfbreed flags or generic "Chimera" rows.
- **Parent Dominance / power band / heredity** — live in the roster glossary
  (`world/roster/AGENT_GLOSSARY.md`); the rules engine is
  `world.roster.services.heredity`. _Avoid:_ "crossing" for species mixing —
  crossings are the magic-progression thresholds (3/6/11/16/21).
