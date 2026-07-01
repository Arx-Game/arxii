# Legend is earned only from difficult victories

Legend awards are gated on both risk (`Beat.risk` != `RenownRisk.NONE`) and success
(`BeatCompletion.outcome == SUCCESS`), and scaled by how decisive the win was
(`RISK_LEGEND_AWARDS[risk] * tier_multiplier(outcome_tier.success_level)`, see
`world/mechanics/effect_handlers.py::_legend_award`). A no-risk win earns nothing; a
defeat earns nothing but never erases previously-earned Legend (monotonic, consistent
with `lifetime_earned` per ADR-0054). This sharpens ADR-0036 (combat merits Legend,
never XP) into the general stakes/consequence engine (#1716): the same formula now
applies to any staked beat (combat, mission, or scene), not just combat.

We rejected awarding Legend for participation or completion alone (the common RPG
default) because the game's progression philosophy is deliberately hard: characters
advance by repeatedly attempting difficult, risky things and winning, not by showing
up. A structural consequence — not enforced by this ADR, purely emergent from the
math — is that solo advancement becomes statistically non-viable at high risk tiers,
pushing play toward groups (the same force behind the battle spine's peril/rescue
mechanic, #1733).

> Status: accepted · Source: #1716
