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
conditions whose `ConditionCategory.alters_behavior=True` — e.g. the fury `Berserk`
condition (category `Control`), possession, charm, mind-control. It is a read-time
derivation on `CharacterSheet`, not a stored column.
_Avoid_: self-control flag, dominated flag.

## Web / telnet labels

- **Shift** (verb shown in the `FormSwitcher` dropdown label and telnet `form shift`):
  assumes an alternate self.
- **Revert** (verb shown on the `FormSwitcher` revert button and telnet `form revert`):
  restores the captured return anchors.

## Shapeshift lifecycle

**Assume**:
To activate an alternate self, swapping in its form/persona facets and granting its
stat and ability suites. Not gated by `in_control`. Strictly-one-active: raising a
second while one is active raises `AlternateSelfActiveError` (would orphan the
prior grants) — revert first. A cross-sheet `form`/`persona` FK raises
`FormOwnershipError` / `ActivePersonaError`. _Avoid_: shift, activate.

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

## PC-to-PC identification (#1107 slice 5)

**Identification check**:
The `CheckType` (intellect + Investigation) a viewer rolls to recognize who's really
under a target's fake-name persona/overlay — `world/forms/services/identification.py`,
seeded by `ensure_identification_check`. Distinct from `Search` (perception +
Investigation) and from the illusion-*piercing* contest (perception vs. a MAGICAL
overlay, still senior-dev/future work) — Identification answers "who," piercing
answers "is this even fake." _Avoid_: recognize check, unmask roll.

**Familiarity tier**:
How much a viewer's prior connection to the target eases an Identification check's
difficulty: an active `CharacterRelationship` toward the sheet under the mask ("knows
personally"), and/or the target's TRUE persona `fame_tier` ("famous likeness"), each
contributing its own ease (currently combined additively — a PLACEHOLDER combine
rule, see `appearance_and_identity.md` §"Identification loop (slice 5)"); neither
present is the "stranger" case (no ease). _Avoid_: recognition bonus, familiarity
score.

**Fake-ID botch**:
An Identification check's worst outcome band (`success_level <= -2`): the viewer
mistakenly and confidently names a random active `Functionary` NPC
(`random_active_functionary()`, `world/npc_services/functionaries.py`) as who's under
the mask — never a real PC (the spec's oracle rule against false-fingering another
player). Degrades to a plain failure when no Functionary exists to blame. _Avoid_:
false positive, misidentification.
