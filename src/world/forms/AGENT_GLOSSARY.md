# Forms glossary

Domain-local vocabulary for physical identity, appearance, and shapeshift.

## Identity / physical

**Form**:
A saved set of `FormTrait`/`FormTraitOption` values describing a character's physical
body at a point in time. `FormType` distinguishes `TRUE` (current real human body +
cosmetics), `ALTERNATE` (a shapeshifted real body), and `DISGUISE` (a fake overlay).
_Avoid_: shape, body.

**True Form**:
The character's real, cosmetic-bearing body as it exists right now before any
shapeshift — the return point for an alternate form. _Avoid_: natural form.

**Alternate Self**:
A bundle of optional facets (`form`, `persona`, `combat_profile`, `techniques`) that a
character may assume as a single shapeshift/identity shift. Stored in
`forms.AlternateSelf`; the currently assumed one is tracked per-character in
`forms.ActiveAlternateSelf`. _Avoid_: alt form, shape.

**In Control**:
Whether the character is currently in control of their own actions. Derived from active
conditions whose `ConditionCategory.alters_behavior=True` (rage, possession, charm,
mind-control). It is a read-time derivation on `CharacterSheet`, not a stored column.
_Avoid_: self-control flag, dominated flag.

## Shapeshift lifecycle

**Assume**:
To activate an alternate self, swapping in its form/persona facets and granting its
stat and ability suites. Not gated by `in_control`. _Avoid_: shift, activate.

**Shift Form**:
Player-facing verb for the assume action (registry key `"shift_form"`,
`ShiftFormAction`). The backend canonical term remains **Assume**; this is the
surface label shown to players. _Avoid_: activate, transform.

**Revert**:
To restore the return anchors captured at assume time and remove the granted stat/ability
rows. Blocked while `not in_control` (`RevertBlockedError`). _Avoid_: shift back.

**Revert Form**:
Player-facing verb for the revert action (registry key `"revert_form"`,
`RevertFormAction`). The backend canonical term remains **Revert**. _Avoid_:
shift back, return to normal.
