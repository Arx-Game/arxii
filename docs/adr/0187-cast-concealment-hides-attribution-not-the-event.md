# Cast concealment hides attribution, not the event

ADR-0170 built cast observation as a three-tier ladder where the bottom tier "perceives
nothing." #2734 extended that seam into combat and the model broke: a concealed working
could wound, knock out or drop a PC whose feed showed an empty round and a health bar
that silently moved. The OUTCOME pose is the *only* channel that tells a player what
happened to them — vitals are viewer-scoped, and no damage path emits a separate message
— so hiding the pose from a non-detector erases the event from the one place it existed.

That was never the fantasy. Concealment is a sniper shot: the room may not know where
it came from, but nobody's head explodes in secret.

## Decision

**A concealed cast hides who worked it, not that it happened.** `CastAudience` carries
three tiers, and they are a ladder of *attribution*, not of existence:

| Tier | Roll | Reads |
|---|---|---|
| `full` | `success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL` | the attributed narration — caster and technique |
| `vague` | `== 1` | the effect, plus that it was *a working*, still unattributed |
| `effect_only` | `<= 0` | the effect alone, with no sense that magic was involved |

No observer receives more than one pose, and no tier is ever told strictly less than a
tier that rolled worse — `vague` folds the effect line in rather than replacing it.

**The one thing that still vanishes is a working with nothing to perceive.**
`Technique.has_perceptible_effect` (BooleanField, default `True`) marks the rare
technique — a silent binding, a curse laid at a distance — that produces no outward
event. For those, `effect_only` stays empty and the pre-#2734 hide-outright behaviour
holds. The default is `True` because almost any applied condition produces something a
bystander would see; the imperceptible working is the exception that opts out, not the
rule.

**Contact defeats concealment, and reach is what encodes that.** A `SAME`-reach
technique returns an unconcealed audience before any query or roll: you have to be
standing on someone to stab or touch them, so the act gives the actor away no matter how
subtly its caster works magic. This is what makes a melee attack unconcealable — not
whether it is "magical."

**Fail-closed now fails closed on attribution only.** A missing `DETECT_CAST_CHECK_NAME`
CheckType means nobody can be *attributed*, but a perceptible working is still narrated
to the room. ADR-0033's rule is that a misconfiguration must not leak; erasing every
combat event from every participant's feed is not a safe default, it is a different
failure.

## Why not `Gift.is_magical`

The first cut of #2734 added `Gift.is_magical` to separate a working from a sword swing,
because `Technique.gift` is non-null and every technique therefore hangs off a `Gift`.
Rejected: **every Gift is magical by definition — that is what a Gift is.** The column
was a proxy invented to answer a question the conflated model created, and it dissolved
along with the conflation. The residual wart it was pointing at is real but separate:
`world/combat/defend_content.py` seeds a `Gift` purely as a container for combat stances,
because techniques need somewhere to hang. Making `Technique.gift` nullable is its own
change.

## Why the unattributed line drops the suffix clauses

`render_unattributed_action_narration` carries none of the three clauses the attributed
line appends. The signature clause is the caster's personal authored flourish (#1728) —
the single strongest attribution tell in the system. The power clause names "the working"
or "the ward", telling an `effect_only` observer that magic was involved when not
knowing that is precisely what defines their tier. The synergy clause narrates condition
interplay that reads as authored magic. Each is a leak of exactly the thing the tier
withholds.

## Rejected alternatives

**Always emit a public effect line, with no per-technique gate.** Simplest rule, no new
column — but it makes a subtle binding announce itself ("something happens to Corvin"),
breaking the Whispers fantasy in the other direction. The authored flag costs one column
and gets both ends right.

**Derive perceptibility from the payload** (has damage profiles → visible;
conditions-only → not). Attractive because it needs no new field, but wrong on the
merits: a flashy condition-only working is perceptible and a silent damage-over-time is
not. Perceptibility is an authoring judgement, so it is authored.

**Keep concealment as an existence dial and special-case combat.** Rejected: it leaves
two different concealment models in the game depending on whether a fight is running,
and the scene path has the same defect in milder form.

> Status: accepted · Supersedes the tier semantics of ADR-0170 (its per-observer
> resolution, receiver-row materialisation, `PERCEIVED_ONLY` tier, and
> capabilities-are-a-bonus rulings all stand unchanged) · Source: #2734 · Confidence:
> built and wired — `CastAudience.effect_only`, `resolve_cast_audience(technique=)`,
> `Technique.has_perceptible_effect`, `render_unattributed_action_narration`,
> `render_unattributed_cast_narration`, both cast paths. Inert until content authors
> `DETECT_CAST_CHECK_NAME` and non-zero `cast_concealment` values.
