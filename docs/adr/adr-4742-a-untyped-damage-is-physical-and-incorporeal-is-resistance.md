# ADR-4742-A: Untyped damage is Physical, and incorporeal is resistance, never untargetability

Damage with no damage type is Physical. `resolved_damage_type` substitutes
`VitalsConsequenceConfig.physical_damage_type` at the entry of every damage seam, so resistance,
cover, property bonuses, damage interactions and consequence pools all treat a weapon hit as
Physical. This reverses the #1588 contract that untyped damage skips resistance. That contract
made every production weapon (all four templates are untyped) immune to every Physical and
all-types resistance row staff had authored (Flanked, Prone, Exposed, Protected and others),
and it would have made an incorporeal form's Physical resistance meet no real weapon. We
designate the row by a config foreign key, not by its name (rows are found by field, never by
string), and the field is nullable only so an empty database still runs. It is not an opt-out:
the owner ruled "if it's not specified, it is physical". The rejected alternative was a
staff-side rule to give every weapon and threat a damage type. It leaves a default that silently
bypasses resistance whenever someone forgets one.

Incorporeal (`ConditionCategory.grants_intangibility`) no longer removes the bearer from NPC
target picks or area casts. Its protection is a severity-scaled Physical resistance row on the
condition, subtracted per hit, so ordinary blows do nothing and an overwhelming one lands the
difference. The owner ruled that nothing is invulnerable. The flag still means the bearer holds
no ground. A knockback rider now needs a hit that survives resistance. The bearer's own strikes
are weakened per damage type by `ConditionDamageDealtModifier`, a percent on outgoing damage. We
chose a new table over a direction column on `ConditionResistanceModifier`, because resistance is
a flat amount off incoming hits and this is a percent on outgoing ones. We did not use
damage-type-scoped power targets: they scale technique power but not weapon damage, they match
a whole technique, and they skip untyped profiles.

> Status: accepted · Source: owner rulings 2026-10-27 on #4742 · issue #4742
