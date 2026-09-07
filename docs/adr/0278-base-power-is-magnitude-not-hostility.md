# ADR-0278: base_power is a magnitude knob, never a statement of hostility

**Status:** Accepted (#3682, 2026-09-07). Related ADR-0024, ADR-0064, ADR-0119, ADR-0248.

**Context.** `is_technique_hostile` (`world/magic/services/hostility.py`) has answered
`True` for any technique whose `EffectType.base_power` is non-null since it was written
in #772/#779, on the reading "power-scaled effect, therefore offensive." The authored
catalog does not agree with that reading: `Defense` carries `base_power` 10, as do
`Weapon Enhancement`, `Attack` and `Ranged Attack`. Power scaling is what
`has_power_scaling` and `base_power` are *for* — how big the effect gets — and the
authored payload rows (damage profiles, and applied/removed conditions with their
`target_kind`) are the only place a technique says who it is aimed at.

The consequence was not cosmetic. All 54 Defense techniques in the live catalog
classified as hostile, and `derive_target_relationship` gives hostility precedence over
the SELF and ALLY conditions those techniques actually carry (43 SELF, 3 ALLY). So a
shield cast at another character routed through `_route_hostile_cast` rather than the
benign path ADR-0119 built for exactly that case; the ENEMY branch of
`_check_relationship` refused to let a self-shield name its own caster as a target; and
every consent, aggro and combat-seeding branch keyed on `is_technique_hostile`
(`world/scenes/cast_services.py`, `world/scenes/action_serializers.py`,
`actions/definitions/social.py`) read protection as aggression.

**Decision.** Hostility is derived from the payload rows alone — a damage profile with
`base_damage > 0`, an ENEMY-targeted applied condition, or an ENEMY-targeted removal
(the dispel case, ADR-0064). `base_power` is not consulted. The module's own docstring
already said this; the branch was the outlier.

Checked against the live catalog before removing it: every `Attack`, `Ranged Attack` and
`Weapon Enhancement` technique keeps its hostile classification on its damage profile,
and only `Defense` changes — 51 to SELF, 3 to ALLY. No offensive content is disarmed.

**Consequence.** A technique with no payload rows at all now reads benign rather than
inheriting hostility from its effect type. That is the honest answer for unauthored
data, and it is already reported separately: `technique_is_underspecified` flags exactly
that state on the player-facing summary ("Its effects are not yet catalogued") and in
the `TechniqueAdmin` authoring-gap column and filter. An author who creates an offensive
technique and forgets its damage rows is told so, rather than being silently rescued by
the effect type.

`EffectType.category` (`TechniqueCategory`) was considered as a replacement signal and
rejected: it is a player-facing grouping, every authored row currently sits at its
`utility` default, and keying a safety-relevant classifier on a display field would
recreate the same confusion of presentation with intent one field over.

**Rejected alternative.** Keep the shortcut and fix the data by nulling `base_power` on
`Defense`. Rejected because `base_power` is genuinely non-null there — Defense scales
with power, and the DE evaluator and severity scaling both read it. Blanking it to fix a
targeting bug would break magnitude to fix intent.
