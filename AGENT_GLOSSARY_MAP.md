# Arx II agent glossary map

Ubiquitous-language reference for agents and developers. This file holds the
**cross-cutting (root) terms** that span apps; each app keeps its own
`AGENT_GLOSSARY.md` next to its code for domain-local vocabulary. Definitions
describe what a term **IS**, not what it does; when synonyms exist one canonical
term is chosen and the rest are listed under `_Avoid_`.

## Per-app glossaries

- [magic](src/world/magic/AGENT_GLOSSARY.md)
- [covenants](src/world/covenants/AGENT_GLOSSARY.md)
- [scenes](src/world/scenes/AGENT_GLOSSARY.md)
- [combat](src/world/combat/AGENT_GLOSSARY.md)
- [conditions](src/world/conditions/AGENT_GLOSSARY.md)
- [checks](src/world/checks/AGENT_GLOSSARY.md)
- [mechanics](src/world/mechanics/AGENT_GLOSSARY.md)
- [progression](src/world/progression/AGENT_GLOSSARY.md)
- [classes](src/world/classes/AGENT_GLOSSARY.md)
- [societies](src/world/societies/AGENT_GLOSSARY.md)
- [relationships](src/world/relationships/AGENT_GLOSSARY.md)
- [secrets](src/world/secrets/AGENT_GLOSSARY.md)
- [justice](src/world/justice/AGENT_GLOSSARY.md)
- [clues](src/world/clues/AGENT_GLOSSARY.md)
- [codex](src/world/codex/AGENT_GLOSSARY.md)
- [stories](src/world/stories/AGENT_GLOSSARY.md)
- [gm](src/world/gm/AGENT_GLOSSARY.md)
- [missions](src/world/missions/AGENT_GLOSSARY.md)
- [npc_services](src/world/npc_services/AGENT_GLOSSARY.md)
- [tarot](src/world/tarot/AGENT_GLOSSARY.md)
- [currency](src/world/currency/AGENT_GLOSSARY.md)
- [achievements](src/world/achievements/AGENT_GLOSSARY.md)
- [goals](src/world/goals/AGENT_GLOSSARY.md)
- [items](src/world/items/AGENT_GLOSSARY.md)
- [traits](src/world/traits/AGENT_GLOSSARY.md)
- [areas/positioning](src/world/areas/positioning/AGENT_GLOSSARY.md)
- [buildings](src/world/buildings/AGENT_GLOSSARY.md)
- [forms](src/world/forms/AGENT_GLOSSARY.md)
- [battles](src/world/battles/AGENT_GLOSSARY.md)

## Relationships (how the root concepts connect)

Both the web frontend and telnet converge on **`action.run()`** — the **Seam**. An
**Action** owns its prerequisites and execution and calls **Service Functions** for
state changes; **Commands** are the thin telnet layer. **Flows** are a separate
reactive layer where **Triggers** run flows in response to **Events**. A **Check**
resolves an attempt through the rank/chart/outcome pipeline into a graded
**CheckOutcome** that draws from a **Consequence Pool**; **Modifiers** adjust it. A
**Round** (action-driven) sequences declarations inside a **Scene**; **combat** is
one specialization. **Personas** are the IC identities that own reputation and
appear in scenes; **Threads** are the magic currency that anchors to traits,
techniques, sanctums, relationships and other targets. Progression runs along a
**Path** of **Levels**, narrated as **the Durance**, measured by **Legend** and
awarded live through **Renown**.

## Architecture seam

**Action**:
A self-contained unit of game behavior (`src/actions/`, base class `actions.base.Action`)
that owns its own prerequisites (permission checks) and execution; anything a player
can do is a real Action. _Avoid_: command, handler.

**Seam**:
The single `action.run()` doorway that both the web dispatcher and telnet commands
converge on, so one Action serves both interfaces. _Avoid_: entrypoint, gateway.

**Service Function**:
A function in `src/flows/service_functions/` that performs an actual state change;
Actions and Flows call service functions rather than mutating state inline. _Avoid_: helper, util, manager method.

**Command**:
The thin telnet-compatibility wrapper (`src/commands/`) that parses text and calls
`action.run()`; it carries no business logic. _Avoid_: action.

**ActionRef / dispatch_player_action**:
The reference and dispatch path by which the web frontend names an Action (by registry
key) and routes intent through the seam. _Avoid_: command string.

**SCENE_ADAPTIVE**:
The `ActionBackend` for actions that work both inside a combat/scene round and outside
one (e.g. a standalone technique cast); the round rules decide immediate, deferred, or
blocked execution. _Avoid_: combat-only, always-immediate.

