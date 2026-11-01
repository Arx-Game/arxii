# B: expected results, written before the run

Branch head: `b8ac97bdba5ec93362d460113bf86391c4e4ab06` (feature-4802-involuntary-control-loss-one-mechanism-m).
Database: throwaway `rt_4802f`. Server: this worktree's own `just start`.

Every number here comes from the seeded rows and the rulings, not from anything the code printed.

## Seeded numbers used

- Berserk's compulsion (the real seed, `ensure_berserk_compulsion`): base difficulty 25, +2 per
  severity, wants an attack. Forbidden extras: flee +5, parley +5, leave +10, change back +10.
  Bands: Critical Success and Success act freely; Partial Success acts strained (penalty 4,
  Control -2); Failure acts for the compulsion (Control -2); Critical Failure acts for the
  compulsion (Control -4). Retry wait outside combat: 5 minutes.
- Mira, Vela and Kael carry Berserk at severity 3.
- Seeded wound trigger on "Wound rage" (Doran, Kael): below 50% health, "Hold the rage" vs 20,
  Failure and Critical Failure apply Berserk 3 for 3 rounds, Control -6, Intensity +4.
- Every fighter starts at 100/100 health. NPC hits in round 1: Brute's Haymaker 60 on Brann,
  Ogre's Crusher 150 on Doran, Troll's Haymaker 60 on Kael, Vash's Slap 10 on Garrick.
- Staging: a "forced" roll is a staff rollmod of -200 on the character (every roll lands on face
  1) plus, where one exact outcome is needed, a flat check modifier from a staging condition.
  Both are written before the step and named in its transcript.

## Item 4: telnet, compelled Mira

1. Round 1, declaring. Mira types `combat flee`. Difficulty = 25 + 2x3 + 5 = 36. Expected, exactly:
   `Against Berserk: Resist compulsion check, difficulty 36. If it fails, you attack instead.`
2. Between rounds (after round 1 resolves), roll forced to fail. Mira types `combat leave`.
   Difficulty = 25 + 2x3 + 10 = 41. Expected: a roll line
   `Mira tries to leave the encounter against Berserk. Resist compulsion vs 41: <a failing outcome>.`
   followed by `You cannot break away.` She stays an active participant. Tomas, in the room,
   reads the roll line.
3. She types `combat leave` again in the same between-rounds window. Expected, exactly:
   `Berserk still holds you. You can try again next round.` No second roll line anywhere.
   DB: her seat stays ACTIVE and records the round of the failed try.

## Item 8: Ruling 47, intensity rises as the roll worsens

1. Admin ADD form, Control Loss Trigger: vulnerability Battle fever (Brann carries it), wound
   threshold below 50%, check Hold the rage, base difficulty 20. Bands:

   | Outcome | Intensity | Control | Condition |
   |---|---|---|---|
   | Critical Success | 0 | 0 | none |
   | Success | 2 | 0 | none |
   | Partial Success | 3 | -1 | none |
   | Failure | 4 | -2 | none |
   | Critical Failure | 5 | -3 | none |

   Expected: it saves with no error (Ruling 47: intensity is not held to "better roll, never
   worse"), and the reloaded change page shows intensities 0, 2, 3, 4, 5.
2. Live: Brann takes Haymaker 60 (100 to 40, crosses 50%), roll forced to Failure. Expected line:
   `Brann falls below 50% health. Brann fights to keep control. Hold the rage vs 20: Failure. Control -2 · Intensity +4.`
   No condition is named, since the band applies none. DB: Brann's combat engagement intensity
   modifier rises by exactly 4 and control modifier falls by exactly 2.

## Item 9: one case per ruling

- **Ruling 16** (Sela, no compulsion, wears a talked-down self, "the Mourner", whose emergence
  condition Grief-stricken is active). `form revert` expected:
  `You can't revert while not in control of yourself.` No roll line. DB: still wearing the Mourner.
- **Ruling 20** (Vela, Berserk 3, out of combat, wears "the Red Hound", roll forced to fail).
  First `form revert`: a roll line `Vela tries to change back against Berserk. Resist compulsion vs 41: <a failing outcome>.`
  and a refusal. Second `form revert` straight after: `Berserk still holds you. You can try again in 5 minutes.`
  (a wait naming minutes) and no second roll. DB: the Berserk instance carries a retry time
  about 5 minutes after the first try; she still wears the Red Hound.
- **Ruling 21** (Doran carries the 50% wound trigger, takes Crusher 150: 100 to -50, a killing
  hit). Expected: no `falls below 50% health` / `Hold the rage` line for Doran, and no Berserk
  instance on him afterwards, even though his roll is staged to fail.
- **Ruling 22** (Mira, Berserk 3, declares `combat cover Tomas`; Tomas declares `combat flee`;
  Mira's resist forced to Partial Success). Difficulty = 25 + 2x3 = 31 (cover is not a forbidden
  action). Expected: `Mira tries to cover against Berserk. Resist compulsion vs 31: Partial Success.`
  Cover goes ahead (no "Berserk wins out" line, her cover row survives), and nothing reduces it:
  Cover has no roll of its own, so the strained penalty has nothing to land on, and the bonus
  she gives Tomas's flee is her full cover bonus. Her control falls by 2 (the band). No line
  should tell the room that her cover took a penalty.
- **Ruling 24** (Kael, already under Berserk, carries the 50% wound trigger, takes Haymaker 60:
  100 to 40). Expected: no `Hold the rage` roll line for Kael; his Berserk instance is the
  same one (severity 3), no new one.

## Item 10: masked Garrick, seen by Tomas

Garrick types `persona mask scarred sellsword`. His real face has a portrait
(`https://example.invalid/portraits/garrick-real-face.png`); the mask has none.

Expected on every surface Tomas reads: the mask's name, never "Garrick", never the real portrait.

- Surge (staff `gm dramatic Garrick reason=...`): Tomas's telnet reads
  `scarred sellsword's power surges with sudden, dramatic force.` (the default surge template).
- Clash (Garrick commits `clash Gorr with Maul`, the round resolves): the encounter API's clash
  contributor name is the mask's name.
- Portrait: the encounter API participant row for Garrick has the mask's name and an empty
  portrait, not the real-face URL; the web combat panel shows no real face.
- Held back (Garrick declares no action): `scarred sellsword holds back.`
- Scene feed: the interaction for Vash's Slap on Garrick tags the mask persona's id as its
  target, not the primary persona's id.
