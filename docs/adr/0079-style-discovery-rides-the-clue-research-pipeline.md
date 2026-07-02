# Style discovery rides the clue→codex→RESEARCH pipeline, not a parallel unlock model

Throwback architectural styles (#1469) are discovery-gated through the existing
Investigation & Discovery substrate: a style's `codex_subject` FK (already on
`ArchitecturalStyle`) is the gate, `CharacterCodexKnowledge` (KNOWN) is the
unlock state, and the unlock is earned by researching a CODEX-target `Clue`
through the RESEARCH project kind (`resolve_research` grants the entry to every
contributor). `can_build_style` reads that state; `SetBuildingStyleAction` is the
one player verb. We rejected a style-specific unlock model (a
`PersonaStyleUnlock` table or a new project kind): it would duplicate the
discovery-state the clues/codex apps already own, split "what has this character
learned" across two systems, and add authoring surface for no player-visible
difference. Cost consequence: `cost_multiplier` ships as a data knob only —
charging awaits the economy pass (Phase-E cost deduction is itself unwired), a
deliberate placeholder per the magnitudes-later convention.

> Status: accepted · Source: #1469; composes #1143/#1146 (clues, research) and
> the #1514-era style model; supersedes nothing.
