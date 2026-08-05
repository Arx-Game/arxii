# Planned Systems — designed/intended, not built on either surface

**Purpose:** a durable home for systems and capabilities we intend to build but that have **no code
yet** (no service, model, viewset, Action, or command). Much of this was previously *implied and never
recorded* — mentioned in passing and silently lost. This registry exists so that design intent stops
disappearing. It is **explicitly incomplete and is the capture surface going forward** — add to it
freely; an entry here is recorded intent, not a commitment to a date.

**Relationship to other docs.** Per house policy (*journeys are milestones; only journey-driven issues;
no speculative issues*), planned-but-unbuilt systems live **here**, not as kanban issues — a system
graduates to an issue/milestone only when it becomes next-up. The
[player-reachability audit](../audits/2026-06-25-player-reachability-coverage.md) links its
PLANNED-UNBUILT tier here. Where a planned system *does* already have an issue/milestone, it is cited.

**Status key:** `intent` = no code; `partial` = a piece exists (named here) but the core is unbuilt;
`unrecorded` = surfaced from design conversation, not previously in any doc/issue.

> **Last full verification: 2026-08-05** — every entry below was checked against code (not docs) in
> the ledger-accuracy sweep. Twelve entries previously listed as unbuilt had in fact shipped; the
> still-unbuilt remainder was filed as issues #2985–#3004 and each is cited inline. ✅ DONE entries
> are kept as one-liners for provenance; their detail lives in the system docs.

---

## Cross-cutting primitives (build once, reused widely)

- **Damage/condition immunity & vulnerability framework** — "people who can't drown," vampires harmed
  by sunlight, fire-immune species, etc. `partial` — **#1740/#1588** built the core unified seam
  (`resolve_damage_type_resistance`; immunity = high resistance not boolean, ADR-0073) plus the first
  live trigger (Sunlight Exposure); **#1714** routed vehicle-hazard drowning/falling through it;
  **#1744** (ADR-0069) shipped the companion/location mitigation layer. Species-specific triggers
  beyond sunlight and the vehicle-hazard pair are still unbuilt.
- **Perception-override / altered-reality primitive** — "who perceives what is real." The two intended
  consumers each shipped as *separate mechanisms*: dreams as a room layer (`world/dreams` — sleep/wake/
  dreamwalk, peril branching) and illusion/disguise as form overlays (`DisguiseKind`,
  `ConcealmentLevel`, pierce contest). The shared seam — a scene where different participants perceive
  different realities — is still unbuilt, and `SceneRound` has no mode/variety axis. `intent` — **#2997**.

## Scenes & RP

- **Frictionless / implicit scene start** — a directed interaction starts a scene with no staff staging
  (`ensure_scene_for_location` is built-not-wired; only explicit StartScene wires it). `partial` — #1309, ADR-0006.
- **Provisional, EPHEMERAL-by-default scenes + explicit keep-vs-discard agency** — never auto-persist
  RP; the player decides what is kept. Summary draft→agreed exists; scene-level keep/discard does not.
  `partial` — #1309, ADR-0006.
