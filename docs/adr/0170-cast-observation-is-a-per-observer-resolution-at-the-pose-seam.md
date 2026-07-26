# Cast observation is a per-observer resolution at the pose seam

> Note: this ADR was drafted as 0167 and renumbered to 0170 when the branch rebased.
> `main` had carried two ADR-0164 files and resolved that by renumbering the #2700
> technique-style decision to 0167, then added 0168 and 0169 — so 0170 is the next
> free number. Check `ls docs/adr/` rather than assuming one past the highest.

#2710 asked how "how absolute is subtle casting" should work now that style is a
property of the caster's Path (ADR-0167): if a caster's style is Subtle, does *nobody*
ever notice, or is it a contest? The answer is a contest, resolved once per observer at
the moment the cast poses, not a global on/off switch on the Technique or the Interaction.

## Decision

**`resolve_cast_audience(*, caster, cast_openly=False)` resolves who perceived a cast,
and in how much detail, per co-located observer, at cast time** — never a single
room-wide "is this cast visible" boolean. Concealment is a magnitude
(`TechniqueStyle.cast_concealment`, a `PositiveSmallIntegerField`, default 0), not a
flag: 0 means overt and the caster's style imposes no difficulty floor at all — the
detection path returns before running any query or check, so every pre-#2710 style
stays byte-identical. Above 0, each observer rolls the detection `CheckType`
(`DETECT_CAST_CHECK_NAME`) against `cast_concealment + level_opposition(caster)`
(ADR-0166) and lands in one of three tiers: `success_level >= 2`
(`CAST_DETECTION_ATTRIBUTION_LEVEL`) sees the full attributed pose, `== 1` sees a vague
unattributed line, `<= 0` perceives nothing. The caster is unconditionally in the full
tier — you always know what you just cast.

**The resolved audience is MATERIALISED as `InteractionReceiver` rows under a new
`InteractionVisibility.PERCEIVED_ONLY` tier, not recomputed at read time.** Both
interactions a cast writes — the Narrator OUTCOME pose and the caster's own ACTION row
(`world/scenes/cast_services.py`) — carry the resolved tier and receiver set. A scene
log must replay what each viewer perceived **at the time**, and only a snapshot can do
that: recomputing on every read would let a bystander who *later* picks up a
magic-detection capability retroactively "see" a cast their character genuinely missed
when it happened, silently rewriting history every time the log is opened.

## Why not `can_perceive` / `ConditionInstance.detected_by`

Both answer a different question: "can A perceive B **right now**," for a **standing**
thing — `can_perceive` gates live interaction with an already-concealed object or
character, and `detected_by` persists which characters have detected an ongoing
`ConditionInstance`. A cast is an **act**, not a state: it happens once and is over.
There is nothing durable to attach `detected_by` to, and reusing it would mean minting a
throwaway `ConditionInstance` per cast purely to hold an M2M — machinery built for
persistence pressed into service for an instant.

## Why a new tier rather than `VERY_PRIVATE`

`InteractionVisibility.VERY_PRIVATE` already existed and already means "hidden from
almost everyone," so it was the obvious first reach. It's wrong: `VERY_PRIVATE` admits
**no** exception, staff included (`InteractionQuerySet.visible_to` excludes it from both
the staff branch and the scene-GM branch; `can_view_interaction` denies staff too). A
concealed cast worked in a GM's own running scene must stay legible to that GM — a scene
has to stay runnable, and a magic system a GM cannot see into is a magic system they
cannot adjudicate. `PERCEIVED_ONLY` is the new, strictly looser tier: writer +
`InteractionReceiver` rows, **plus** staff and the scene's GM. The GM exception is a
scene-log read guarantee only (`InteractionQuerySet.visible_to`'s `gm_visible` branch,
`world/scenes/managers.py`) — a non-staff GM is denied by both `CanViewInteraction` (REST
object access) and `can_view_interaction` (the reaction-witness gate), which admit staff
only, same as `VERY_PRIVATE`. The two tiers are not interchangeable, and nothing about
`VERY_PRIVATE`'s semantics changed.

## Why capabilities are a bonus into the detection check, never an auto-detect threshold

A magic-detection capability (once content authors a `CheckTypeCapabilityModifier` row
bridging it to `DETECT_CAST_CHECK_NAME`) folds into the detecting observer's roll like
any other capability bonus — it never short-circuits the roll into an automatic "you
detect any concealed cast in range." Capabilities are magnitudes on a ladder (ADR-0164),
and a hard auto-detect threshold would collapse the whole contest the moment a character
crosses it: concealment stops being a magnitude the moment detection stops being one.
This was an explicit stakeholder ruling, not a default inherited from ADR-0164 by
analogy.

## Rejected alternatives

**A boolean `is_subtle` flag** (on the style, or on the technique). Rejected for
flattening a spectrum the paths genuinely differ along — the whole point of
`cast_concealment` as a `PositiveSmallIntegerField` is that a Whisper-style caster and a
merely-quiet Incantation caster can both be "not overt" while presenting very different
difficulty floors. A boolean would have reproduced the ADR-0164 lesson (style content
punished a same-shaped boolean gate 71% of the time) one field over.

**Recompute the audience at read time from each viewer's current capabilities**, instead
of materialising receiver rows. Rejected as the retroactive-detection leak described
above — see "Decision."

**Reuse `VERY_PRIVATE` for concealed casts.** Rejected — see "Why a new tier."

**Route detection through `can_perceive`/`detected_by`.** Rejected — see "Why not
`can_perceive`."

> Status: accepted · Source: #2710 · Confidence: built and wired —
> `world/magic/services/cast_observation.py:resolve_cast_audience`,
> `TechniqueStyle.cast_concealment`, `InteractionVisibility.PERCEIVED_ONLY`, both cast
> poses in `world/scenes/cast_services.py`, `SceneActionRequest.cast_openly`. Inert until
> content authors `DETECT_CAST_CHECK_NAME`, a `CheckTypeCapabilityModifier` bridge row,
> and non-zero `cast_concealment` values — all lore-repo content, not arxii seed data.
