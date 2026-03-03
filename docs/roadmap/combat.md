# Combat

**Status:** not-started
**Depends on:** Traits, Skills, Magic, Conditions, Mechanics, Relationships (for combo attacks)

## Overview
Combat is always Players vs. the Bad Guys — no PVP killing. Three distinct combat modes serve different scales and narrative purposes, all designed to create heroic moments and reward teamwork over solo power.

## Key Design Points
- **Party Combat:** The main form. An adventuring party vs. boss, NPC group, or boss + minions. Unapologetically designed for groups — bosses are nearly impossible to hurt without combo attacks. This forces teamwork and prevents solo characters from ignoring the relationship game. Designed to feel like superhero/fantasy team-up arcs: characters get battered, pushed to the edge, and then break through with an Audere Majora
- **Battle Scenes:** Large-scale abstracted conflicts — potentially hundreds of PCs vs. an army, god, or kaiju-scale force. Fixed number of rounds. Characters contribute (or subtract) victory points based on actions each round, with random damage/death risk. Final outcome determined by total victory points: crushing defeat to overwhelming victory
- **Duels:** Non-lethal sparring only. Designed to be slow — characters pose and build rich moments between rounds. For showing off and Enemies-to-Lovers arcs, not for killing. Story-first design
- **No symmetrical PVP:** Frees balance design to focus on "feels cool" rather than "perfectly fair"
- **Magic is predominant:** Gifts should greatly move the needle. Higher Path steps and threshold crossings should feel transformative in combat
- **Relationship bonuses in combat:** Romance gives collaborative bonuses; if one partner is near death, the other gets an overwhelming bonus nudging them toward an Audere Majora. Rivalries give intensity bonuses. Party bonds improve coordination
- **Level considerations:** Need caps to prevent low-level characters from feeling worthless, while still allowing them to participate meaningfully

## What Exists
- **Models:** Conditions app has combat-relevant fields (affects_turn_order, draws_aggro, turn_order_modifier, aggro_priority). Mechanics app has modifier collection and stacking rules. Checks app has the roll resolution engine. Attempts app has narrative consequence layer with roulette display
- **Supporting systems:** The check/attempt pipeline is built — trait-to-rank conversion, result charts, weighted trait composition, narrative consequence roulette. Conditions with stage progression and DoT exist
- **No dedicated combat models** — no encounters, initiative tracking, targeting, damage resolution, or party management

## What's Needed for MVP
- Combat encounter model — tracking participants, turn order, rounds, state
- Party Combat system — initiative, targeting, combo attack mechanics, boss vulnerability windows
- Battle Scene system — victory point tracking, round management, risk/reward action choices, mass participant handling
- Duel system — slow-paced sparring with pose integration, non-lethal resolution
- NPC combat AI — behavior for bosses, minions, and battle scene forces
- Combo attack mechanics — how characters combine abilities for amplified effects
- Relationship modifier integration — bonuses from bonds, romance, rivalry applied situationally
- Audere Majora trigger conditions — detecting when a character is at the threshold of a breakthrough in combat
- Magic integration — techniques and gifts as combat actions
- Damage and healing resolution
- Death/defeat mechanics (character death possible in Party Combat and Battle Scenes, never in Duels)
- Combat UI — web-first interface for all three modes

## Notes
