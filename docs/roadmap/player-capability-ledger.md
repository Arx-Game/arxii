# Player Capability & Identity Ledger

**Status:** the single source of truth for *"what can a player do and be — and is it
releasable?"* across magic, combat, identity, and progression. Domain docs
([`combat.md`](combat.md), [`magic.md`](magic.md),
[`character-progression.md`](character-progression.md), [`species.md`](species.md))
carry the detail and link up here; planned-but-unbuilt systems live in
[`planned-systems.md`](planned-systems.md).

This ledger was rebuilt from a **code-and-test verification pass (2026-06-27)**, not from
prior roadmap prose. Where it and a domain doc disagree, **this ledger and the code win**.

## The governing tenets (read first)

1. **No improvised mechanics (the MVP bar).** Anything a player should *plausibly* be able to
   do — or any event that can plausibly happen (a war, a charm, a summons) — must have a
   **real system** to resolve it. A GM forced to wing it for an uncovered capability is a
   disaster: it puts canonical veracity and fairness in question and forces retcons. The bar
   is **coverage of plausible intent**, not exhaustive handling of rare permutations.
2. **Dazzling combinations are the product.** The point is a *dazzling number of combinations*
   across identity axes (species/lineage × gift × path × resonance × distinction × covenant
   role) so players feel special in what they can **do** and **be**. The combinatorial space is
   the product, not a nice-to-have. Realized by the one specialization engine (ADR-0055).
3. **Closed-issue ≠ proven.** A capability is "done" only when an **end-to-end test
   demonstrates the expected outcome**. "Someone merged it" and "the roadmap says SHIPPED" are
   not evidence. (This audit found the combat roadmap citing a proof file —
   `test_e2e_combat_magic_api.py` — that does not exist.)

## Tier legend

