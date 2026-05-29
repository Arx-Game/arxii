# Design Tenets

> **Read order:** [ROADMAP.md](ROADMAP.md) covers the top-level pillars
> ("Engagement is survival", "No PVP killing", "Heroic by design", "Web-first
> UX"). This document elaborates the more specific rules that flow from those
> pillars — the day-to-day judgment calls that come up while designing
> systems. Per-system docs (e.g. `combat.md`, `missions.md`) cover
> system-specific design; this doc is the cross-cutting layer.

---

## Player respect (hard rules)

These are structural defenses against abuse. They don't bend for cool-sounding
features — when a tradeoff is between "could a bad actor abuse this" and "cool
mechanic," the hard rule wins.

### No invisible characters, ever

The visibility model has no "hidden observer" mode for any role — not staff,
not GMs, not players. There is no `is_invisible` flag, no `staff_only_can_see`
mode, no "system can see hidden characters" backdoor. If a character is in a
room, every other character in the room can see them.

The corollary: any feature that would need invisibility (lurking, scry-from-a-
distance, omniscient staff observation) has to be redesigned around the
constraint. The right architectural answer for "watch a scene without
participating" is to enter as a separate persona, not to become invisible.

### Public means public

Public-room sessions are open to all players — no allowlist, no quiet-presence
mode, no "I'm here but don't show up in the participant list." If a player
wants privacy, the session goes in an instanced room (party-only); if it's in
a shared world room, anyone in that room can engage with it.

Story-info visibility is per-PC scoped (you see what your character would know),
not per-account or per-player. A player with two PCs in a room sees what each
PC's identity would let them see, not the union.

### Never out alts

Account-scoped surfaces (an account's full PC list, their cross-PC activity
log, OOC details that would link two PCs to the same person) are staff-only
and explicitly permission-gated. UI displays are by persona — never by
account. Even staff tooling that necessarily reveals the linkage should
require an explicit "you are about to view account-linked data" gate.

## Cooperative RP bedrock

### PC antagonism only happens when both players want it

Conflict between PCs (combat, theft, betrayal, social attacks) requires consent
from the targeted player. This subsumes "no PVP killing" (a stronger ROADMAP
pillar) — even non-lethal antagonism needs buy-in from the target. Systems
must never put players at cross-purposes unintentionally.

The friction this introduces (a thief can't just steal from any PC) is
intentional. Drama between PCs is high-value when both players are invested;
toxic when one player is being targeted without consent.

### Constrained bystander reactions

Witnesses to a scene get **pop-up choice menus** (predefined reactions:
"report to authorities later", "intervene now", "do nothing"), not free-form
mechanical interference. This preserves the active player's agency over their
own scene while still giving witnesses real choices.

The "report afterwards" path runs **after** the active player's action
resolves, not during. The thief steals; the witness reacts later. No
"witnessed mid-action" mechanic that interrupts the player's turn.

## Risk & consequence

### Risk is a conscious player choice

Players always know what they're walking into before they commit. Risk LEVEL
is predictable from visible room state (a "seedy" district can spawn
pickpockets; a "lawful" one cannot). Dangerous areas are clearly marked. No
pop-up ambushes that surprise players with consequences they couldn't foresee.

The corollary — **opt-in risk**: dungeon delves, mission infiltrations, and
combat encounters are explicitly opted into. Once inside, surprise within the
encounter is fine (that's the heroic-arc engine). Surprise *getting into* the
encounter is not.

Roaming is mostly atmospheric. The overwhelming majority of room flavor when
traveling is non-engaging — ambient texture, not required encounters. Players
do not have to stop and resolve things while traveling.

### Consequences make narrative sense

Consequences (wounds, conditions, outcomes) must make narrative sense for the
triggering situation. A player receiving an outcome they don't know how to RP
about is a major red flag. Nonsensical outcomes (a physical scar from psychic
damage, a wound to the wrong body part for the attack type) break immersion
immediately.

Consequence pools should be "dumb" — just weighted lists. The routing logic
upstream selects the right pool based on damage type, severity, body context,
etc. Never let a generic pool produce outcomes that don't fit the triggering
context.

### Bite-sized encounters

Story encounters should resolve cleanly enough per-session that PCs can return
to normal RP and normal life between sessions. Avoid persistent "PC is stuck
in X" states that block the player from engaging with the rest of the game
between GM sessions.

A GM session might run multiple shorter encounters; what matters is that the
PC's situation is wrappable at session end, not that the entire arc concludes.

## Player agency

### Frictionless RP entry

Zero ceremony to start RPing. A player who logs in and wants to RP with
whoever is in the room shouldn't have to enable a mode, declare a session,
register a participation token, or click anything beyond the actual pose.
Organic RP must remain unmarked even when the DB *could* detect it — adding
a confirmation step kills momentum.

The corollary: systems that reward RP must work on detected-but-undeclared
activity. Rewards run after the fact based on what the system observed, not
based on what the player opted-in to.

### Never parse pose text for mechanics

The system never reads what a player writes for mechanical effects. No "if
your pose contains the word 'attack' then trigger an attack roll." Mechanical
inputs come from explicit opt-in toggles (mood, stance, action buttons) — pose
text is purely narrative expression.

Reasons: parsing is brittle (typos, RTL text, creative phrasing), it punishes
expressive writing, and it creates an arms race where players game the parser.
The mood/stance system gives players the same expressive surface without the
parsing trap.

### GM authority is constrained

GMs **author** story trees with pre-defined rolls and outcomes. Live play
runs through that authored content. GMs apply check modifiers based on
creative play (umpire role) and branch the tree on the fly, but they don't
decide outcomes by fiat — the player roll resolves what happens.

This means: live tools (the GM-during-session UI) are secondary to authoring
tools (the GM-pre-session UI). The thing GMs spend the most time on must be
the thing the staff frontend is best at.

Corollary: a GM saying "you take damage" without rolling for it is a system
failure, not a feature. Always route through `perform_check` with the
appropriate CheckType — character stats, conditions, buffs, relationships
all influence the outcome.

## UX placement

### IC vs UI placement test

The question to ask for any new feature: would this make sense as a thing a
character does in a physical place (IC), or as a UI panel a player interacts
with (out-of-character)?

- **Abstract bookkeeping** (inventory list, character sheet, achievement
  log, settings, social feeds) → UI panels / commands. These don't need
  to exist as physical places.
- **Room-bound concrete features that players invest in** (a shop the
  character built and stocked, an estate they own, a research library
  they curated) → physical space the character visits IC. These reward
  the character's investment by living in the world.

The test: would a player feel a sense of ownership / pride about the
existence of this thing in the world? If yes, IC space. If it's just
admin, UI.

### IC vs OOC ownership boundary

**IC possessions belong to the character.** Items, gold, in-game reputation,
society standing, in-game property — these are tied to the character. If the
character dies (or is permanently removed from play), these go with them.

**OOC rewards belong to the account.** XP, kudos, friend tracking,
achievements, OOC reputation — these are tied to the player behind the
screen. They persist across characters. Account #2's old character earned
kudos for great RP; the new character starts from zero but the account keeps
the kudos count.

The line is: does this reward the *character's existence in the world* or
the *player's craft and contribution*? Character → IC. Player → OOC.

---

## What's NOT here

This doc covers cross-cutting design principles. System-specific design lives
in the per-system docs (`combat.md`, `missions.md`, etc.). Engineering
conventions (code style, project structure, testing tiers) live in
[`CLAUDE.md`](../../CLAUDE.md). If you're looking for "how should I structure
this view" or "where do I put this model", those are the right files.