**Flow**:
A database-defined workflow (`FlowDefinition` + steps) in the reactive layer that
executes game logic in response to events. _Avoid_: script, pipeline.

**Trigger**:
A `TriggerDefinition`/`Trigger` that listens for a named **Event** and runs a Flow in
response. _Avoid_: signal, hook, listener.

**Event**:
A named occurrence (`EventName` choice) emitted during play that Triggers can react to;
the codebase uses explicit service-function calls, not Django signals. _Avoid_: signal.

**Object State (BaseState)**:
A mutable wrapper (`flows.object_states.BaseState` and subclasses like `CharacterState`,
`RoomState`) placed around an Evennia object during flow execution to expose dynamic
permissions and scene state. _Avoid_: proxy, adapter.

**Behavior**:
A reusable package of game logic attached to an object that supplies actions/handlers
it can participate in. _Avoid_: mixin, component.

**Enhancement / Effect**:
An `ActionEnhancement` links a source (item, condition, technique) to a base Action and
contributes typed **Effects** (handlers in `actions/effects/`) that modify how the action
resolves. _Avoid_: buff, modifier (Effect is the action-layer term; Modifier is the
mechanics-layer term).

## Identity

**Persona**:
An in-character identity a player presents (`PRIMARY` / `ESTABLISHED` / `TEMPORARY`);
reputation and IC-meaningful state hang off the Persona, never the account. _Avoid_: character, alt, mask.

**CharacterSheet**:
The source-of-truth anchor for a character's mechanical data (traits, vitals, sheet
state) that personas and forms compose over. _Avoid_: profile, stats blob.

**Guise**:
A projected fake overlay (a mask/disguise/illusion) shown over the real form; it reverts
to the current real form when pierced. _Avoid_: disguise, alias.

**Roster**:
A category group of characters (Active, Inactive, Available, etc.) used for character
lifecycle and applications. _Avoid_: cast list.

**RosterEntry**:
The bridge record linking one character (ObjectDB) to its Roster. _Avoid_: membership.

**RosterTenure**:
A player↔character relationship over a span of time, carrying anonymity (player number)
and approval data; `end_date` null means current. _Avoid_: ownership record.

## Resolution

**Check**:
A resolved attempt run through the rank/chart/outcome pipeline; it exposes a graded
outcome and never leaks raw roll numbers. _Avoid_: roll, dice check.

**CheckType / CheckRank / ResultChart / CheckOutcome**:
A **CheckType** is the database-defined kind of check (weighted traits + aspects); a
**CheckRank** is a banded tier of capability; a **ResultChart** maps the rank difference
and points to a graded **CheckOutcome**. _Avoid_: difficulty class, DC, pass/fail.

**Consequence Pool / graded outcome**:
The authored pool of consequences a graded outcome draws from; difficulty comes from
authored model/config fields routed through the pool, never hardcoded constants or binary
pass/fail. _Avoid_: loot table, success/failure flag.

**Capability**:
A gating ability that determines whether a character may attempt or benefit from
something, granted by techniques, conditions, or progression. _Avoid_: permission, perk.

**Challenge / ChallengeInstance**:
A **Challenge** is the authored obstacle definition resolved through checks; a
**ChallengeInstance** is one live instantiation against participants. _Avoid_: encounter (combat-specific), test.

**Modifier / ModifierTarget**:
A **Modifier** adjusts a resolved value; its **ModifierTarget** names which derived value
or check the adjustment applies to. _Avoid_: bonus, buff.

**Round / RoundContext**:
A **Round** is one action-driven cycle of declarations; the **RoundContext** is the seam
object carrying its mode and state. Rounds advance on actions, never on wall-clock time
(dangerous progression must never advance while AFK). _Avoid_: turn timer, tick.

**Round mode (OPEN / POSE_ORDER / STRICT)**:
The resolution mode of a Round — **OPEN** (free declaration), **POSE_ORDER** (informal
turn order), or **STRICT** (enforced order); a danger round is `STRICT` specialized with
`DANGER`. _Avoid_: forced mode, combat mode.

**Focused vs Secondary action**:
Within a round a character takes one **focused** action plus up to two **secondary**
actions; focused-vs-secondary is the per-round choice, not a trait of the technique.
_Avoid_: passive (for "secondary"), main/off (for the pairing).

## Four character primitives

**Distinction**:
An authored, individualizing trait-tag that marks what makes a character particular
(and can anchor threads/checks). _Avoid_: feat, tag.

**Condition**:
A time-bound state applied to a character (template → instance → stage) that can alter
checks, capabilities, or behavior. _Avoid_: status effect, buff/debuff.