| Tier | Meaning | Treat as |
|---|---|---|
| ✅ **PROVEN** | An E2E/journey test drives the path and asserts the outcome | Done |
| 🟨 **WIRED-UNPROVEN** | Real code path exists end-to-end, but no test asserts the outcome | **Not done** — "write the journey test + fix what it exposes" is work |
| 🟧 **BUILT-NOT-WIRED** | Service/model exists but no player surface reaches it | Not done — wire it (after checking it isn't a duplicate) |
| 🟡 **SUBSTRATE** | Primitives/fields exist; the player-experienced capability isn't assembled | Not done — assemble it |
| ❌ **ABSENT** | grep + read confirm no code | Greenfield |

A row may be ❌/🟡 **and** carry **→ DESIGNED (ADR-xxxx)**: the design decision exists (an ADR),
the build does not. Those are *build-to-the-ADR* work, **not** open design questions.

The **MVP?** column is a *proposal* for your ranking. `MVP` = needed for a releasable character
system; `now` = `priority:now` keystone; `MVP+ADR` = MVP and reverses a recorded decision; `soon` =
MVP-or-immediately-after; `P2` = Phase 2 (recorded, not launch), **no-improv-flagged** the moment an
in-fiction trigger is plausible.

---

## Pillar BE — Identity (who you are)

| Capability | Tier | Evidence / home | MVP? |
|---|---|---|---|
| Species as **stat-bonuses** + name hierarchy | ✅ PROVEN | `world/species/models.py` | done |
| **Distinctions** (effects→modifiers, can grant *rituals*) | ✅ PROVEN | `world/distinctions/models.py` | done |
| Paths (models, next-options, path-intent) | ✅ PROVEN | `world/classes`, `world/progression` | done |
| Species **abilities/traits** beyond stats | ✅ PROVEN (infrastructure) | **ADR-0050** + **#1580**: `SpeciesGiftGrant` + `provision_species_gifts` + GIFT anchor cap (`path_stage × 10`) + RESISTANCE pull-effect; E2E `test_species_gift_e2e.py`. Pending: seed real species Minor Gift data. | now |
| **khati / vampire / lycan**, lineage / bloodline | 🟡 SUBSTRATE | **ADR-0050** + **#1580** (plumbing built — `SpeciesGiftGrant` + `provision_species_gifts`); no species → Minor Gift data rows seeded yet | now |
| Species / lineage / distinction **grants a gift** | ✅ PROVEN | **ADR-0050** + **#1580**: `SpeciesGiftGrant` through-model + `provision_species_gifts` mints `CharacterGift` + latent GIFT thread; E2E `test_species_gift_e2e.py` | now |
| Species **vulnerabilities** (vampire↔sunlight) + immunity framework | 🟡 SUBSTRATE | **#1580**: minimum substrate built — `EffectKind.RESISTANCE` + `ConditionResistanceModifier` net at `apply_damage_to_participant` (ADR-0062); broad framework + environmental triggers → **#1588** | MVP |
| Resonance as an identity axis that *differs* your magic | ❌ → DESIGNED | **ADR-0052/0055** (gift affinity + technique form from resonance) | MVP |

---

## Pillar DO — Acts & effects (what you can do in a scene or fight)

| Capability | Tier | Evidence / home | MVP? |
|---|---|---|---|
| Cast → pose → log → outcome loop | ✅ PROVEN | `cast_services.py`; magic.md | done |
| Damage technique cast at an NPC → health drops | ✅ PROVEN | `test_combat_cast_telnet_e2e.py` (check mocked) | done |
| DEFEND halves / INTERPOSE zeroes incoming damage | ✅ PROVEN | `test_defend_stance.py`, `test_interpose_damage_path.py` | done |
| Escalation → Audere offer → accept → power change | ✅ PROVEN | `test_escalation_integration.py`, `test_audere_telnet_e2e.py` | done |
| Apply a condition to an **enemy NPC** (and it's consumed) | 🟨 WIRED-UNPROVEN | `combat/services.py:471-520`; only ally tested | prove-it |
| Combo attack **full journey** | 🟨 WIRED-UNPROVEN | `services.py:3356-3367`; pieces unit-tested only | prove-it |
| Thread pull changes a cast/clash **final outcome** | 🟨 WIRED-UNPROVEN | reaches check input; final outcome not asserted | prove-it |
| **Remove / dispel** a condition (cleanse) | ✅ PROVEN | `TechniqueRemovedCondition` payload + `remove_technique_conditions` (`world/magic/services/condition_application.py`) wired into the cast seam; honors `can_be_dispelled` + opposed `cure_check_type`/`cure_difficulty`; E2E `world/magic/tests/integration/test_dispel_cast_e2e.py` (#1585, ADR-0064) | done |
| **Charm / switch-sides** an enemy NPC | ✅ PROVEN | `derive_allegiance` → `select_npc_actions` (#1590, ADR-0058) | MVP |
| **Negotiate / parley** an NPC down | ✅ PROVEN | `apply_social_disposition_delta` → `adjust_npc_affection`; durable + ephemeral tiers (#1591, ADR-0058) | MVP |
| **Effect palette**: summon, reflect, incorporeal, sink, telekinesis, teleport, obstacle, force-field | ✅ PROVEN | `effect_palette_content.py`; 9 seeded effects; summon E2E `integration_tests/pipeline/test_effect_summon_telnet_e2e.py`; reactive interceptor E2Es `integration_tests/pipeline/test_effect_reactive_families.py` (#1584) | done |
| **Companions / pets / summons** w/ breath weapons & ordered abilities | ✅ PROVEN (basic) | ALLY `CombatOpponent` via `allegiance`/`summoned_by`; opponent-vs-opponent damage; advanced ordered abilities are a follow-up | done (ADR-0059; #672 folds in) |
| **Roles grant techniques** (resonance-spec at lvl 3) | ✅ PROVEN | **ADR-0055** (the specialization engine); `CovenantRole` inherits `AbstractSpecializedVariant` + `fire_variant_discoveries` generalizes the discovery beat across `target_kind`; proven by `covenants/tests/integration/test_resonance_subrole_flow.py` (covenant) + `magic/tests/integration/test_gift_specialization_e2e.py` (gift) | done |
| **War / battle system** | ✅ PROVEN (spine) | **#1592** — spine landed: `Battle` (1:1 Scene extension), `BattleSide` / `BattlePlace` / `BattleUnit` / `BattleRound` / `BattleParticipant` / `BattleActionDeclaration`; `BattleRoundContext` wired into `get_active_round_context`; services + REGISTRY actions + `CmdBattle` (`battle declare\|round\|resolve\|conclude`); E2E `test_battle_telnet_e2e.py` proves stage → declare → resolve → conclude. Deferred: peril/rescue (#1710), AFK knobs (#1711), battle page (#1712), Audere weighting (#1713), rich type-matchups (#1714), naval/siege (#1715), campaign-stakes propagation + win-gated Legend (#1716). | soon |
| Mounts / charging · flying mounts / dragons | ❌ ABSENT | planned-systems (aerial positioning exists, no mount) | P2 |
| Ranged / archery mechanics | 🟡 SUBSTRATE | range bands + RANGED class exist | soon |

---

## Pillar GROW — Acquisition & progression (how you get stronger)

| Capability | Tier | Evidence / home | MVP? |
|---|---|---|---|
| Author your **own** new techniques | ✅ PROVEN | `author_technique` | done |
| Gain a **new Gift** in play (post-CG) | 🟨 PARTIAL | **Path-crossing grant ✅ PROVEN** — crossing into a new Path mints its Gift(s) via `PathGiftGrant` + `grant_path_magic` (#1579, `test_path_crossing_grant_e2e.py`). Weave/XP-buy acquisition of a standalone Minor Gift (**ADR-0050** + **ADR-0053**) is still → #1587. | MVP |
| Grow stronger in a gift (more/stronger techniques) | ✅ PROVEN | **ADR-0051** + **#1581**: gift-technique variants resolve at cast time via `resolve_specialized_variant` (wired into `get_runtime_technique_stats` + `_resolve_and_pose_cast`), gated on `unlock_thread_level`. Gift-thread also confers the standard always-in-action thread bonus (`_ALWAYS_IN_ACTION_KINDS`, wired in #1580). Imbue premium kept (`ThreadPullCost.imbue_cost_multiplier`); pull cost stays uniform — no per-kind penalty at point of use. Dev seed authors starter variants. E2E: `test_gift_specialization_e2e.py` (`test_variant_takes_effect_at_cast`). | done |
| **Learn / train / buy** an existing technique | ❌ → DESIGNED | **ADR-0056** (signature thread for one technique) + **ADR-0053** (unlock gate) | MVP |
| **Leveling grants magical power** (unlocks gifts/techniques) | ✅ PROVEN | **Path-crossing grant ✅ PROVEN** — advancing into a new Path grants that Path's Gift + a curated starter technique set per (Path × Gift) (#1579, ADR-0055 grant leg; `test_path_crossing_grant_e2e.py`). **Within-tier gift-thread strength axis ✅ PROVEN** — imbuing raises `Thread.level`; once it crosses a `TechniqueVariant.unlock_thread_level`, `resolve_specialized_variant` returns the resonance-specific variant form at cast time (ADR-0051, #1581; `test_variant_takes_effect_at_cast`). | **now (foundational)** |
| Trainer / teaching system | ❌ ABSENT | (`MentorBond` is a combat bond, not teaching) | soon |
| Path-crossing (Audere Majora) — change path in play | ✅ PROVEN | offer created by cast hook `maybe_create_audere_majora_offer` (`world/magic/services/techniques.py` Step 8c); journey driven E2E in `test_audere_telnet_e2e.py` | done |
| Ritual of the Durance level-up | 🟨 WIRED-UNPROVEN | works via generic machinery but **unseeded** | fix |
| Codex teaching / learning | 🟧 BUILT-NOT-WIRED | `CodexTeachingOffer.accept` has no player surface | soon |

---

## Pillar COMBINE — the specialization engine (how your axes make you singular)

| Capability | Tier | Evidence / home | MVP? |
|---|---|---|---|
| Covenant role resolution `(role × resonance × thread level)` → sub-role | ✅ PROVEN | `resolve_effective_role`; the **template** to generalize | done |
| **One specialization primitive** `(entity × resonance) → customized capability` | ✅ PROVEN | **ADR-0055** — `AbstractSpecializedVariant` base + `resolve_specialized_variant(entity, character)` (the one resolver; `resolve_effective_role` is a shim); `test_gift_specialization_e2e.py` | done |
| **Gift × Path → specialized techniques** | ✅ PROVEN | **ADR-0055** — the (Gift × Path) leg sets the *base technique set*: `PathGiftGrant` + `grant_path_magic` mint a path-specific curated set from a shared Gift on crossing (#1579, `test_path_crossing_grant_e2e.py`); resonance then specializes each on read via `TechniqueVariant` (#1578, `test_gift_specialization_e2e.py`) | done |
| **Resonance differentiates your magic** (gift affinity + technique form) | ✅ PROVEN | **ADR-0052** (gift affinity = thread resonance) + **ADR-0055** (derive-on-read); `gift_resonances_for` feeds the four cast sites; `test_gift_specialization_e2e.py` | done |
| **Signature technique** (motif-signed additive flourish on one technique) | ✅ PROVEN (partial) | **ADR-0065** (supersedes ADR-0056; motif-bonus model, not resonance-divergence; bonus is ADDITIVE, not a `TechniqueVariant`): `SignatureMotifBonus` catalog + `Thread.signature_bonus` FK + selection service (`services/signature.py`) + actions (`SignatureSet/Clear/List`) + `CmdSignature`; `flat_intensity_delta` + bonus conditions wired into both cast paths; non-combat cosmetic narration (`signature_clause`). Proven: `test_signature_motif_e2e.py`. **Deferred fast-follows:** `damage_profiles` combat seam, capability-grant cast seam, combat cosmetic narration, web `SignatureViewSet`. | soon |
| **Fall / Redemption** resonance conversion (asymmetric) | ❌ → DESIGNED | **ADR-0054** (new conversion service; respect monotonic `lifetime_earned`) | soon |
| **Covenant of the Court** lets a peerless puissant hold a role | ✅ PROVEN | **ADR-0057** (amended 2026-06-30, #1589) — `CovenantType.COURT` + `Covenant.leader` FK + `CourtPact` (grant cap) + gulf enforcement (`power_tier_for_level`) + mission-driven engagement (`has_active_court_mission`) + fealty ceremony; proven by `world/covenants/tests/integration/test_court_e2e.py` | done |
| Multi-PC group combos `(effect-type × resonance)` | ✅ PROVEN | `ComboDefinition`/`ComboSlot` (group, not personal) | done |

---

## MVP work slate (derived from the tiers above)

A large build program; this ledger makes it **sequenceable and honest**. Five flavors:

### `priority:now` keystones (everything else stacks on these)
- **Major/Minor gifts** (ADR-0050) — the gift taxonomy. *Nothing else in the gift/resonance economy can be built until this exists* (species abilities, gift acquisition, gift-thread strength all depend on it).
- **The specialization primitive** (ADR-0055) — generalize `resolve_effective_role` into the one `(entity × resonance) → capability` engine. The COMBINE pillar and "roles grant techniques" depend on it.
- **Level → power coupling** (ADR-0053 + 0051) — leveling/XP must unlock gifts/techniques (today: nothing).

### Build-new (ABSENT / substrate — build to the ADR, or greenfield)
- **Identity (ADR-0050):** species abilities / lineage / khati / vampire / lycan as Minor Gifts — the infrastructure is built (#1580: `SpeciesGiftGrant` + `provision_species_gifts` + RESISTANCE substrate); pending: seed real species Minor Gift data. Broad immunity/vulnerability framework + environmental triggers → #1588 (ADR-0062).
- **Gift/resonance economy (ADR-0050–0056):** Minor-Gift acquisition; GIFT thread anchor + per-target-kind cost (0051); gift-resonance-from-thread refactor (0052); the specialization engine (0055); signature re-scope of `TargetKind.TECHNIQUE` (0056); fall/redemption conversion service (0054).
- **Covenants:** `CovenantType.COURT` + Court roles (ADR-0057) — **SHIPPED #1589** (see PROVEN row above).
- **Effects:** the effect palette — **SHIPPED #1584** (9 effects: summon/reflect [Mirror Ward]/
  incorporeal [Ghostform]/sink [Earthmeld]/telekinesis [Force Grip]/teleport [Phase Jump]/
  obstacle [Barricade]/force-field [Aegis Field]/blink [Phase Step]; allegiance-aware summon
  proven E2E; reactive interceptor trio proven E2E; ADR-0059 + ADR-0060). Remaining effects work:
  charm/switch-sides (#1590, allegiance-flip); NPC negotiation (#1591); condition removal/dispel
  (#1585, shipped — `TechniqueRemovedCondition` + `remove_technique_conditions`, ADR-0064).
  Teleport/obstacle/telekinesis have placeholder position IDs — runtime destination selection
  deferred to a follow-up issue.
- **Combat systems:** war/battle system; mounts & flying (P2, no-improv-flagged); ranged/archery enforcement.

### Prove-it (WIRED-UNPROVEN — write the journey E2E, fix what it exposes)
- Enemy-NPC condition application · combo full journey · thread-pull final outcome.

### Fix (integrity / foundational holes)
- `CharacterGiftViewSet` unguarded `ModelViewSet` (mints gift bindings, bypasses `action.run`).
- Audere Majora: verify the private DB seed of `AudereMajoraThreshold` rows
  (boundary levels 5/10/15/20) exists in the live DB. The offer-creation cast
  hook (`techniques.py:950`) is wired and E2E-tested, but the gate returns
  `None` at gate 2 unless those threshold rows are present. Ceremony text
  (`vision_text`/`manifestation_text`) is intentionally DB-authored only, never
  committed (see `world/magic/CLAUDE.md`, Audere & Audere Majora). No code
  change; an ops/seed-verification check.
- Ritual of the Durance unseeded.

### Cut (sludge — close, per "no rare permutations")
- #1297 (unreachable hardening), #1549 (gang-finish edge), #1213 (jargon reconciliation), #1363 (re-frame as the resonance-aware-checks design question — now COMBINE work, not a standalone ticket).

---

## Domain docs & deeper detail

- Combat detail & build history: [`combat.md`](combat.md) · [`combat-build-history.md`](combat-build-history.md)
- Magic detail & build history: [`magic.md`](magic.md) · [`magic-build-history.md`](magic-build-history.md)
- Progression / classes / paths: [`character-progression.md`](character-progression.md)
- Identity / species: [`species.md`](species.md)
- Covenants & roles: [`covenants.md`](covenants.md)
- Planned-but-unbuilt registry: [`planned-systems.md`](planned-systems.md)
- Decisions: [`../adr/README.md`](../adr/README.md) — esp. ADR-0050–0057 (gift/resonance economy + Court)
- Design tenets: [`design-tenets.md`](design-tenets.md)
