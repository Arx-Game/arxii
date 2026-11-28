# Magic glossary

**Affinity**:
One of the three magical sources — Celestial, Primal, or Abyssal — modeled as a first-class domain entity with an optional link to the modifier system. Every Resonance belongs to one Affinity.

**Aura**:
A character's soul-state expressed as a percentage share per Affinity, one `CharacterAuraShare` row per affinity, constrained to sum to 100. Its presence is the derived gate for whether a character can work magic at all. The shares are the character's lifetime resonance by affinity (`recompute_aura`); who the character IS is a separate per-affinity figure, the **Settled share**. Shown to players in words ("mostly primal, a third abyssal"), never as numbers.

**Acting aura**:
The aura a character acts with right now: 100% of the worn alternate self's resonance affinity when it has one, otherwise her true aura. Casts (alignment, and the affinity the cast works in), places of power, defilement and covenant attacker affinity read it; the Fall, the Soul Tether gate and the sheet display keep the true aura. Looked up with `acting_aura(sheet)`. _Avoid_: effective aura, mask aura.

**Unsettled** (#5123; replaces the older reading of drift):
The state of a character whose aura has grown past who they are: an affinity other than their main one stands over its **Settled share** by more than the **Range before Unsettled** that applies to it (which affinities are read, and at which range, depends on the main affinity and the character's lean; see **Range before Unsettled** and **Own-side range**). The **Mire** is corruption, not a share of the aura, so it has no part in this reading (#5177); a Sineater who **Succumbs** grows the Sinner's resonance in their own aura, which can make them unsettled like any resonance. Measured by `drift_for(sheet)` on the TRUE aura and on lifetime resonance, never on spendable balance, so spending the excess does not settle it. A mixed character is not unsettled for holding a second affinity; only for growing it past who they are. Unsettled makes a cast call for a focus check, harder by the step width (`unsettled_step_percent`, per main affinity like the range) the further past. The one way out is the **Rite of settling**, over what the character reflected on: it **Atones** (Disown the unsettling resonance, up to the open **Conversion offer**) or accepts the aura's change (Embrace it, `accept_aura_change`). The player-facing line is "Your {Resonance} has grown strong enough to make you unsettled." _Avoid_: drift (the code's `drift_*` names read this state; see **Drift**), corruption, taint, off-aura.

**Range before Unsettled** (#4751):
How many percentage points another affinity may grow past its **Settled share** before a character led by a given main affinity is **Unsettled**. Set per main affinity on `Affinity.unsettled_tolerance_percent`, with the step width on `Affinity.unsettled_step_percent`; blank uses the general `DriftConfig.unsettled_tolerance_percent` and `unsettled_step_percent`. Celestial's is small, so a Celestial-led character unsettles early by her own Abyssal acts. Read through `_unsettled_numbers` in `services/drift.py`, and chosen by side in `_range_for` (#5231): a Celestial main reads Primal and Abyssal at Celestial's range; an Abyssal main reads Celestial only, at Abyssal's range, and never Primal; a Primal main that leans to a side (the larger settled share of Celestial and Abyssal) reads the opposite side at the range of the affinity she leans to and her own side at the **Own-side range**; a Primal main with no lean reads Celestial and Abyssal at Primal's range. The word "room" is only ever a game room.
_Avoid_: room, headroom, tolerance (the field name; players and staff read "range before Unsettled"), threshold (an older, removed figure).

**Own-side range** (#5231):
How many percentage points a Primal character's own side may grow past its **Settled share** before she is **Unsettled**. Her own side is whichever of Celestial and Abyssal she leans to, the larger settled share of the two; growth on the opposite side is measured against the range of the affinity she leans to instead. Set once on `DriftConfig.own_side_tolerance_percent` (15 to start), not per affinity. A Primal character with no lean has no own side and keeps Primal's range for both. _Avoid_: room, headroom, own tolerance.

**Worked in** (#5231):
The one resonance a cast is made in, and the resonance its power and its corruption follow. `cast_resonance_for(character, technique, preferred)` finds it: the resonance the caster names, else a worn alternate self's, else the leading resonance of the Gift's thread, else the Gift's own first resonance when she has no thread on the Gift; a Gift with no resonance is worked in none. A named resonance with no row on the Gift's thread is refused before anything is charged ("That resonance is not part of this Gift's thread."), and a stored choice the thread has lost since falls back to the default and never refuses a round or a consent-gated cast. Choosing the base form does not change it: the form and the resonance are separate choices. _Avoid_: cast in (reads as a place), channelled; and do not say "the cast's resonance" when the thread's leading resonance is meant.

**Reflection** (#5124):
What a pose or a journal entry (White or Black) says it reflects on: one deed the character has not reflected on (a kindled deed, or, since #5177, a succumbing), the resonance that is unsettling them, or the **Mire** they carry for one Sinner (a **Burden reflection**), and what they do with it: **Embrace** or **Disown** a deed or the resonance, **Absolve**, **Condemn** or **Succumb** to a burden. Recorded with the writing (`record_reflection`), it changes nothing until a rite of settling carries it out; a deed is reflected on once, and a newer waiting reflection on the unsettling resonance or on a burden replaces the older. The room sees only the pose. _Avoid_: remorse, confession.

**Kindled** (#5124):
The state of a resonance a character holds when something it cares about is present: one of its **Kindling situations** holds, or a Rally or a GM kindled it by hand. Players see which of their resonances are kindled, how strongly in words, and what kindled each one; the numbers stay hidden. A kindled resonance gives more when a pull is paid with it, can be given in to, surges more on a Dig deep or a Rally, and sets what a **Mark** of that resonance pays. Acting on what kindled it earns nothing by itself: a situation only suggests the resonance beside a **Recorded act**, and only an authored choice such as a mission option's theme pays at once (#5327, ADR-5327). Read live by `kindled_resonances`; never stored for a situation (a **Recorded act** keeps the strengths that were true at the moment). _Avoid_: stirred, activated, triggered, charged.

**Kindling situation** (#5124):
A staff-authored `KindlingSituation` row: one situation (from the covenants `Situation` list, six of them new) that kindles a resonance, set on the resonance itself or once on an affinity so it counts for every resonance of that affinity, with the strength it kindles at and an optional reason line the player reads. The strongest situation present sets how strongly the resonance is kindled. A thread-anchor situation takes the bond's own tier. _Avoid_: trigger, kindle condition, stir.

**Kindled strength** (#5124):
A staff-named step of how strongly a resonance is kindled (Faint, Strong and Blazing to start), one `KindledStrengthTier` row each, compared only by its `rank`. It sets the pull uplift, the deepest Fury tier, the Dig deep and Rally surge, the share of a deed earned and, since #5231, the power a cast **worked in** that resonance gains (`cast_power`, times the resonance's affinity's `kindled_boost_percent`). Players see only the name. _Avoid_: kindle level, intensity (a cast's power), strength of feeling.

**Drawing strength** (#5181):
The general term for a character taking resonance from what moves them or from a willing partner: a kindled deed that pays, a **Mark**, an Anima ritual with a partner. "Feed" is reserved for Abyssal drawing, so an Abyssal ritual feeds on its partner and a Celestial or Primal one draws strength. No corruption comes from drawing strength; corruption falls only through a Sineater. (This is the same term the kindled pull uses: a kindled payer reads a thread higher.) _Avoid_: feeding (for a Celestial or Primal character), harvesting, draining.

**Recorded act** (#5327, ADR-5327):
One act a player character took that has an award row and paid no chosen deed, written down by `award_kindled_deeds` as a `RecordedAct` so her player has something to point a **Mark** at. It keeps a label the game words from the action and its target as the actor knows them ("Intimidated Hale"), an `act_phrase` (the label without the target's name, so every other reader of the pose sees the target under the name THAT reader knows and a mask stays a mask), the result tier and check type (references, not copied numbers, so an award retune reaches waiting acts), the target when a person, the fatigue pool a gain from it charges, and one `RecordedActSuggestion` for each resonance a situation reached, with the strength and the reason line. Unmarked means `marked_grant` is null; an unmarked act stays pointable for `KindlingConfig.recorded_act_days` and is then pruned. A failed roll, an area scene action, an extra target of a multi-target action and a hostile cast accepted into combat leave no record. _Avoid_: deed record, pending deed, claimable act (nothing is claimed any more).

**Mark** (#5327, ADR-5327; replaces the **Claim** of #5181, which is gone):
A pose or a journal entry that names a resonance and points at one **Recorded act** (`reach_resonance_id` with `reach_act_id`). It pays at once as a `MARKED_ACT` gain: the act's `KindledDeedAward` for its result tier times the earn share of the strength a situation reached for that resonance (the lowest strength when none suggested it), cut by the weekly table (`WeeklyMarkReturn`) and by the payer's fatigue room, then grown by the bonus check. Any resonance may be marked, in her aura or not, Primal included. She can mark every act, one after another; an act pays once and a writing carries one mark. The writer alone reads one private line, which opens with the verb staff wrote on that affinity (`Affinity.claim_verb`: "You gloat. Your Cruelty grows by 9."); the room sees only the pose. A mark that would pay nothing is refused and leaves the act pointable (a journal entry that carried it stays posted); in an ephemeral scene a mark pays nothing, because no pose is stored to carry it. A pose that names a resonance and no act is a **Reach**, not a mark. _Avoid_: claim, cash in, redeem, attest (the player attests by marking; the word names the act in play, `mark` names the thing).

**Proposal** (#5327, ADR-5327):
A witness's pick of a resonance on a pose that named none: a `PoseEndorsement` saved with `awaiting_acceptance` set. It pays nothing and settlement skips it until the poser, the scene's GM or staff accept it; declining deletes the row. The witness picks from one list of every resonance, and the menu's list shows nothing about the poser's aura (the pose payload still carries `endorsable_resonances` for entrance and outfit endorsements). She may change the pick (it then waits again, even after an accept) or withdraw it until the weekly settlement pays it. The poser is told once, when the pick is made. A pick the weekly settlement cannot pay because its payer is too worn stays unsettled and is tried again next week. A pose that named its own resonance is confirmed by one click and waits for nobody. _Avoid_: suggestion (that is what a situation does beside a **Recorded act**), request, vote.

**Earn rate** (#5181):
How fast a resonance is earned, as a percentage set on each Affinity (`Affinity.earn_rate_percent`) and applied by the affinity of the resonance earned (#5231), whoever earns it and whatever her own main affinity: 100 is as authored, so Abyssal resonance can grow fast for anyone. It scales resonance newly earned and never resonance that is only moved or converted (`AFFINITY_RATE_EXEMPT_SOURCES`). _Avoid_: earn multiplier, gain speed.

**Learn rate** (#5181):
How fast a character's technique training advances, as a percentage set on each Affinity (`Affinity.learn_rate_percent`) and applied by the character's main affinity: 100 is as authored. The weekly training limit and the action point cost still count the unscaled points. _Avoid_: learning speed, training multiplier.

**Embrace** (#5124):
One of the two things a **Reflection** says. Embracing a deed grows the resonance it earned; embracing the unsettling resonance is accepting the aura's change. Carried out by the **Rite of settling**, never when the reflection is written. _Avoid_: accept (accepting is only what embracing the unsettling resonance does), keep, endorse.

**Disown** (#5124):
The other thing a **Reflection** says. Disowning a deed turns most of what it earned toward the main affinity; disowning the unsettling resonance is atoning, up to the open chance to atone. Carried out by the **Rite of settling**. _Avoid_: remorse, repent, renounce, reject.

**Settled share** (#5123):
Who the character is, per affinity: `CharacterAuraShare.settled_percent`, 0-100, summing to 100 once set. Written at character creation (one Primal pick and at most one Celestial or Abyssal pick, weighted by the player's split, nudged by the Glimpse) and by accepting; read by `drift_for` and by the aura alignment power term. The **main affinity** is the affinity with the largest settled share (a tie goes to Primal, then to the lowest affinity id; #5231), not whatever is largest right now. The settled share never shrinks as a streak fades, so a faded streak can return up to it without unsettling the character. A share row survives with `percent` 0 while its `settled_percent` is above 0. _Avoid_: dominant affinity (the largest CURRENT share, `CharacterAura.dominant_affinity`), baseline aura, true self.

**Mire** (#5177, ADR-5177; replaces the Mire share of #5123):
The corruption a Sineater carries for their Sinners, and only that. It lives on the Sineater's own corruption in a resonance (`CharacterResonance.corruption_current`, with that resonance's corruption condition and stages), and `MireHolding` records how much of it came from which Sinner, per Sineater-side relationship and resonance (`amount`); the holdings in a resonance never sum to more than that corruption. A Sinner sheds only corruption that is their own, so a character who is a Sineater for someone else cannot pass that Mire on. A Sineater takes it on by **Sineating**, softened by their resistance, and it stops at the Compulsion stage (`CorruptionConfig.sineater_max_stage`). They settle it through the rite of settling with a **Burden reflection**: **Absolve**, **Condemn** or **Succumb**. Shown to the Sineater only. _Avoid_: Mire share (removed; the Mire was once a share of the aura, `mire_lifetime`), burden share, Mire balance, taint.

**Sineating** (#5177):
A ritual with a roll, framed by poses in a shared scene. The Sinner's pose asks for it (the plea, `entreat_sineating`, a `SineatingPendingOffer`); the Sineater's pose performs it (`perform_sineating`), chooses how many of the offered units to take on, and rolls `SoulTetherConfig.sineating_check_type`. Each unit moves `corruption_per_unit` of the Sinner's carried corruption onto the Sineater as the **Mire** whatever the roll, and refills the Hollow; the roll's `SineatingOutcomeAward` scales the resonance each of them earns. Since #5231 the corruption moves in the resonance on the Sinner's thread in which she has the most of her own to shed (a tie goes to the resonance with more imbued, then the lower id), the Sineater earns in the resonance of their own thread, and the Sinner is paid across the resonances on her thread by the amounts imbued (the leading one takes the remainder; a thread with nothing imbued pays its leading resonance). A Sinner with nothing of her own to shed is not refused: the ritual performs and says so. It costs the Sineater no anima and no fatigue. Once per pair per scene; refused for a **fallen** Sineater. _Avoid_: consuming sins (the Sineater takes on and carries), the old request-and-accept Sineating (removed).

**Burden reflection** (#5177):
A **Reflection** whose subject is the **Mire** a Sineater carries for one Sinner (`Reflection.tether`, `ReflectionTargetKind.BURDEN`), listed as "The Mire you carry for <Sinner>" and named `mire:<Sinner>` on telnet. It takes **Absolve**, **Condemn** or **Succumb**, written as a pose in a scene or a journal entry, in any amounts and at any time; one large settling and several small ones give the same total. _Avoid_: burden share, confession.

**Absolve** (#5177):
A choice on a **Burden reflection**. The rite clears `floor(held x share)` of the Mire from that Sinner with no resonance granted back, rewards the Sineater with `purify_reward_percent` of it in their own thread's resonance, adds to the **Jackpot**, and moves their side of the tie toward affection. _Avoid_: forgive, cleanse.

**Condemn** (#5177):
A choice on a **Burden reflection**. The same clearing and reward as **Absolve**, and the tie moves toward conflict instead. _Avoid_: punish, curse.

**Succumb** (#5177):
A choice on a **Burden reflection**, always the player's own. The rite turns `floor(held x share)` of the Mire into that much of the Sinner's resonance in the Sineater's own aura (a deed, `GainSource.SUCCUMBED`), which can make them Unsettled and which they can later reflect on and atone for. It pays the Sinner `succumb_bonus_percent` of the amount plus the **Jackpot**, and moves both tie gauges. _Avoid_: surrender, give in (giving in is a **Compulsion**'s lifting), fall (see **Fall of a Sineater**).

**Jackpot** (#5177):
The base the Sinner's extra payout is sized from when a Sineater **Succumbs**: `CharacterRelationship.mire_purified_since_payout` (on the Sineater's side of the tether), what the Sineater has absolved or condemned for that Sinner, in any resonance, since the last payout. It builds while the Sineater resists, belongs to one tether, pays `jackpot_percent` of itself on a Succumb and resets to 0, and atoning does not restore it. Shown to neither party; the Sinner learns the payout when it lands. _Avoid_: pot, bank.

**Fall of a Sineater** (#5177):
What happens when a **Succumb** leaves a Sineater's aura predominantly Abyssal (`sineater_has_fallen`, `dominant_affinity`). Every Sinner they succumbed to since their last fall is paid `fall_payout_percent` of that amount, the Sinner of the most recent succumbing `fall_breaker_bonus_percent` more, and the counters reset (`CharacterRelationship.mire_succumbed_since_fall`, on the Sineater's side of the tether). Until their aura is predominantly something else the Sineater serves no one: Sineating and the rescue refuse (`SineaterFallenError`). Not the **Fall** of a character's affinity (`perform_fall`). _Avoid_: Fall (that is the affinity conversion), break, corruption of a Sineater.

**Intrusive Thoughts** (#5177):
How a character's corruption shows from the stage `CorruptionConfig.intrusive_thoughts_stage`: the condition reads "Intrusive Thoughts: <resonance>" (display only, `corruption_display_name`; no template is renamed). When something the resonance cares about is present in a scene, the character is sent `Resonance.impulse_text` once. Nothing else happens, and the player chooses what the character does. Felt by a Sinner for their own corruption and by a Sineater for the **Mire** alike. _Avoid_: whispers, urge.

**Compulsion** (corruption, #5177):
The later impulse stage (`CorruptionConfig.compulsion_stage`): the corruption condition reads "Compulsion: <resonance>", and while something the resonance cares about is present, `CorruptionConfig.compulsion_condition` (staff author it with a scene duration and a check modifier that scales with severity) penalizes the character's rolls until her player marks a gain in that resonance in that scene (a **Mark**, or a kindled deed she chose from a mission option; `COMPULSION_INDULGING_SOURCES`; an Anima ritual does not lift it, and neither does merely acting on it), which lifts it, adds `compulsion_indulge_corruption` of corruption and, for a Sineater, adds to the Mire. A grant from another player, a GM or a cron, and succumbing to the Mire, do not lift it. Settling below the stage clears it. **Not the `Compulsion` model of `world/conditions/models.py`** (see that glossary's **Compulsion**: an authored block on a behavior-altering condition, with forbidden actions and resist bands). The two are told apart by the code path: the corruption Compulsion is `corruption_display_name`, `refresh_impulses` and `CorruptionConfig.compulsion_condition` in this app; the control-loss one is a `Compulsion` row in the conditions app. _Avoid_: possession, charm.

**Resonance Conflict**:
The authored condition a failed focus check (`check_resonance_focus`) puts on a character for the template's duration (authored as the scene), designated by `DriftConfig.conflict_condition`; its own check modifier is the penalty. Her category is `self_shakeable`, never `alters_behavior`. She shakes it off with `breakfree`; others stir it up through authored social actions.

**Aura share**:
One affinity's percentage of a character's aura: a `CharacterAuraShare` row keyed on the aura and the `Affinity` row. Code reads shares by Affinity row, never by a name or a per-affinity column.

**Glimpse**:
The narrative of a character's first magical awakening — prose living on `CharacterAura.glimpse_story`. Authored at character creation via a guided, tag-driven flow (#2427) and revisable afterward through the "finish your Glimpse later" editor on the own-character sheet.

**Glimpse Tag**:
An authored catalog choice (`GlimpseTag`) on one of four narrative axes (`GlimpseTagAxis`: Tone, Consequence, Witness & Secrecy, Sensory & Discovery) that a player picks while composing their Glimpse. Content model, lore-repo authored, no factory-seeded catalog. A tag's distinctions are `character_creation.DistinctionOffer` rows opened by it (`chapter=glimpse`, `glimpse_tag=<this tag>`), read behind `GlimpseTag.offers` (a `PrunedCachedProperty`-backed `Prefetch(to_attr=...)` target, ADR-0298; migrated off the old `CachedRowsHandler`/ADR-0278 wrapper, #3816 Task 9), the same offer mechanism every other CG chapter uses, replacing the retired `GlimpseTagDistinctionSuggestion` pairing table (#3675).
_Avoid_: conflating with `Ritual.glimpse_eligible` — an unrelated ritual-gating flag (whether a `Ritual` may be performed pre-formal-training), not a tag from this catalog.

**Glimpse State**:
`CharacterAura.glimpse_state` — the NOT_STARTED/TAGS_ONLY/COMPLETE deferral cache tracking whether a character's Glimpse has any chosen tags and/or written prose. Maintained exclusively by `world.magic.services.glimpse`, mirroring the `CharacterDistinction.secret`/`.from_glimpse` FK-presence-is-state precedent — never written directly. (#2427.)

**Anima**:
A character's pool of magical energy (current / maximum). It governs the *safety* of casting, not access — magic can always be attempted, and a shortfall is paid from life force rather than blocking the cast.
_Avoid_: mana, magic points.

**Anima Check**:
The stat + skill pair every one of a character's casts rolls, chosen explicitly during the CG Gift stage (closing the Tradition → Gift → Technique funnel alongside a ritual name) instead of the old silent Willpower + highest-skill default. Embodied as the personal `RitualCheckConfig` on the character's anima ritual (a `Ritual` row), provisioned by `provision_player_anima_ritual`. The skill pick never offers a MAGIC-category skill, because a cast also adds the technique skill and the staff-mapped skills (see **Technique skill**) and would count it twice (#4450). Deliberately **not** called "Signature" — ADR-0072 already owns that term for the Motif-flourish mechanic. (#2426, ADR-0136.)

**Gift**:
The kind of magic a character works: a thematic collection of Techniques (e.g. Pyromancy, Shadow Majesty), associated with a set of Resonances. A character acquires a Gift to gain access to its Techniques. The Gift says what the magic is; it does not say how it is wielded (see **Technique** for the other half of that pairing).

**Major Gift**:
The Gift chosen at character creation — a character's primary magical calling (one per character). Same `Gift` model as a Minor Gift, distinguished by a `kind` column. (ADR-0050.)
_Avoid_: main gift.

**Minor Gift**:
A smaller, shared, more-easily-acquired Gift (e.g. Sight → Soulsight/Magesight; Travel → teleportation). Minor Gifts are minor because they are Path-agnostic: each is either innate (a species gift nobody chose) or learned in a form every caster uses the same way, independent of whichever Path they walk. Because the character didn't choose it the way they chose their Path, a Minor Gift may set its own `Gift.style` (nullable FK to `TechniqueStyle`), overriding the caster's Path-chosen casting style for that gift's techniques (ADR-0199): the one exception to Technique's Path-sets-the-style rule below. **Species abilities (vampire/lycan/khati) are delivered as species-granted Minor Gifts.** (ADR-0050.) A species gets **one** Minor Gift, with its techniques under it; shared material between sibling species lives in an umbrella Gift the kinds' gifts hang beneath (see **Gift lineage**). (#2891.)
_Avoid_: lesser gift, sub-gift.

**Gift lineage**:
A Gift followed by every ancestor Gift, nearest first, walked through `Gift.parent` (self-FK, PROTECT). **Holding a Gift reaches the Techniques of that Gift and of every ancestor, and the character's Gift-thread on the held Gift is the thread for all of them** — one `CharacterGift`, one Thread, one technique cap. Shared species material (the Khati senses, the Infernal fire-resistance) lives once in an umbrella Gift; each kind's Gift hangs beneath it. `Gift.lineage` / `Gift.lineage_ids` / `Gift.inherited_techniques` are the model surface (`Gift.cached_techniques` still means the Gift's OWN techniques); `resolve_owned_gift` and `gift_threads_for` are the service seams. Distinct from `SpeciesGiftGrant.inheritable`, which walks the **species** chain rather than the Gift chain — both axes exist and both are needed. (#2891, ADR-0192.)
_Avoid_: gift tree, gift hierarchy, parent gift chain, gift inheritance.

**Tradition**:
A school of magical practice. Every character has exactly one, the self-taught `Unbound` tradition is a real Tradition row, not a NULL special-case. A Tradition does not limit which Major Gifts are pickable at CG: any Tradition may teach any Major Gift (#4659). Its `TraditionGiftGrant` rows mark the Gifts its teachers favor (tradition × gift, plus a `special_techniques` M2M of the techniques the tradition keeps for its own members: a technique no Tradition grant lists is open to every Tradition, one listed is open only to the listing Traditions, and either way it is offered only on the Paths whose Path Gift Grant lists it, #4555, ADR-4555-A); there is no selection gate, every tradition a Beginning's slate offers is selectable outright, but `BeginningTradition.state` (`TraditionState`: SELF_TAUGHT/TEACHERS_GONE/LIVING_MASTERS, #3675, was `required_distinction` pre-#3675) decides which drawback the pick carries for free via its `TraditionStateLine`. A Tradition also *teaches well* to some students (**teaching fit**, below): a Gift it favors (its `TraditionGiftGrant` rows) and the affinities in `Tradition.favored_affinities` (M2M `Affinity`, blank means none). Organizations may serve as a Tradition's teaching structure, many orgs per tradition (chapters, academies), via the nullable `Organization.tradition` FK (specific to general, ADR-0010; `Tradition` itself stays dependency-free). (#2426, ADR-0136; #3675.)
Membership in play is `CharacterTradition`, history-preserving via `left_at` (nullable — one active row per character, enforced by a partial-unique constraint mirroring `societies.OrganizationMembership.left_at`). `join_tradition(sheet, tradition, *, via_membership=None)` ends the active row and creates a new one (wired from accepting an `OrganizationMembershipOffer` on a tradition's teaching org, #2441 ruling 1); `leave_tradition(sheet)` stamps `left_at` with no replacement, no live caller yet. Learned techniques are never revoked on a switch ("learned is learned" — only future signature-list *access* changes). See "Unbound (drawback)" below for what auto-attaches/sheds on switch.

**Tradition Training**:
A rankable distinction that scales a character's CG starting-technique-pick budget: baseline (Unbound, no distinction) is 1 pick, and each rank of Tradition Training adds +1 (rank 1 → 2 picks, rank 2 → 3). Data-modeled as a `ModifierTarget` ("Starting Technique Picks") + `DistinctionEffect`, read at draft time via the existing `CharacterDraft._get_distinction_bonus`, no new mechanism. A tradition whose slate state opens stances offers it as a `DistinctionOffer` (chapter `tradition_step`) tied to its `SchoolingLine` stances (#3675), not a `BeginningTradition.required_distinction` FK. The state decides how many stances it opens (`SCHOOLING_MAX_RANK_BY_STATE`, #4457): LIVING_MASTERS ranks 0 to 2, TEACHERS_GONE ranks 0 and 1 (its teachers were lost before anyone could finish), SELF_TAUGHT none. The stance a player picks carries **magical training points**, so Tradition Training is the one creation source of Magic skills. (#2426, ADR-0136; #3675; #4457, ADR-4457-A; #4659, ADR-4659-B.)

**Magical training points** (#4659, ADR-4659-B; replaced the #4457 Magic skill floor):
The pool a character creation draft spends on Magic-category skills (`magic_category_skills()`). The base is the sum of the draft's distinction effects on the `magic_training_points` modifier target (the schooling stance's granted distinction, plus any other distinction that carries the effect). Teaching fit adds a flat bonus to it, only when the base is above 0. A Magic skill value costs its own value in points, the ordinary 10 per step. The player must spend all of it, up to what the Magic skills can hold (`required_spend`); the allocation lives in `draft_data["magic_skills"]` and finalize writes it. `CharacterDraft.magic_training_pool` computes it live on each call. A self-taught character, or one who took rank 0, has no base and starts with no Magic skills; they catch up in play: by use, weekly training, or a **Skill course** at the Academy. Joining a Tradition in play grants nothing. The set is every Magic-category skill, staff-controlled by category; a per-Tradition list is deferred.
_Avoid_: Magic skill floor (the retired fixed level), Magic skill grant, tradition skill bonus, starting Magic points (CG skill points never buy a Magic skill).

**Teaching fit** (#4659, ADR-4659-B):
How well a Tradition teaches a particular student, resolved by `teaching_fit(tradition, gift, affinity)` in `world/magic/services/teaching_fit.py`. It has two independent parts: the **Gift fit** (the Tradition has a `TraditionGiftGrant` for the student's Major Gift) and the **affinity fit** (the student's `Affinity` row is one of the Tradition's `favored_affinities`, compared by foreign key). Each part that fits adds its flat bonus to the magical training pool and eases an Academy course taught under that Tradition; the amounts are the `TraditionTeachingConfig` singleton. Fit is a bonus, never a gate: any Tradition may teach any Major Gift. Character creation uses the picked Gift and the picked resonance's affinity; the Academy uses the character's Major Gift and the affinity of the resonance on their active GIFT thread for it. Fit by the character's aura is deferred to #4672.
_Avoid_: Tradition affinity restriction, Gift whitelist, fit gate.

**Unbound (drawback)**:
The `Distinction` (slug `unbound`, negative `cost_per_rank`) carried for free by picking the Unbound Tradition. The SELF_TAUGHT `TraditionStateLine.carries` FK names it (#3675); `reconcile_offer_picks` applies it to the draft the moment a SELF_TAUGHT tradition is selected, through the same generic mechanism every carried drawback uses (no Unbound-specific code path; Orphaned Tradition's TEACHERS_GONE drawback carries the identical way). Its `DistinctionEffect` carries a +50% surcharge on the `magic_learning_ap_cost` `ModifierTarget`: self-taught mages pay more Action Points to learn techniques (`charge_and_learn`'s AP scale, both front doors), TIME, not power; resonance is untouched. Shed automatically on joining a living Tradition (`join_tradition`), re-applied on leaving one (`leave_tradition` via `world.character_creation.offers.self_taught_drawback()`), the underlying `CharacterModifier` cascade-deletes with the distinction, so the surcharge tracks membership with no separate cleanup. (#2441, #2442, #3675.)
_Avoid_: conflating this with the `Unbound` Tradition row itself (see "Tradition" above) — the Tradition is the school-of-practice entity; this is the drawback distinction a traditionless character carries while in it.

**Gift-thread**:
The one Thread a character holds on a Gift: its level sets the Gift's strength (more and stronger techniques) and its **Leading resonance** sets the Gift's affinity, with every resonance it holds on its rows (#5123). Any resonance she holds can feed it: the Gift's own `resonances` list limits nothing, it is only the default a grant naming no resonance reaches for. The costliest thread kind, because it gates magical power. (ADR-0051, ADR-0052.)

**Thread level** (#4585, ADR-5091):
The stored `Thread.level`, which is also the number a player sees (a thread at 30 reads 30),
like stats and skills. Every authored thread threshold (crossings 30/60/110/160/210, variant
and sub-role unlocks, signature minimums, pull-effect minimums) is a stored level compared
directly; `is_thread_crossing_level` names the crossings. A thread is capped at ten times its
owner's character level (the **level cap**, `compute_level_cap`). Formulas tuned "per 10
thread levels" count the **thread rung** (`thread_rung(level)`, `level // 10`), an internal
step that is never shown. _Avoid_: "shown thread level" (removed by #5091); dividing a thread
level by 10 for display; "path cap" (threads are no longer capped by Path stage).

**Signature**:
A Thread woven into a single Technique, deepening just that technique above its Gift baseline. The character applies their Motif to the signed technique via a `SignatureMotifBonus` — an ADDITIVE flourish (intensity delta, conditions, cosmetic prose) that fires alongside the technique at cast time. The bonus is NOT a `TechniqueVariant` and does NOT change the technique's identity. No longer a level-3+ mechanic: `SignatureMotifBonus.min_crossing_level` (a thread level, default 30, authorable lower or higher) is the only gate on when a given bonus unlocks, and creation can weave a starting thread up to `CREATION_PERSONALIZATION_MAX_LEVEL` so an early flourish is reachable at CG (#4099, ADR-4099). (ADR-0072, supersedes ADR-0056.)
_Avoid_: technique thread (use "signature"); discordant signature (the resonance-divergence model was closed by ADR-0072).

**Signature Motif Bonus**:
The staff-authored catalog row (`SignatureMotifBonus`) that a player attaches to a TECHNIQUE-kind Thread to sign that technique. Gated on the character's Motif (facet and/or resonance). Carries `flat_intensity_delta`, `narrative_snippet`, and payload child rows (capability grants, damage profiles, applied conditions) sharing the `Abstract*` bases from `models/techniques.py`. (ADR-0072, #1582.)
_Avoid_: signature variant, signature specialization (it is additive, not a variant form).

**Hold**:
`CharacterTechnique`, a character's hold of a Technique. Distinct from the shared catalog `Technique` it points at: a character's own name, description, price and early form all live on the hold, never on the catalog row, so two characters holding the same Technique can personalize it differently. (#4099, ADR-4099.)
_Avoid_: grant, possession (use "hold").

**Price**:
A `Restriction` of `kind=PRICE` that a caster chooses for their own hold of a Technique, offered in creation when staff set its `creation_point_cost`. The stronger the power bonus, the more it costs to take. A price costs something real: it may consume carried items on every cast that pays it (`PriceComponentRequirement`) and may inflict an authored condition on the caster (`inflicted_condition`). A cast **pays** its price when the caster carries every component (always, for a price with none); only a paid cast gets the `power_bonus` power-ledger term and the `cast_narration` clause, and only a paid cast spends the components and takes the condition. An unpaid cast still happens, just without the price. `price_paid_for_cast` is the one place that decides. Distinct from a DESIGN-kind `Restriction`, which refunds a technique's design budget in the builder and is never attached to a hold. (#4099, ADR-4099.)
_Avoid_: cost, drawback, toll.

**Early form**:
A `TechniqueVariant` bought on a character's hold during creation, before the gift thread has reached the level that would naturally resolve it. Applies only for its buyer, at the hold's own resonance, and never for a role-granted hold. A naturally-reached higher-level form still beats an early pick once the thread catches up. (#4099, ADR-4099.)
_Avoid_: unlocked form, bonus form.

**Personalized name**:
A character's own `custom_name`/`custom_description` on their hold of a Technique. Free, unreviewed, and display only: every lookup, cast resolution and prerequisite check keeps reading the catalog `Technique.name`, never the personalized one. (#4099, ADR-4099.)
_Avoid_: using a personalized name as a lookup key anywhere in code.

**Specialization engine**:
The one shared `(entity × resonance) → customized capability` resolution (a generalization of covenant sub-role resolution): the same Gift down different Paths, or with a different resonance, yields different specialized techniques, derived on read. (ADR-0055.)

**Technique**:
A specific magical ability that lives within a Gift, carrying base intensity, control, and anima cost plus a style and effect type. A Technique is the intersection of a Gift and a Path: the Gift is the kind of magic, the Path is how, and to what ends, the magic is wielded, and a Technique is how someone of a given Path uses a Gift. The same Pyromancy Gift plays differently in a warrior-line Path's hands than in a spy-line Path's: `PathGiftGrant` (the (Path x Gift) availability pool, see below) is what makes that concrete, handing each Path its own curated technique set from the same authored Gift; its `starter_techniques` list is the techniques for that Path and Gift, so a technique is offered only on the Paths that list it (#4555, ADR-4555-A); its cast skill follows the casting style instead (#5002). The caster's Path sets a Path-chosen technique's casting style (`Path.style`, `TechniqueStyle`, #2700, ADR-0167) unless the Gift itself overrides it (a Minor Gift's `Gift.style`, ADR-0199; see **Minor Gift**, since a Minor Gift is Path-agnostic). Never frame magic as "Path or Gift": a character needs both, and a Technique is where they meet. It is the primary unit of magical action. At character creation, players pick 1 + `Tradition Training` bonus Techniques from a staff-authored catalog (their Path × Gift's list, less the techniques other Traditions keep for their own members) rather than authoring one. Mechanical personalization (a Price, an Early form, a flourish, a custom name and description) is now offered at CG itself, on the character's own hold, not only once a thread is deep enough (#4099, ADR-4099, supersedes in part ADR-0136). (#2426, ADR-0136.) The rest of a Gift's pool is filled in **play**, not at CG: `charge_and_learn` (`services/gift_acquisition.py`) is the one shared charge+acquire seam behind both player-to-player `TechniqueTeachingOffer` accepts and the Academy's `TRAIN` offers (`world.npc_services`): the latter additionally spend one Golden Hare per technique (see `currency` glossary), gated on the learner's Academy entrance obligation being settled. Reaching character level 2 requires knowing ≥3 techniques of the character's major Gift (`progression.MajorGiftTechniqueRequirement`, #2440 ruling 4). (#2428, #2440, ADR-0137.)
_Avoid_: power, spell, ability; **cantrip** (retired #2426 — see ADR-0136; CG used to mint a personal Technique from a staff-curated `Cantrip` template, now it links to catalog `Technique` rows directly, no per-character row created).

**Effect Summary**:
What a Technique actually does, derived on read from its payload families (capability grants, applied conditions, damage profiles, removed conditions, treatments and the morale effect) plus the existing `is_technique_hostile` / `derive_target_relationship` derivations - never a stored field, since `Technique.target_type`'s help text already rules a stored relationship out. Built by `summarize_technique_effects`, cached on the row as `Technique.cached_effect_summary`, serialized once by `TechniqueEffectSummarySerializer`, and embedded as `effect_summary` by every technique surface (CG, the magic API, the in-scene cast list, the character sheet) so the four cannot drift apart again. Carries a **plain-words line** (`summary`) authored server-side - the same sentence in the web client and over telnet - alongside the structured lists. (#2898.)
_Avoid_: re-deriving or re-wording the sentence client-side; adding an `is_self_buff`-style stored relationship field.

**Technique morale effect** (#4619, ADR-4619-A):
The payload row (`TechniqueMoraleEffect`, one at most per technique, draft copy `TechniqueDraftMoraleEffect`) that makes a cast remove morale from the enemies it lands on: a base, a share of the cast's effective power, a step per success level above a minimum, and the minimum itself. It has no prose. It makes the technique hostile and enemy-aimed, and the effect sentence says "Shakes morale." Combat applies it after damage; see the combat glossary's **Morale**. _Avoid_: fear effect, demoralize (that is the social-combat maneuver).

**Underspecified Technique**:
A Technique with no applied condition, removal, treatment, damage profile or morale row, so nothing about its effect (including its targeting relationship) is derivable from authored data (86 of 272 when #2898 shipped). Surfaced to players as "effects not yet catalogued" rather than a blank, and to staff via `TechniqueAdmin`'s authoring-gap filter. Distinct from an **ambiguous** technique, whose payload rows carry more than one `target_kind` so the single derived relationship is a guess: the self-teleport-that-Flanks-an-enemy shape found in #2764. Both are reported, never guessed around. (#2898.)

**Technique Function**:
The fine-grained "what job does this technique do" vocabulary — a code-defined `TechniqueFunction` `TextChoices` (damage buff, barrier, cleanse, weaken, fear, ...) distinct from the coarser SWORD/SHIELD/CROWN `archetype_alignment`. One shared vocabulary consumed by two independent systems: `covenants`' per-vow technique specialty (#2443) and situational perks (#2536). `TechniqueFunctionTag` (NK `(technique, function)`) is the content-authored join recording which labels a given Technique carries — a lore-repo authoring decision, while the vocabulary itself stays a code enum so both consumers validate against stable values. (#2443, ADR-0149 amendment.)
_Avoid_: conflating with `archetype_alignment`/the SWORD-SHIELD-CROWN blend axis (Layer 1) — Technique Function is the finer-grained Layer 2/4 vocabulary, not a replacement for it.

**Consequence-Pool Catalog**:
The curated set of `ConsequencePool` rows selectable when authoring a technique — structurally, the single-depth children of the base "Magic: Technique Cast" pool (`ConsequencePool.parent`). Each catalog entry has a matching `ActionTemplate` sharing the base template's `check_type`/`pipeline`/`target_type`; only `consequence_pool` differs. (#1320.) CG no longer has an "Outcome Flavor" pick from this catalog — dropped in #2426 (ADR-0136) because it only worked by baking a pool into a per-character technique row, which shared catalog techniques make impossible without new cast-path machinery.

**Intensity**:
The magnitude a caster *channels* — it drives cost and risk (anima cost, control mishap, Soulfray, Audere gating, resonance attribution). It is a base/static value on the Technique and is never reduced by a ward.

**Power**:
The effective magnitude the working carries into the world — it drives landed effect (damage budgets, condition severity, capability grants, clash progress). Power is always derived and recomputed each cast, never stored; it is seeded by intensity and then diverges.

**Control**:
A Technique's base safety/precision stat. High control reduces anima cost and eliminates mishap risk; it is the efficiency lever opposite intensity.

**Control Mishap**:
An additional consequence drawn when runtime intensity exceeds control (the `control_deficit`), routed through the consequence pool whose deficit band matches via `MishapPoolTier`. It never replaces the intended effect and never carries character-loss consequences.
_Avoid_: fumble, miscast.

**Soulfray**:
The magical strain a character accrues by casting while anima is depleted below the configured threshold ratio; severity scales with depletion and is tested against a resilience check. Tuned by the `SoulfrayConfig` singleton, whose `condition` field names the condition template that is Soulfray (the game never finds it by name).

**Overburn**:
The condition where a cast's effective anima cost exceeds the available pool and the deficit is drawn from the caster's life force. Non-lethal encounters clamp cost to available anima instead.

**Burn**:
Resonance a character spends from the resonance of a thread she is pulling, on top of the pull's cost, to push a cast harder (#4736). Rolled on the strain check, the outcome tier's `StrainBurnReach` sets the share she reaches, and only that share is debited. Reached points become strain units at the resonance's affinity `burn_value`, joining the anima strain before the one diminishing curve. It exists only with a pull and strains only the action it was declared with.
_Avoid_: overburn (that is the anima deficit), sacrifice.

**Burn ceiling**:
The most resonance a cast may burn: its runtime intensity times `StrainConfig.burn_per_intensity`, floored, and never more than the balance left after the pull's cost. The pull preview shows it.

**Hasty fall**:
A burn by a caster whose acting aura is dominantly Abyssal, of resonance from another affinity. The points convert at the Fall pair rate and are valued as Abyssal, and the corruption they cause is multiplied by `CorruptionConfig.hasty_fall_multiplier`.

**Engagement share**:
The percentage (`StrainConfig.engagement_share_percent`) of a cast's strain bonus that is also added to the caster's engagement intensity modifier, so strained intensity feeds back into her engagement.

**Penetration**:
The contest run when a Technique's Power meets a target's ward: a check against the ward's strength whose success level selects a factor from the authored ladder, applied as the `PENETRATION` stage of power derivation. Unwarded casts record no penetration entry.

**Ward**:
A target's defensive barrier (a positive `barrier_strength`) that Power must penetrate to land its effect. A ward reduces Power only; it must never reduce intensity.
_Avoid_: shield, barrier (as the canonical term).

**Backfire**:
The adverse consequence resolved when a cast is worked in an environment whose Affinity is OPPOSED to the caster's, drawing from the pairing's authored consequence pool. The opposed half of the resonance-environment interaction.

**Resonance Environment**:
The directed pairing between a caster's Affinity and the place's Affinity that conditions a cast — an ALIGNED pairing amplifies (and may grant a boon), an OPPOSED pairing backfires or defiles. Modeled as nine `AffinityInteraction` rows plus a tuning singleton.

**PowerLedger**:
The transient, never-persisted record of how a cast's Power was derived — an ordered list of entries each carrying a stage, source label, operation, amount, and running total. It is recomputed on every cast and surfaced for transparency.

**PowerStage**:
The enum naming each phase of power derivation in the ledger (base, flat modifier, multiplier, term, environment, reactive, combat pull, penetration, clamp). Each ledger entry is tagged with one stage.

**Thread**:
A per-character attachment owned by a CharacterSheet, anchored to exactly one anchor (Trait / Technique / Facet / relationship side / relationship capstone / covenant role / Gift / Mantle / Sanctum), one thread per anchor, holding one or more Resonances on its `ThreadResonance` rows, each with the cumulative amount of that resonance ever imbued (#5123, ADR-5123-A). It accrues `developed_points` into a `level` and is the unit of long-term magical investment. `developed_points` is this app's instance of the **Development** progression currency (see "The three progression currencies" in the root `AGENT_GLOSSARY_MAP.md`): it stands for the resonance a character has invested, not an XP purchase. Crossing an internal level that is a multiple of 10 additionally requires an XP spend at an authored `ThreadXPLockedLevel` boundary, so a thread's level reflects both currencies at once: Development gets it to the boundary, XP is what lets it cross.

**Imbue**:
Spending Resonance currency of one held resonance to advance an existing Thread's developed points and level; the thread's row for that resonance grows by the amount (`spend_resonance_for_imbuing(sheet, thread, resonance, amount)`). Player-facing it is the Rite of Imbuing, a CEREMONY-kind Ritual completed by the `imbue` finisher.

**Weave**:
Creating a new Thread on an anchor the character is unlocked to weave on; an anchor that already has a thread is imbued instead. Player-facing it is the Rite of Weaving, a CEREMONY-kind Ritual completed by the `weave` finisher.

**Leading resonance** (#5123, ADR-5123-A):
The resonance of a Thread's first `ThreadResonance` row: the largest cumulative amount, a tie to the row created first (no minimum share). `Thread.resonance` is a denormalized copy of it, written only by `refresh_leading_resonance`. It gives the thread's always-on (tier 0) perks and its identity for readers that want one resonance (a Gift's affinity, a technique's variant). _Avoid_: main resonance (the character's own earliest-gift or highest-lifetime fallbacks use that phrase), primary resonance.

**Paying resonance** (#5123, ADR-5123-A):
The resonance a player chooses, per pulled thread and each time, to pay that thread's cost in a pull. Stored on `CombatPullThread.paying_resonance` / `ScenePullThread.paying_resonance` (a bare thread pays with its leading resonance). Any resonance the character holds may pay; its perks are the perks the pull gives. The leading resonance reads the thread's level, another resonance with a row reads `DriftConfig.second_resonance_level_step` lower (never beating the leader), and a held resonance with no row, or an empty one, pays and gives the ordinary pull benefit and no perks. _Avoid_: pulled resonance, the pull's resonance (a pull has none of its own; ADR-5066-B), burned resonance (the one a burn comes from, named separately and one of the payers).

**Ritual**:
An authored magical procedure dispatched in one of four ways: SERVICE (invokes a service-function path), FLOW (invokes a flow definition), CEREMONY (creates a pending effect a finisher command later consumes), or SCENE_ACTION (fires a check via a `RitualCheckConfig` sidecar). Performance converges on the single `perform_ritual` Action. "Spell" is an acceptable in-prose synonym for a ritual in player-facing narrative text, but `Ritual` is the only mechanical term — never mint a `Spell` model or code identifier (#3001, ADR-0205; and "spell" stays on Technique's avoid list, since the sheet's technique section is historically the "spellbook").

**Anima Pool (ritual)**:
The per-performance pot of anima a `Ritual.anima_requirement > 0` rite consumes, filled by `RitualAnimaContribution` rows: **channel** (own anima), **prick** (one drop — 1 anima, trivial damage), **gash** ((1d6+1) × level, a real wound), **sacrifice** (a victim drained wholesale). The price is the only framework gate — no Gifted-check anywhere in ritual dispatch. Underfilled pools roll a deficit-bumped check and can fizzle (consuming the pool); ≥2× the requirement unlocks the spectacular tier. (#3001, ADR-0205.)
_Avoid_: mana, spell points; conflating with the anima-ritual (the personal recovery rite).

**Death Harvest**:
The ×`AnimaConfig.death_harvest_multiplier` (20) yield of a killing anima drain — feeding gorge or ritual sacrifice — measured against the victim's full maximum, not what remained. The metaphysical engine of ritual murder, and why anima-feeders are tempted to finish victims. Fires the "Murder by Anima Drain" compromise taint (+5 Praedari). (#3001.)

**Hedge-Accessible**:
`Ritual.hedge_accessible` — the single visibility-and-eligibility predicate (`ritual_visible_to`) for rites open to characters with no magical profile (no `CharacterAura`). Non-hedge rites are hidden from and refused to quiescent performers at browse and solo perform alike; session rituals gate inside their own service functions instead. (#3001.)

**Sanctum**:
A leveled room that serves as a Thread anchor via `target_sanctum_details`, capped at the sanctum feature's level × 10. A Sanctum-anchored Thread is pull-applicable (an in-sanctum boost) while the character is in the Sanctum's room.

**Style Binding**:
A player-authored link (`MotifResonanceStyle`) between a staff-curated `Style` word
(`world.items.Style`) and one of the character's own claimed motif resonances —
individualized, so two characters binding the same `Style` name attach it to
different resonances. Capped at 3 bindings per resonance. Authored via
`bind_motif_style`/`unbind_motif_style` (`services/motif_style.py`), telnet
`CmdMotif`, or the web `MotifStyleViewSet`; consumed by the coherence walker and the
peer style-presentation endorsement. (#2030.)
_Avoid_: facet binding (a Facet is a different axis — a flat, shared imagery
vocabulary since #3776/ADR-0289 — bound through `MotifResonanceAssociation`, not
through `Style`).

**Facet alias**:
Another spelling that routes to a facet (`FacetAlias`, #4197): the names a merge retired
("Scythes" after Scythes was merged into Scythe) and any spelling staff add by hand. Read by
the pickers' search and by `POST /api/magic/facets/`, never shown to a player. The merge
itself is `merge_facets` (`services/facets.py`); the spelling rule both share is `facet_key`.
_Avoid_: synonym (an alias is a spelling of the same facet, not a related one); tag.

**Facet effect bonus**:
A facet's always-on bonus to one maneuver effect (`FacetEffectBonus`, #4815): "Wolf: +2 Charge:
damage". The facet names the effect, whatever its thread's resonance, and it counts while the
character wears an item carrying the facet and has a facet thread on it. Its `amount_tenths` is
tenths of the Facet effect bonus lane's baseline at the facet thread's rung (#5093).
_Avoid_: facet passive (that is the resonance-keyed tier-0 `ThreadPullEffect` bonus, a different
row); facet buff.

**Mantle**:
A specific, storied, attunable ItemInstance in the world (a particular sword, amulet, banner) with authored progression levels. A character attunes by weaving a MANTLE-kind Thread anchored on the Mantle, gated on having cleared at least its first level; the Thread's level cannot exceed the character's max-cleared mantle level.

**Touchstone**:
A resonance-tied `ItemInstance` a character has personally attuned via `attune_touchstone` (requires holding it, an unset `attuned_to_character_sheet`, and having claimed the item's `tied_resonance`). Attunement does not consume the item. Touchstone-mode component/item requirements (`RitualComponentRequirement`, `ItemRequirement`) match any attuned item whose `ResonanceTier` meets a floor, rather than one fixed catalog item — see ADR-0087.

**Portal Anchor Kind** (#2222, ADR-0121):
A staff-authored catalog row (`PortalAnchorKind`) naming a medium of portal travel (e.g.
"Mirror") plus its narrative arrival/departure verb phrases. A `Technique.travel_anchor_kind`
FK marks a technique as a travel-mode technique through that medium — many gifts can each
unlock travel through the same anchor kind, or their own distinct one.
_Avoid_: anchor type, portal kind.

**Portal Anchor** (#2222, ADR-0121):
A concrete, installed instance (`PortalAnchor`) of a Portal Anchor Kind in one specific room —
"a tall silvered mirror" is a Mirror-kind anchor. Stackable: a room may hold more than one
active anchor of different kinds at once (one active anchor per kind per room, enforced by a
partial unique constraint). `is_network_open` gates whether strangers may travel to it; a
locked anchor is still reachable by anyone with owner/tenant standing at its room. Dissolved
(never hard-deleted) via `dissolved_at`, mirroring Room Feature dissolution. Explicitly NOT a
`RoomFeatureInstance` (one-feature-per-room cardinality is wrong for a stackable network node)
or a `RoomDecoration` (wrong domain — amenity/affinity dressing, not technique-gated travel
connectivity) — see ADR-0121.
_Avoid_: portal, waypoint, travel node.

**Travel-Mode Technique** (#2222):
A `Technique` whose `travel_anchor_kind` FK is set — knowing it lets a character portal-travel
through anchors of that kind. A character "knows" an anchor kind for travel purposes by
knowing any one `CharacterTechnique` bound to it; the technique's own `anima_cost` is the
per-use cost (0 for the seeded "Mirrorwalk" starter). Distinct from a technique's ordinary
combat/social effect — a travel-mode technique's payload IS the instant relocation, resolved
by `world.magic.services.portal_travel.perform_portal_travel`, not a damage/condition/
capability-grant row.
_Avoid_: portal technique, teleport spell.

**Cast Concealment** (#2710, ADR-0170):
`TechniqueStyle.cast_concealment` — the style's difficulty floor for being noticed while
casting. A magnitude, not a flag: 0 (default, overt) means the cast is posed to the whole
room exactly as always and no detection check runs at all; above 0 it's the difficulty an
observer's detection roll must beat, on top of the caster's own level opposition. Style is
a property of the caster's Path (ADR-0164), so concealment is too — the same catalog
`Technique` is loud cast by one Path and concealed cast by another. The same style also
carries the cast's skill (`TechniqueStyle.skill`, #5002; see **Technique skill**).
_Avoid_: spell visibility, stealth casting.

**Cast Audience** (#2710, ADR-0170; reworked #2734, ADR-0187):
Who perceived a concealed cast, and how much of it they could **attribute** — resolved
per co-located observer at cast time by `resolve_cast_audience`, never a single
room-wide flag. Concealment hides attribution, not the event: three tiers, and the
caster is always `full`. `full` (`success_level >= CAST_DETECTION_ATTRIBUTION_LEVEL`)
sees who cast what; `vague` (a lesser success) sees the effect and knows it was a
working, but not by whom; `effect_only` (a failure) sees the effect with no sense that
magic was involved. Materialised as `InteractionReceiver` rows under the
`InteractionVisibility.PERCEIVED_ONLY` tier so a scene log replays what each viewer
perceived at the time, not what they could detect if re-read today.
_Avoid_: spell visibility, stealth casting.

**Perceptible Effect** (#2734, ADR-0187):
`Technique.has_perceptible_effect` — whether working this technique produces something
bystanders can see happen, independent of whether they can tell who did it. `True` by
default and for the overwhelming majority: almost any applied condition produces some
visible effect. `False` marks the rare working that leaves nothing to perceive at all (a
silent binding, a curse laid at a distance), and is the **only** case where a concealed
cast still hides outright from an observer who fails detection instead of being narrated
without attribution. Orthogonal to `cast_concealment`, which is a property of the
*caster's style*, not of the technique.
_Avoid_: visible spell, flashy technique, is_magical.

**Mage Scar**:
The player-facing name for a magical alteration imprinted on a character by magical exposure — a queued, tiered cosmetic-to-profound change carrying social, weakness, and resonance effects. Backend class and table names retain the `MagicalAlteration` naming.
_Avoid_: Magical Scar, Magical Alteration (as the player-facing name).

**Cosmetic Mage Scar**:
A Mage Scar with no drawbacks that does not hold back advancement (`PendingAlteration.is_cosmetic`, #4501). A trial's Success or Critical Success route may queue one as a reward (`ConsequenceEffect.scar_is_cosmetic`). The player still writes it and others see it as they see any scar, but its resolution must leave every magnitude at 0 (a library pick must be a drawback-free entry), `has_pending_alterations` ignores it, and it merges only with another cosmetic scar. It is never a cost. Not the same as tier 1, **Cosmetic Touch**, the smallest tier of an ordinary Mage Scar, which keeps its label and still gates advancement.
_Avoid_: reward scar, free scar, cosmetic alteration (as the player-facing name).

**Soul Tether**:
A bond mechanic between two characters (a player's or an NPC a GM runs) whose tuning lives in the `SoulTetherConfig` singleton, providing a rescue-and-resolution mechanism with a dramatic advancement/modifier surface (**Sineating**, the **Mire**, rescue rituals, stage-advance bonuses). The Sinner and Sineater are its two roles; forming it weaves a thread for each, each on a fresh ritual capstone of that character's own side of the bond. It never joins two characters one account plays.

**Sineater**:
One of the two roles in a Soul Tether bond: the participant who performs **Sineating** and carries what they take on as the **Mire**. The complementary role is the Sinner. A Sineater whose aura is predominantly Abyssal has fallen (**Fall of a Sineater**).

**Sinner**:
The other role in a Soul Tether bond: the character who accrues corruption from non-Celestial casting, whose Hollow absorbs some of it, and who asks the Sineater by pose to take on what they carry. A Sinner profits from every Sineating and gains when their Sineater **Succumbs**. _Avoid_: victim.

**Dramatic Moment**:
A staff-tagged scene moment of an authored category that simultaneously grants a character Resonance and fires a renown award. Tags are immutable provenance records, capped per character per scene.

**Entry Flourish**:
A self-grant of Resonance triggered on a successful Entrance social action, where the entrant declares one of their claimed Resonances to broadcast. Idempotent per scene; it is the actor-side complement to the peer-side scene-entry endorsement.

**Technique Entrance** (#2183):
An Entrance whose check IS a technique cast (`enter <technique>[=<target>]` / the web `EntranceTechniqueAttachment`), the cast's own success level substitutes for the entrance's social roll entirely, one check driving every downstream consequence (see ADR-0113). Distinct from **Entry Flourish** (the resonance self-grant this success level unlocks alongside), **Dramatic Moment** (the GM-tagged reward category a qualifying entrance may *suggest*, never auto-grant), and **Dramatic Surge** (`world/combat/AGENT_GLOSSARY.md`, a different system entirely: an intensity-modifier jump at a combat beat, not a recognition/reward mechanism). A qualifying success creates a PENDING `GMPrompt` of kind `dramatic_moment` (`world/gm/AGENT_GLOSSARY.md`, #4101; was `DramaticMomentSuggestion`), via `maybe_suggest_dramatic_moments`, resolved by `resolve_dramatic_moment_suggestion` (confirm mints a real `DramaticMomentTag`; dismiss closes it with no reward).
_Avoid_: technique-cast entrance (use "Technique Entrance"); auto-tag, auto-grant (recognition is never automatic, see ADR-0113); DramaticMomentSuggestion (renamed, see `world/gm/AGENT_GLOSSARY.md`'s "GM Prompt").

**Prepared Text** (`CharacterCrossingText`, `CharacterSurgeText`, #4101):
One character's own authored line for their next Audere surge or Audere Majora
Crossing, written by staff or that character's table GM, play-adjacent (never catalog
content, never exported). Resolved field by field: the character's own prepared text
first, then the Crossing's patron variant (surges have no patron layer), then the
tier's authored default. A Crossing's prepared text is consumed (linked to the
`AudereMajoraCrossing` it fired) on use; a surge's is reusable. Feeds the `room_text`/
`private_text` a `world/gm/AGENT_GLOSSARY.md` GM Prompt carries for that event.
_Avoid_: custom vision, override text, patron text (patron variant is a narrower,
pre-existing layer underneath this one).

**Anima ritual** (#5280):
A character's personal ritual, a scene with a partner that is never performed alone. It rolls a check, recovers anima and eases Soulfray on a success (Partial Success and above), and grows up to two resonances in her aura: a Primal one for how it feels to her and a Celestial or Abyssal one for how it reaches the partner, split by the two affinities' settled shares. Anyone who plays it is asked for a partner; an NPC partner needs a GM. _Avoid_: solo ritual, the anima refill.

**Endorsement (of a ritual)** (#5280):
A player partner's answer to an **Anima ritual** that reached for their resonance: Endorse grows the performer's outward resonance by the held part, Withhold grants nothing, and an unanswered question lapses when the scene finishes. After a failed roll an endorsement grants `AnimaConfig.failed_endorsement_percent` of the outward part of the Success tier's award. Not a `PoseEndorsement`. `AnimaRitualPerformance.endorsement` holds where it stands. _Avoid_: consent (that is the partner's agreeing to take part, before the roll), approval.

**Attunement** (#5280):
The paid way to change an **Anima ritual**'s two resonance picks after their free first setup, for the anima, resonance and action point costs staff set on `AnimaConfig`, and a check when staff set one. A failed roll keeps the costs and the old picks. Not the Touchstone attunement of an item. _Avoid_: re-pick, edit.

**Endorsement**:
A peer's recognition of another character's pose (`PoseEndorsement`) that settles at the weekly tick to grant Resonance from a shared pot. A legitimate, live Resonance-award mechanism alongside scene-entry and style-presentation endorsements.

**Renown**:
The reputation/legend award fired alongside certain magical events (Dramatic Moments, Audere Majora crossings) via `fire_renown_award`. A live award mechanism; when an event's configured risk is NONE, no deed is minted.

**Effect palette**:
The seeded set of nine castable combat effects (`ensure_effect_palette_content()` in
`world/magic/effect_palette_content.py`): Summon Spirit, Aegis Field (force-field), Mirror
Ward (reflect), Phase Step (blink), Phase Jump (teleport), Barricade (obstacle), Ghostform
(incorporeal), Earthmeld (sink), Force Grip (telekinesis). Each is a full Technique + Condition
+ Flow + Trigger bundle wired idempotently via `get_or_create`. Handlers and adapters live in
`world/magic/services/effect_handlers.py`.

**Intangibility**:
The status of being incorporeal (smoke, ghost, sunk into earth), conferred by a
`ConditionInstance` whose `ConditionCategory.grants_intangibility` is True. An intangible PC
holds no ground (`is_intangible(objectdb)` in `world/conditions/services.py`, read by
`held_ground.encounter_holds`) but stays targetable: protection is the condition's own
severity-scaled Physical resistance, so a hard enough hit still lands (#4742). Ghostform and
Earthmeld are the seeded intangibility conditions (#1584).
_Avoid_: untargetable (incorporeal is near-total mitigation, never immunity)

**Target-Aware Pull**:
A thread pull whose numeric payload can be modulated by the live target the pull's
action is directed at, via `apply_target_modulation` (#1831). Distinct from an
ephemeral/untargeted pull, which always resolves unmodulated.
_Avoid_: targeted pull (ambiguous with targeting a technique, not a pull).

**Pull Target Modulation**:
The per-`target_kind` extension seam (`apply_target_modulation`,
`world/magic/services/pull_modulation.py`) that `resolve_pull_effects` calls for every
numeric-payload pull effect row, dispatching on `thread.target_kind`. A no-op unless a
rule is registered for that kind. Two rules registered: COVENANT_ROLE (Court Regard
Modulation, below) and RELATIONSHIP_TRACK (Relationship Bond Pull Modulation, below).
(#1831, #1849.)

**Regard Polarity**:
`ThreadPullEffect.regard_polarity` (`RegardPolarity`: OFFENSIVE / PROTECTIVE / NEUTRAL) —
authored on a pull-effect row to say how Court-role (COVENANT_ROLE) pull modulation
responds to the Court leader's signed `NpcRegard` for the live target: OFFENSIVE is
empowered by negative regard (a disfavored target), PROTECTIVE by positive regard (a
favored target), NEUTRAL by either nonzero sign. Ignored for every other `target_kind`.
(#1831.)

**Court Regard Modulation**:
The only `Pull Target Modulation` rule wired today (`court_regard_modulation`,
`world/magic/services/pull_modulation_court.py`): empowers a COVENANT_ROLE thread pull
by the covenant leader's signed `NpcRegard` (#1717) for the live target, sign-directed
by the effect row's `Regard Polarity`. The combat-UI picker
(`compute_thread_applicability`) surfaces `InapplicabilityReason.COURT_LEADER_NO_STAKE`
when no candidate effect on the thread would ever be empowered against the given target.
(#1831.)

**Relationship Bond Pull Modulation** (#1849):
The `RELATIONSHIP_TRACK` sibling to Court Regard Modulation
(`relationship_bond_modulation`, `world/magic/services/pull_modulation_relationship.py`):
empowers a relationship-thread pull by the owner's own bond strength
(`CharacterRelationship.pair_depth()`) to the thread's threaded person
(`Thread.target_relationship.target`), when the live target IS
that person or holds a hostile (`conflict > affection`) relationship toward them
(they're "threatening" them). Deliberately **no** `Regard Polarity` gate — unlike
Court's NPC-preference sign-matching, this rewards any PC-to-PC relationship
investment unconditionally (rival or lover alike). Magnitude is a staff-tunable
saturating curve (`RelationshipBondPullTuning`), not a fixed ratio, since
`CharacterRelationship` values are unbounded (unlike `NpcRegard`'s `0..REGARD_MAX`).
The combat-UI picker surfaces `InapplicabilityReason.RELATIONSHIP_NO_STAKE`.
_Avoid_: regard bonus, court modulation (different mechanic, different narrative
purpose — see Court Regard Modulation above).

**Relationship Trigger Check**:
`_relationship_pull_would_trigger(x_sheet, y_sheet)`
(`world/magic/services/pull_modulation_relationship.py`) — shared between
`relationship_bond_modulation` and the picker's
`_relationship_pull_would_have_effect`, so the trigger rule can't diverge between
the two call sites (mirrors `_regard_polarity_matches`'s role for Court
modulation). True when `x_sheet == y_sheet` (direct) or `x_sheet` holds an active,
mutually-consented, net-negative `CharacterRelationship` toward `y_sheet`
(indirect — "threatening"). (#1849.)

**Bounded Percent Lane** (#2643, ADR-0158):
A percent-buff/debuff mechanic whose SUMMED contribution is clamped to a flat cap
before it multiplies damage — the EQ2 lane guard against percent sources
compounding into an unbounded spike. Two live lanes: the `team_damage_percent`
lane (Uplift, ally-side, `TEAM_BUFF_LANE_CAP_PERCENT`) and the
`ConditionDamageInteraction.damage_modifier_percent` lane (Undermine, enemy-side,
`ENEMY_LANE_CAP_PERCENT`). Any future percent lane reuses one of these two rather
than adding a third.
_Avoid_: "damage multiplier stack" (ambiguous with the unbounded legacy
`power_multiplier` target, which this deliberately does NOT fold into).

**Vow-Keyed Stacking** (#2643, ADR-0158):
Diminishing returns applied WITHIN one vow's contributions to the bounded
team-damage-percent lane (100/50/25/25%... descending), while distinct vows stack
FULLY against each other — `world.magic.services.techniques
.vow_keyed_diminished_total`, grouped by `conditions.ConditionInstance.source_vow`.
Mechanically rewards multi-vow engagement over single-vow spam, echoing the
four-layer vow-power model's own incentive (ADR-0149).

**Execute** (#2643):
A damage-profile authored ramp (`AbstractDamageProfile
.execute_missing_health_multiplier`) that scales a landing hit's damage up as the
TARGET's PRE-hit health runs low — `1 + multiplier * missing_health_fraction`,
never computed off post-hit health (which would be self-referential). Strike-family
techniques opt in; default 0 elsewhere.

**Ambient Activation** (#2708, ADR-0169):
The test for whether a thread contributes *passively* to a capability's power figure —
`world.magic.services.resonance._anchor_ambiently_active`. Strictly stricter than
anchor-in-action (`_anchor_in_action`): a thread pull may be authorised by player
assertion because it is paid for; a free passive contribution costs nothing, so it must
be demonstrable — every arm tests real state (actually-worn items, the character's
actual current room, the technique/trait actually in play) rather than trusting the
caller. Feeds `CharacterThreadHandler.contextual_thread_power`, one of the two terms
(with `context_free_power`) composing the `power` figure that curves a technique's
`TechniqueCapabilityGrant`. See `docs/systems/conditions.md`'s "Capability magnitude
curve" section for the full nine-arm breakdown and the deferred ORGANIZATION arm.
_Avoid_: "passive anchor check", "auto-pull" (that names the automatic defensive pull in combat, #5066).

**Thread carry** (#4097):
A thread woven into a technique also empowers, at the thread's full level, every
technique that technique is a transitive prerequisite for (a `TechniqueKnownRequirement`
chain, possibly several hops deep, possibly including a hidden ultimate). Read on
demand, never moved or stored: `prerequisite_technique_ids`
(`services/technique_prerequisites.py`) walks the requirement graph;
`PullActionContext.involved_technique_closure` unions it with the pull's own involved
techniques; `_anchor_in_action`'s TECHNIQUE branch tests the closure instead of the
bare involved-technique set. Applies to both casts and paid pulls (both resolve
through `_anchor_in_action`); deliberately does NOT widen the passive **Ambient
Activation** sweep (above): a prerequisite's thread isn't itself demonstrably in use
just because something it unlocked is being cast. See
`docs/adr/adr-4097-threads-carry-through-technique-prerequisites.md`. The
prerequisite gate itself (whether a character may *learn* a technique at all) is
**Technique prerequisite**; see `progression/AGENT_GLOSSARY.md`.
_Avoid_: thread inheritance, prerequisite thread (the thread itself doesn't move or
copy; only its empowering effect reaches further).

_Avoid_: invisible (use "intangible" when referring to the game-mechanical untargetable state)

**Ultimate** (#4098):
A `Technique` flagged `is_ultimate=True`: a power otherwise out of reach, reachable
only through Audere or Audere Majora. Reuses the catalog, payload tables, and cast
path of an ordinary technique; the flag is what keeps it off every everyday cast
surface, not a separate model. Two kinds: **owned** (the character's Path x major
Gift pushed to its limit, attached via `PathGiftGrant.ultimate_techniques`) and
**bond** (a patron being, a companion archetype, or one of the character's alternate
selves makes it available while the bond holds; choosing an alternate self's ultimate puts
her in that self, #4731). A Court
pact enhances qualifying ultimates the same way it enhances qualifying techniques; it
never grants ultimates of its own.
_Avoid_: super move, limit break, unlocked technique.

**Gift ultimate** (#4118):
An ultimate attached to a MINOR gift through `Gift.ultimate_techniques` and revealed at
Audere to any character holding that gift, whatever their Path (`UltimateSource.GIFT`). A
major gift's ultimates stay on its Path Gift Grants (owned).
_Avoid_: minor ultimate, gift power.

**Known ultimate** (#4098):
A character's discovery of an ultimate: a `KnownUltimate` row (`character`,
`technique`, nullable `crossing`, `readied`), never a `CharacterTechnique`. Once
known, it joins the character's known ultimates for every later Audere; an **owned**
known ultimate stays listed regardless of which Path is current, as long as the
granting Gift is still held as MAJOR; a **bond** known ultimate is listed only while
that bond is active. It cannot be cast outside Audere or Audere Majora.
_Avoid_: unlocked ultimate, learned ultimate (learning is the ordinary-technique
vocabulary; an ultimate is discovered, not learned).

**Readied ultimate** (#4098):
The character's single active pick for the current Audere: the one `KnownUltimate`
row with `readied=True` (a DB constraint enforces at most one per character).
Choosing an ultimate at the reveal readies it; it does NOT cast it. The readied pick
is castable only through the ordinary combat declaration while an active DECLARING
round holds, and is cleared on the next Audere accept, a Crossing, or Audere's end.
_Avoid_: active ultimate, equipped ultimate.

**Reveal** (#4098):
The set of ultimates an Audere or Audere Majora offers a character to choose from,
grouped by category. Computed fresh on every read (`ultimate_reveal_for`) from the
character's current owned/owned-known/bond pools, never an offer table written at
accept time. A known ultimate's card shows its name and description; an undiscovered
one shows only its authored category label (Sword/Shield/Crown's evocative display
name), never its name, description, or identity.
_Avoid_: offer, ultimate list (the reveal is derived state, not a stored offer).

**Owned ultimate** / **Bond ultimate** (#4098):
The two kinds of ultimate (spec decision 1). An **owned** ultimate comes from the
character's own Path x major Gift; a **bond** ultimate comes from a patron being, a
companion archetype or one of her alternate selves and is available only while that bond
holds, since bonds make
ultimates available but never spend or refuse on the character's behalf (spec
decision 5, "the character pays").
_Avoid_: patron ultimate / companion ultimate as the category name (those are bond
*sources*, not a third kind alongside owned and bond).

**Certain death (deferred)** (#4098):
See `vitals/AGENT_GLOSSARY.md`.

**Manifestation option** (#4118):
A `TechniqueManifestOption` row: one entity (a `WorshippedBeing` or a `CompanionArchetype`,
exactly one) a technique can bring into a fight, with a `tier` that sizes a being's
arrival. A technique with any option is a manifesting technique. Authored per technique;
it is a menu, not a choice.
_Avoid_: summon option, entity FK, summon (the flow-payload `summon_ally` threat-pool
summon is a different, reactive mechanism).

**Character manifestation** (#4118):
A `CharacterManifestation` row: which manifestation option one character brings when they
cast a manifesting technique, keyed by (character, technique) so it covers an ultimate
that has no `CharacterTechnique`. It holds only while the character's bond to the entity
(active patronage, a being pact's included, or their own unreleased companion of the
archetype) holds. Chosen by the player with the technique picker (#4341), or set by staff.
_Avoid_: manifest choice, summon binding, bonded summon.

**Fury** (#567, reworked #4738):
A chosen trade of control for intensity, declared with a technique cast and the **kindled** resonance she gives in to (#5124; it was an anchor person, ADR-5124). The chosen **Fury tier** is a preset amount of control she surrenders for the rest of her engagement; her control roll's outcome picks the **Fury degree share** of the trade she buys, and how strongly the resonance is kindled sets the deepest tier offered and eases the roll. Both land on her `CharacterEngagement`. Both land on her `CharacterEngagement`. **Berserk** is the far end: a tier with `berserk_severity` above 0, chosen, never rolled into.
_Avoid_: fury bonus, lucid check, losing control to Fury.

**Magic Activity** (#4450, ADR-4450):
A kind of magical roll that adds staff-chosen skills, one `MagicActivity` member each: the anima ritual, technique learning, ritual working, sustaining magic, dispelling, magical treatment, Soulfray resilience, resisting loss of self, Soul Tether rescue, Performing Sineating, Court petition, Fury control, moon control, enduring hostile resonance, feeding restraint, sensing magic, worship rite, invocation, ceremony, companion binding and dream peril. Staff map an activity to skills with `MagicActivitySkill` rows (a skill and a weight each); the roll keeps its own check type and adds those skills as terms. An activity with no row adds nothing. A technique cast is not an activity; its skill is the **Technique skill**. A new magical roll joins by adding a member and passing `activity_skill_terms(<member>)`.
_Avoid_: magic check type, roll category, skill bundle.

**Technique skill** (#4450, ADR-4450; #5002, ADR-5002):
The one skill a technique cast adds to its roll, on top of the caster's Anima Check. Resolved in order: the technique's own `skill` override; otherwise the `skill` of the **casting style** the cast is worked in (`TechniqueStyle.skill`): the technique's Gift's own `style` when it sets one (ADR-0199), else the caster's current Path style. That is the same style that sets the cast's concealment (`casting_style`), so a cast's manner and its skill never disagree; a technique cast after a Crossing adds the new Path's style skill (#5002 retired #4555's own-Path rule). It enters the roll at weight 1.00 as an `ExtraTraitTerm`. With none set, or an inactive skill, the cast adds nothing. Resolved by `technique_skill_term` / `resolve_cast_check`.
_Avoid_: path skill (a Path sets a style, and the style carries the skill), spell skill.

**Drift** (#4672, slice 4 #4733; reread by #5123):
The code's name for resonance of a non-main affinity that has grown past who the character is: `drift_for`, `drift_holdings` (rows of such an affinity with lifetime earned, not balance, so a spent streak still counts), `DriftConfig`, `DriftReading`. It is what a character is **Unsettled** by, and what atoning may convert. Players never see the word drift.
_Avoid_: aura drift (that is `AuraDrift`, the older, different sense: the shift in the aura's stored percentages when `recompute_aura` runs), corruption, taint, off-affinity resonance.

**Drift correction** (#4733):
Converting drift into the character's own resonance through deeds, player-facing **Atone** (#5123): a deed in the main affinity in a live scene opens a **Conversion offer**, and the character answers it with the **Rite of settling** (Disown the unsettling resonance). It is separate from **Fall** and **Redemption**, which change a character's affinity, and from accepting; atoning moves lifetime resonance (their own excess) toward a resonance the character is growing and leaves the affinity alone, and spends balance only as far as it exists, so it works after the excess was spent. The aura follows because `lifetime_earned` moves. It uses the same authored pair rates as Fall and Redemption (`AffinityInteraction.conversion_multiplier`).
There is one rite, the rite of settling. "Atonement" is the plain word for its reflections that turn away from something (disowning); the old Rite of Atonement, a separate rite that never ran, was removed in #4751.
_Avoid_: the Rite of Atonement (removed), purge, cleansing, aura correction.

**Conversion offer** (#4733, one per character since #5124):
A `DriftConversionOffer`: a character's one open chance to correct drift, opened when a deed (a `GainSource` in `DEED_GAIN_SOURCES`) grows a resonance of their main affinity while they are unsettled and hold drift they could convert toward it and stand in a live scene, and extended by later deeds in any scene. It holds one `DriftConversionCap` per target resonance, the most that may be converted toward it (caps from several scenes merge per resonance). It stays open until the rite of settling spends it or no cap is left; it no longer lapses when the scene ends. A deed settled away from a scene opens none.
_Avoid_: pending offer (the `AbstractPendingOffer` family is a different shape), conversion window, correction quest.

**Rite of settling** (#5124; was the conversion rite, #4733):
The one ritual that carries out every waiting **Reflection**, designated by `DriftCorrectionConfig.rite`: the character offers up one item that counts (tied to a resonance the rite moves, carrying a motif facet of it, or meaning enough to them), a configured check is rolled with their worn focus added, and the outcome tier's share (`DriftCorrectionOutcomeShare`) applies to each reflection: Embrace a deed grows what it earned, Disown a deed turns most of it toward the main affinity, Embrace the unsettling resonance accepts the aura's change, Disown it atones up to the open chance. A failed roll spends the offering and takes every reflection while moving nothing. Performed by `perform_settling_rite`; recorded as a `SettlingRite`.
_Avoid_: correction check, drift roll, purification, conversion rite (the old name), accept button.

**Thread retune** (#4735, slice 6 of #4672; reshaped by #5123):
Moving part of one of a thread's resonances to another of its resonances by performing the retune rite (the SERVICE ritual at `THREAD_RESONANCE_SERVICE_PATH`). It moves an amount between two `ThreadResonance` rows on the same thread: within the source resonance's affinity one for one; across affinities it is a Fall or a Redemption of that amount at the authored pair rate (floored at 1). The thread's level and `developed_points` do not change; the leading resonance follows the larger row. It changes no balance and no affinity, unlike a **Fall** or **Redemption** of the character, which converts every thread's rows in the affinity.
_Avoid_: reweave (weaving makes a new thread), thread conversion (the full Fall re-anchors every thread), respec.

**Substance** (#5125, ADR-5125; was Gift substance, #5018):
What a major gift works through and can perceive and control, as one entry in a single staff-authored list (`Substance`): fire, ice, shadow. A Gift points at one (`Gift.substance`, never on a minor gift; a child gift with none uses its parent's), and so do the Primum a place or creature holds, a Primum item template and an item that carries it. Ice and water are two substances: a gift's boundary is narrative, not scientific. It may name the room condition it grows along. Its optional `property` is carried by every technique of a major gift with it. Two substances may stand as related or opposed (`SubstanceRelation`, authored once, never chained). _Avoid_: element, medium, gift substance (the old per-gift mapping), resonance (a resonance is identity and currency; a substance is a thing the Gift works).

**Technique marks** (#5066, ADR-5066):
A technique's own `Technique.properties`: the properties that say how it works (a blink carries `teleport`, a smoke form `incorporeal`), ticked per technique by staff. They are the technique's effect properties for capability sources, applications and clash opposition (`effect_property_ids_by_technique`, `world/magic/services/technique_marks.py`). The gift's resonances never count. _Avoid_: technique tags, resonance properties (those belong to the resonance).

**Primum** (#5125, ADR-5125):
The magical essence of one substance, always typed: fire Primum, ice Primum, never an untyped Primum and never a number on a character sheet. A place or a creature holds some, in amounts that read as a **Primum step**. Primum can be harvested only from a lair or a slain creature, and harvested Primum is an item. _Avoid_: mana, essence (untyped), crystal, magic points.

**Primum step** (#5125):
One named band of how much Primum a place or creature holds (`PrimumStep`, ordered by `rank`; the starter names are Trace, Some, Rich and Massive), worth a number of power points to a caster whose gift matches when a place holds it (a creature's step is only sensed and harvested, never drawn on by a cast). Staff own the rows; code compares only the rank. The lowest step, Trace, is what an ordinary room whose condition leans the substance's way reads. _Avoid_: level, tier (those name the Kindled and quality scales), measure.

**Sighting** (#5125):
A character's record that she has sensed one substance's Primum in one room (`PrimumSighting`), written by a perception check and ended when she leaves. A mage always perceives her own gift's substance without one. A source of another substance she has not perceived is never named to her. _Avoid_: scan, detection, discovery.

**Calling up** (#5018; reshaped by #5125):
Raising the Primum of a gift's substance in the place she stands by one step, for one shared anima amount set once for every substance, with no resonance charge. It happens automatically as part of a cast where the substance is missing (only up to Trace), or with no technique (`call_up_substance`, telnet `callup`). It writes a `PrimumCallUp` that lasts while she stays, and the room sees one line the game writes ("<name> begins to manifest fire in the area."). Never refused for anima. _Avoid_: summon, conjure, generate.

**Affinity skill** (#5308, ADR-5308):
The one Magic skill staff link to an affinity (`Affinity.skill`): Villainy for Abyssal, Heroism for Celestial and Reflection for Primal. It is added to the **Bonus resonance check** of every resonance gain or spend in that affinity, so a trained character earns more and gets more from spending it. Reached only through the affinity, never named in code. The Primal skill Reflection is not the **Reflection** a pose or journal entry makes, and not the Reflection step of character creation. _Avoid_: affinity stat, alignment skill.

**Bonus resonance check** (#5308, ADR-5308):
The check every earned resonance gain rolls, once per affinity the act pays (`ResonanceGainConfig.bonus_check_type`, `roll_gain_bonus`). The stat of the act that earned the resonance replaces the check's stat, the **Affinity skill** is added, and the result sets a percentage (`ResonanceCheckAward.gain_bonus_percent`) the gain grows by. A staff grant and every conversion roll nothing; a **Mark** rolls once, with the stat of its act. _Avoid_: skill bonus, flat bonus.

**Resonance worth** (#5308, ADR-5308):
What one resonance is worth when it is spent, as a percentage: a thread pull rolls the same check with the stat of the action and scales every effect it bought by the result (`ResonanceCheckAward.spend_worth_percent`), and a kindled cast scales its kindled power the same way. The affinity's `spend_worth_floor_percent` is the least it can be. Previews show 100 and never roll. _Avoid_: spend bonus, pull multiplier.

**Trickle** (#5308 changes it; #2036 and #4520 made it):
The small amount of resonance a character's days earn: a resident's room tags and a worn piece's facets, written once a day as a `TrickleAccrual` row. A trickle pays nothing until a **Trickle harvest**, and it is not a grant, so it moves no balance.

**Trickle harvest** (#5308, ADR-5308):
What an Anima ritual with a partner does to the waiting trickles of the performer, successful or not: one `TRICKLE_HARVEST` grant per resonance, grown by the ritual's **Bonus resonance check** for that resonance's affinity, and every row it covered is stamped `harvested_at`. It earns no pledge favor. _Avoid_: collecting, payout.

**Reach** (#5308, ADR-5308):
The resonance a pose names when its author poses and points at no act (`PoseResonanceReach`, one per pose; web `reach_resonance_id`, telnet `pose/reach <resonance>=<text>`), in her aura or not. It pays nothing at once: whoever endorses the pose confirms that resonance instead of picking one, and it pays when the weekly settlement runs. A pose that also points at an act is a **Mark** and writes no reach. Not a **Reflection** and not a **Mark**. _Avoid_: aim, target resonance.

**Present (substance)**:
A place that holds at least the first Primum step of a substance (Trace), whether from its ordinary condition, a call-up or a scene's GM mark (`stage_substance`). _Avoid_: available, active.