**Resonance**:
A magical affinity-tied charge a character earns and spends (a `balance` with
`lifetime_earned`); resonance gains feed dramatic and progression mechanics. _Avoid_: mana, essence.

**Secret**:
A piece of concealed canon scoped per knower; the `secrets` app stays dependency-free and
other systems FK into it. _Avoid_: rumor, mystery.

## Covenants

**Court Pact**:
The per-(Court covenant, servant) sworn-fealty bond carrying the master's `granted_pull_cap`; the
cap bounds the servant's Court-role thread pull level. The grant is the gate: no active pact → an
effective cap of 0 → cannot pull. _Avoid_: mentor bond, patron, indenture.
Full entry: [covenants AGENT_GLOSSARY](src/world/covenants/AGENT_GLOSSARY.md).

## Combat-magic surface (#1584)

**Allegiance**:
Which side a `CombatOpponent` fights on — `ENEMY` (hostile to PCs, the default) or
`ALLY` (fights for the party). Mutable: summons create `ALLY` opponents; future charm
or switch-sides flips an existing `ENEMY`. One `CombatOpponent` model covers both cases
(ADR-0059). _Avoid_: faction, team (as model-attribute names).

**Summon** (in-combat):
An `ALLY` `CombatOpponent` conjured during combat by a technique
(`CombatOpponent.allegiance=ALLY`, `summoned_by` FK → `CharacterSheet`,
`bond_expires_round`). It attacks `ENEMY` opponents via
`CombatOpponentAction.opponent_targets`. The per-app glossary (combat) has
the full entry. _Avoid_: familiar, pet, companion (for the in-combat row).

**Intangibility** (conditions gate):
The untargetable-in-combat status conferred by a `ConditionInstance` whose
`ConditionCategory.grants_intangibility` is `True`. Checked by `is_untargetable(objectdb)`
in `world/conditions/services.py`. Seeded as Ghostform and Earthmeld by the effect palette.

**Reactive interceptor**:
A mutation-only `DAMAGE_PRE_APPLY` flow handler: force-field (`absorb_pool`, priority 10),
reflect (`reflect_damage`, priority 20), or blink (`blink_dodge`, priority 30). Sets
`payload.amount = 0` on success; fizzles on insufficient `reactive_anima_cost`. No
`CANCEL_EVENT` child step — mutation-only (ADR-0060).

**Effect palette**:
The seeded set of nine castable combat effects (`ensure_effect_palette_content()` in
`world/magic/effect_palette_content.py`). See the magic per-app glossary for the full entry.

## Magic spine

**Thread**:
The magic currency/anchor (`world.magic.Thread`) that ties a character to a typed target
(trait, technique, facet, relationship track, capstone, covenant role, or sanctum) and is
levelled and pulled. _Avoid_: bond, string, link.

**Anima**:
A character's animating magical reserve (`CharacterAnima`) drawn on to perform rituals and
weave threads. _Avoid_: mana, energy.

**Intensity vs Power**:
**Intensity** is the authored tier/magnitude band of a technique's effect; **Power** is the
realized force a particular casting brings to bear. Keep them distinct — they are not synonyms. _Avoid_: using "power" for "intensity".

**Signature Motif Bonus**:
A staff-authored catalog row (`world.magic.SignatureMotifBonus`) that a player attaches to a
TECHNIQUE-kind Thread to *sign* that technique — applying their Motif above the Gift baseline.
It is an **additive flourish** (intensity delta + conditions + cosmetic prose), NOT a
`TechniqueVariant` and NOT a resonance-divergence. Gate: character's Motif must satisfy the
bonus's `required_facet` / `required_resonance` (AND semantics). (ADR-0065, #1582.)
_Avoid_: signature variant, signature specialization.

## Progression & legend

**Durance**:
"The Durance" is a character's whole life-journey through the world; it is the narrative
frame over the Class/Level backend, not a single event. _Avoid_: "a Durance" (singular event), career.

**Ritual of the Durance**:
The dramatic ceremony that advances a character a Level — one rite within the Durance.
_Avoid_: "a Durance", level-up.

**Audere Majora**:
A dramatic advancement event (a threshold-crossing) that can mint a legend deed; treated
purely as a neutral progression/resolved-pool surface. _Avoid_: restating its ceremonial wording or any in-world purpose.

**Path / PathStage / Level**:
A **Path** is the progression track a character follows; a **PathStage** is a named band
along it; a **Level** is the discrete advancement step within the backend. _Avoid_: class tree, tier.

**Legend / Legend Points**:
**Legend** is the metric of how storied a character is; **Legend Points** are awarded only
for storied/dangerous deeds, never as a combat/XP grind. _Avoid_: XP (for Legend), score.