- ✅ **Auto-close an empty scene** — DONE (#1361).
- **Intimate / private relationship scene variety** — a distinct scene mode (and mechanics) for the
  scenes where relationships are tested and capstones created. `intent`.
- **GM-run-table as a live scene variety** — today `GMTable` is only a membership grouping, not a live
  scene mode a player-GM runs. `intent`.
- **Dreamstate / illusionary scene varieties** — superseded in part: dreams shipped as a room layer and
  disguise as form overlays (see the perception-override entry above). What remains is the scene-level
  shared-altered-reality mode — **#2997**. Dreams also have **zero web surface** — **#3003**.
- **Community pose-of-the-scene voting / award** — `partial`: `WeeklyVote`/`VoteButton` are built but
  unwired (#2161).
- ✅ **New-player onboarding tutorial** — DONE (#1035; T1–T7 mission chain + e2e journey). Still
  `intent`: **friend list / "looking for RP" finder**; rich-text composer / conversation threading.

## Combat depth

- **Ranged / reach / archery** — `partial`, NOT greenfield. Technique targeting already has range
  bands (`SAME`/`ADJACENT`/`ANY`, `world/magic/models/techniques.py`), a `RANGED` weapon class, and a
  `bow`→`archery` skill mapping. Missing: positioning/range enforcement, line-of-sight, distinct
  archery actions. `partial`, `unrecorded`.
- **Mounts** — `partial`: mounted **combat** is DONE (#1843 — mount/dismount companion actions, charge
  + joust, mounted bonus/lance penalty, STABLES room feature). Mounted **movement** (travel-speed or
  room-transit effect while mounted) is still unbuilt; the `travel_speed` ModifierTarget exists with
  no source populating it.
- **Verticality / flying / rooftops** — vertical space and an aerial layer player surface (a
  positioning `enter_aerial` path exists internally but no player surface). `intent`, `unrecorded`.
- ✅ **Knockback + trap-into-combat hazards** — DONE (#1317).
- ✅ **Out-of-combat reactive interpose / DANGER-round arming** — DONE (#1316).
- ✅ **Shapeshift (voluntary + rage) + combat profiles** — DONE (#1111; `assume_alternate_self` /
  `revert_alternate_self`, derived `in_control`, `ShiftFormAction`/`RevertFormAction`, ADR-0014).
- ✅ **Transformation cause-paths** — DONE (#1604; `trigger_transformation` seam, technique
  `ASSUME_ALTERNATE_SELF` effect, involuntary trigger via flows, at-will gated by capability).
- **Combo mechanics — fuller rules** — combos exist (upgrade/revert); the exact rules need design.
  `partial`, `unrecorded`.
- ✅ **Soulfray-risk accept + fury commit** — DONE (#1454).
- **Duels** — non-lethal PvP + lethal PC-vs-significant-NPC. Milestone #8; NPC-tier lethality gap M#10
  (ADR-0023/0038/0040). (The duel *Actions* exist and are web-dispatchable.)

## Magic & progression

- **Spell system** — learnable, path-independent hedge magic usable by quiescent characters. No `Spell`
  model; all casting still flows Gift/Path/Technique/Thread. `intent` — **#3001**.
- ✅ **Post-CG Gift acquisition** — DONE (#1579 path-crossing grant; #2116 XP-buy/teaching-offer
  surface: `learn`, `/api/magic/gift-unlocks/purchase/`).
- ✅ **Trainer system** — DONE (#2440 TRAIN effect: NPC teaches a technique for AP + coin;
  `NPCRole.teaches_tradition`, per-technique offers with costs; seeded Academy Trainer +
  tradition-gated trainers + ghost tutelage #2460; Training Room AP discount). Check-based technique
  learning follow-ups remain open: #2739/#2740/#2741.
- **Path discovery / research / switching** — beyond listing next options. `intent`.
- ✅ **Resonance→aspect / aspect-in-magic** — resolved (#1363 closed; resonance→aspect mapping was
  rejected earlier as double-counting, #1357).
- ✅ **Soulfray progression** — DONE (#712).
- **Multi-target per-target consent state machine** — ADR-0045, `partial`.
- **ResonanceGrantReversal** — endorsements are currently irreversible. `intent` (named in code).

## Gift & resonance economy (ADR-0050–0057)

Designed as a connected set (ADRs 0050–0057); most of it has now landed. See
[`player-capability-ledger.md`](player-capability-ledger.md).

- ✅ **Major/Minor gift taxonomy** — DONE (#1577; `Gift.kind`, ADR-0050).
- ✅ **Species abilities as Minor Gifts** — DONE (#1580; `SpeciesGiftGrant` + `provision_species_gifts`,
  seeded vampire/lycan/dhampir sun-sensitivity, Wolf's Fury, Hunger, shade content; gift-lineage reach
  #2891). Content authoring continues — #2764.
- **GIFT thread anchor + per-target-kind cost** — a `GIFT` `TargetKind` + per-kind cost axis;
  gift-threads the costliest kind. ADR-0051. `intent`.
- **Gift resonance from the woven thread** — a gift's affinity read from its gift-thread resonance
  instead of the fixed `Gift.resonances` M2M. ADR-0052. `partial`.
- ✅ **The one specialization engine** — DONE (#1578; resonance × {gift, path, role} → customized
  techniques, ADR-0055/0016).
- ✅ **XP-unlock contract** — wired (#2131 closed the inert/unreachable spend loops; ADR-0053).
- **Signature technique-thread** — re-scope `TargetKind.TECHNIQUE` to a per-technique signature delta
  (own resonance, may diverge → discordant signature). ADR-0056. `partial` (the sibling gift-thread
  specialization #1581 landed).
- **Fall / Redemption conversion service** — resonance-type conversion without violating the monotonic
  `lifetime_earned` invariant. ADR-0054. `intent` — the conversion-table defect is one of the four
  tracked on #2967.
- **Covenant of the Court** — new `CovenantType.COURT` reusing the covenant substrate. ADR-0057. `partial`.

## Relationships, covenants & collectives

- **Relationship mechanics** — `partial`, and much further along than previously recorded: the
  mechanical payoffs ARE consumed (`bond_combat_bonus`/`bond_bonus`/`relationship_gated_contributions`
  read by combat clash/services and scene action services), and decay is computed-on-read over
  `DECAY_DAYS` (no cron needed). Still unbuilt: teamwork/coordination gating (needs a group scope —
  see adventuring party), the consent/deceit safety layer, and the content passes listed in
  [relationships.md](relationships.md).
- **Adventuring-party model** — group formation, shared legend, coordination. Missions/voyages/consent
  each carry their own membership slice; no party primitive. `intent` — **#2992**.
- ✅ **NPC reputation model** — DONE (`NpcRegard` −1000..1000 + `NpcRegardEvent` + config, with
  society/organization twins). Gap: **shops never read it** — no standing-based pricing or access.
  **#2995**.
- ✅ **Org-level ritual-leadership permissions** — DONE (#708).
- **Society politics** — mostly built since last recorded: territory (gang turf + crime cascade),
  warfare (see below), leadership succession (houses `SuccessionLaw`/`Title`/`FealtyEdge` + heredity),
  world-event influence (proclamations/propaganda/obligations). Still unbuilt: a **general
  alliance/treaty/betrayal instrument between orgs** — the only formal inter-org pact is
  `MarriagePact`. **#2999**.
- ✅ **Battle / army / warfare system** — DONE (`world/military`: `MilitaryUnit`/`Army` + services;
  `world/battles`: staging, resolution, fortifications, vehicles, war funding, city defense). War
  covenants now have somewhere to resolve into.

## Crafting, economy, items, estates

- ✅ **Item-creation pipeline** — DONE (`ItemCreateHandler` mints `ItemInstance` from
  `CraftingRecipeKind.ITEM_CREATE`; expressiveness arc #2881 added accents/ladders/refinement).
- **Materials / resources + harvesting loop** — `partial`: materials exist as crafting *requirements*
  (`MaterialCategory`, `CraftingMaterialRequirement`), but no player loop *produces* them —
  `world/agriculture` yields food only. Personal gathering (foraging/mining/salvage) is `intent` —
  **#2998**. Domain-level production is #2540's territory.
- **Recipe acquisition** (discover / learn / buy, skill-gated) — `intent`.
- ✅ **Crafting-station durability + repair economy** — DONE (#1234).
- ✅ **Crafting Action + telnet command** — DONE (#1866/#1931 closed the coverage gap).
- **Store / shop / vendor + player↔player trade** — `partial`: the market shipped (stalls, NPC stock,
  PC ware listings, fence #2862, finishing/service offers, fashion showcase economy #2959). Still
  absent: **negotiated two-sided player↔player trade, barter, auction** — the only direct channel is
  one-way `give`. **#2990**.
- **Ship system** — `partial`: battle vehicles (#1714), persistent ships + upgrades/repair +
  ship-as-sanctum (#1832), and **out-of-combat sea travel** (`Voyage` + actions + telnet) are all
  built. Still `intent`: **crew as named NPCs and cargo as tracked goods** — both are PLACEHOLDER
  integers on `ShipDetails`. **#3000**.
- **Servants, vaults, estates** — split by verification:
  - ✅ **Vault security / access lists / theft** — DONE (`VaultDetails` + `VaultAccessEntry` +
    vault services, org vaults with holdings/transit; `steal`/`steal_permitted` +
    `TheftNotPermitted` gate).
  - **Servant daily-life behaviors** — fetch shipped (#2276); meal/bath prep, message-carrying,
    announcing visitors, guard/doorman duty, and `assign_servant`/`unassign_servant` remain.
    **#2989**.
  - **Building→neighborhood→domain progression** — #696 (open).
  - ✅ **Room-feature systems** — DONE far beyond Sanctum: Library, Training Room, Lab, Command
    Center, Granary, Siege Deck, Bank, Notice Board, Town Crier, Social Hub, Vault, Brig, Stables,
    Workshop of Iniquity — all registered, seeded, with live effects. (#675/#673 closed.)
  - **Property purchase + decoration economy** — the *acquisition front door* (buy land/rooms,
    commission construction with coin) and the furnishing loop (decor → room stats read in scenes)
    are unbuilt over shipped substrate. **#2991**.
- **Touchstone items + magical reagents + personal attunement framework** — `partial`. #707 shipped
  the framework (ADR-0087); a full per-resonance/per-tier catalog is separate content-authoring work.
  Follow-up: #1859 (leveled/Path-scaled component requirements).
- **Asset / Companion subsystem** — #672 (closed as umbrella). Companion/familiar half shipped;
  NPCAsset informant promotion shipped (#1872). Still `intent`: gifts/paths built around
  companionship beyond the one shipped Gift; distinction-granted starting assets; asset gameplay
  loops (tasking/intel/income); compromise/loss lifecycle; voluntary sharing; guard/fan/minor-ally
  variants.

## Species & racial framework

- **Species/racial framework** — the substrate AND seeded ability content shipped (`SpeciesGiftGrant`
  + provisioning #1580, sun-sensitive species, moon content #2845, appetite/shade content;
  environmental vulnerability via #1740). Content authoring continues on #2764. Still unbuilt, the
  two *mechanics* halves — **#2993**:
  - **Language mechanics** — `Language` + `grants_species_languages` exist and #2463 authored
    content, but nothing grants languages to characters: no per-character storage, no CG/heredity
    grant path, no speech integration.
  - **Racial progression** — "growing stronger at racial abilities"; no species-scoped advancement
    track exists in `world/progression`.

## GM tooling, missions, knowledge

- **Umpire check-modifier tooling** — GM applies ±difficulty/advantage in-flight. `intent`.
- **GM trust→risk leveling curve**; **live Situation/Encounter session resolvers** (beyond the GM-mark
  placeholder); **cross-table GM availability marketplace**. `intent`.
- **Mission player journey on `action.run()`** — mission play runs only through a ViewSet today
  (ADR-0001 gap); plus group invite/consent handshake (#887) and player discovery board. (The
  formerly-listed instanced-room wiring #886, categorical room binding #888, and reward sinks #932
  have all closed.) `partial`.
- **Clue/investigation journal UI** — a web surface for held clues + research pursuit; still listed in
  [investigation-discovery.md](investigation-discovery.md). Passive trigger sources landed (#1160
  closed); past-life/scandal clue kinds remain. `partial`.
- **Collaborative research** (start/contribute project) and **codex teaching** (accept/cancel) — service
  layers exist, no player surface. `partial`.
- ✅ **Returning-player wrap-up of FORECLOSED threads** — DONE (#1188, ADR-0039).
- **Achievement content + notification delivery** — the engine is built and stat hooks are wired, but
  definitions are thin and **delivery is silent** (no personal/room/gamewide announcement on earn).
  Ongoing content tracking: #2377, #2831. `partial`.
- **GM trap placement/arming** — only disarm exists; `Trap.is_armed` is set only programmatically.
  `intent` — **#3002**.

## World texture (registered 2026-08-05)

The "world feels inhabited" cluster — promised by design-tenets/ADRs or left as the unbuilt half of a
shipped system, now each filed:

- **Body markings** — tattoos/scars/brands as skin-layer features riding the shipped coverage/reveal
  pipeline (#2965/#2846 anticipate them in code comments). `intent` — **#2985**.
- **Gossip & rumor authoring** — tidings is read-only and derived (no models); missions' RUMOR reward
  sink is a stub; relationship gossip unbuilt. `intent` — **#2986**.
- **Bystander reaction menus** — ADR-0032's witness pop-up choice trees; witness-approach substrate
  shipped (#1824), the interactive half didn't. `intent` — **#2987**.
- **Ambient room texture** — roaming flavor emits + room-state risk telegraphing ("a seedy district
  can spawn pickpockets"); feeder stats exist, no consumer. `intent` — **#2988**.
- **Mood/stance system** — declared expressive state instead of pose-parsing (design-tenets). `intent`
  — **#2994**.
- **Block/mute system** — the OOC safety primitive staff-inbox/journals/ooc-social all depend on.
  `intent` — **#2996**.
- **IC calendar lore + festivals** — lore month names + feast-day cycle over the shipped clock/
  `FeastDay` hook. `intent` — **#2762**.
- **Web surfaces for dreams & kinship** — both backends fully built, telnet/CG-only. `partial` —
  **#3003**.
- **Dead wires sweep** — scene-dp award (broken + uncalled), level-change hook (uncalled), goals XP
  (recorded, never granted), boundaries seed cluster (unwired), FACET_ATTACH production seed path
  (missing). **#3004**.

## Doors, traps & misc

- ✅ **Door lock/unlock** — DONE (#1866; `LockAction`/`UnlockAction` + `CmdLock`/`CmdUnlock`).
- **Persona minting** (create/edit/delete an identity) — reserved for future IC flows. `intent`.
- **Tidings posting/reacting/commenting** — feed is read-only; no authoring model. `intent` — **#2986**
  (folded into gossip & rumor authoring; supersedes #1450's reader-side epic).
- **Scandal reach & containment — BUILT (#1464, ADR-0082)** with civic-hub reader (#1450) and witness
  handling (#1824). Still open: an async prompted-choice containment UX at fork time; venue vitality
  (PC-owned RP hubs) is its own future umbrella.
- **Roster release / end-tenure**; **events RSVP-accept** (invitee response); **projects activation
  service** — small but real gaps where one half of a loop is unbuilt. `intent`.