**Renown**:
The live award mechanism (`RenownAwardConfig`, `fire_renown_award`) that fires legend/
resonance awards for qualifying deeds; Renown is the mechanism, Legend is the metric.
A second, narrower Legend-award pathway exists for the stakes-consequence engine
(#1716): `ConsequenceEffect.LEGEND_AWARD` -> `_legend_award` ->
`create_legend_event` (`world/mechanics/effect_handlers.py`,
`world/societies/services.py`) fires Legend only (no Fame/Prestige/reputation) from a
Beat's consequence pool, scaled by `Beat.risk` x outcome tier — as of #1770, the
risk term is read via `effective_risk_for_beat(beat)`, which prefers the beat's
open stakes-contract `StakeContractActivation.effective_risk` (party-level-priced)
over the raw declared `Beat.risk` when a contract is active; see
`src/world/stories/AGENT_GLOSSARY.md` for the stakes-contract vocabulary
(Stake / Severity / Fuse / Effective Risk / Activation). `fire_renown_award`
stays the mechanism for GM-authored public events that also move Fame/Prestige/
reputation; the two pathways are deliberately separate (#1716 stays Legend-only) and
both reuse `RenownRisk`/`RISK_LEGEND_AWARDS` for the risk axis. _Avoid_:
blanket-avoiding "renown"; fame, reputation; assuming `fire_renown_award` is the only
Legend-award path.

**XP / Kudos / Development Points**:
Out-of-character advancement currencies for creating content and developing a character;
XP is never a combat reward (combat merits Legend, not XP). _Avoid_: using XP for in-combat awards.

## Achievements & discovery

**DiscoverableContent**:
A Django abstract base (`world.achievements.models.DiscoverableContent`) that adds one
nullable `discovery_achievement` FK (→ `Achievement`) to any content model whose instances
can be discovered for the first time. Inherited by `Technique` (magic app) and `CovenantRole`
(covenants app); null FK means the content is not discoverable. Chosen over GenericFK (rejected per
ADR-0015) and per-model field duplication (rejected per ADR-0016). _Avoid_: discoverable mixin, achievement holder.

**Access change**:
The event of a character gaining or losing access to techniques or capabilities, regardless of
source (alternate-self shapeshift, covenant role, character creation). Handled by the single surface
`announce_access_change` in `achievements/discovery.py`; callers never branch on source.
_Avoid_: ability grant, capability notification, technique change.

## Public-event vectors

**Scene**:
A unit of recorded roleplay among personas; scenes are provisional/ephemeral by default
with explicit keep-vs-discard agency, and interaction (targeting another PC) is what makes
one. _Avoid_: log, session.

**Gemit**:
A staff/GM real-time **push** broadcast, hand-authored verbatim and persisted for
reach-scoped retroactive viewing — the push vector of the public-reaction center. _Avoid_: broadcast, news, gossip.

**Tidings**:
The **pull**/browse feed of the public-reaction center, scoped to the societies a persona
hears through. _Avoid_: news feed, inbox.

## Process & design tenets

**Journey**:
An unbounded coverage goal for a domain (combat/social/magic), tracked as a GitHub
Milestone and sliced into plain-language gap issues. _Avoid_: epic, issue (a Journey is neither).

**Gap**:
A concrete, observed shortfall in a journey, filed as a single actionable issue. _Avoid_: bug, feature request (when it is a journey slice).

**Consent-gates-behavior**:
The rule that consent for an effect on another PC depends on whether it alters that PC's
*behavior* (compulsion/charm/fear), not on benign-vs-hostile; pure capability/stat changes
are consent-free. _Avoid_: consent-gates-harm.

**PvP non-lethality**:
The structural rule that PC-vs-PC combat never kills or injures — it resolves to yield or
knockout; lethality is exclusive to PC-vs-significant-NPC. _Avoid_: suppressed death branch.

**AFK-safe**:
The invariant that tempo is action-driven and dangerous progression never advances while a
character is away. _Avoid_: real-time, timed.

**Drama-maximizing**:
The standing design preference for the high-drama/ceremony path over the minimal switch
(e.g. a War Covenant "rises" via a banner-call ritual). _Avoid_: minimal/MVP framing as the goal.

**Individualization**:
The principle that mechanics should make characters more particular; homogenizing
"everyone gets the same grant" designs are rejected. _Avoid_: standardization, parity-by-default.

**Visibility = eligibility**:
The rule that what a viewer can see defines what they are eligible to act on; UI displays
are per-persona, never per-account. _Avoid_: global visibility.

**Provisional scene**:
A scene that is ephemeral by default and only persists on an explicit keep decision;
observation alone never auto-persists RP. _Avoid_: auto-saved scene, draft.
