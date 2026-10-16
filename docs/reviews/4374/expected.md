# #4374 real-testing pass: expected results (written 2026-10-16 before any run)

Source: issue #4333 spec design 3 and 4, rulings 17 and 18, walkthrough A steps 3 and 4,
and the demo (player screen 4, onlooker screen 2, Admin 2). Numbers are this seed's.

Seed: Ombrin (pool 100, Silk favored), one pledge type (favor target 5, closing rite
"Ombrin's rite", tier 1). CLOSING awards 8 / 5 / 3 / 2 / 0 (seeded favor terms). Vision
cost 10 from the pool. Answers on the pledge type: Partial Success (follow-up = mission
clue), Failure; a general (no pledge type) Critical Failure answer. The Success answer is
written by staff in the Answer builder during the pass (every part: fact clue = codex clue,
follow-up = mission clue, cost pool = "Marked by Ombrin" at every tier, Silk line).
Critical Success has no answer of its own.

## Rules the results must follow (from the spec, not the code)
- No fact text and no fact clue below Success.
- No follow-up clue on Failure or Critical Failure.
- A close at a tier with no answer falls to the pledge type's next lower tier, then the
  being's general answers (design 4 draw order). Critical Success -> the Success answer.
- One Silk line per vision even when two Silk items were sacrificed; the second Silk item
  and the plain item are listed by name after the lines.
- The vision names Ombrin unless the answer conceals its source.
- Onlookers see "<name> performs Ombrin's rite." then the answer's onlooker line, and
  nothing else of the answer (no delay, answer, fact, cost, follow-up, prayer text).
- A first Failure or Critical Failure close: no vision, one retry offered.
- Short pool: the answer is held, no vision, nothing handed over; staff see it held on the
  Deity Editor; once the pool can pay, the daily tick sends it with everything it carries.
- A lapse at half the target or more pays the Partial Success award (3 base) and never a
  vision.

## Per character
1. Ysmay (Chosen, 200%), web. Pledge; sacrifice silk scarf (20: 2 base x2 = 4, +8),
   silk ribbon (10: 1 x2 = 2, +4), brass bell (10: 1, +2). Ready to close (14 of 5).
   Close on the card. If Success or Critical Success: closing award 5 or 8 base, x2;
   a vision from Ombrin with, in order, the Success delay text; the Success answer text
   followed by ONE Silk line and "Also sacrificed: silk ribbon, brass bell."; the fact
   text; the cost text; the follow-up text; footnotes naming the codex clue, the mission
   clue and "Marked by Ombrin". She knows the codex entry, holds the mission, has the
   condition. Pool drops by 10 (plus whatever the sacrifices added before).
   If Partial Success: the Partial answer, no fact, the mission handed over.
2. Tobiah (100%), telnet. pledge, sacrifice silk shawl (50: 5 base x2 = 10, +10), close.
   Needed tier: a higher tier than Ysmay's if she got Success (re-run with rollmod raised
   when needed). Critical Success -> the Success answer (fallback), every part, |G[VISION]|n.
3. Orla (rollmod -100, secret faith Ombrin), web dispatch. Pledge with a prayer, sacrifice
   copper bowl (50: +5), close twice. First: Failure or Critical Failure, no vision, retry.
   Second: resolves; Failure -> the Failure answer (delay, answer, cost only; no fact, no
   clue of any kind; condition applied); Critical Failure -> the general CF answer. Room:
   rite line then that answer's onlooker line; her prayer text never in a room line.
4. Hobb (100%), telnet. pledge, sacrifice clay cup (+5). Before his close the pool is set to
   5. Close: answer held; no vision; Deity Editor Visions tab lists 1 held answer; no room
   onlooker line. Pool set to 100, `deliver_held_answers` (the daily tick's callable) runs:
   1 delivered, his vision appears (telnet on reconnect / sheet), held list empty.
5. Wren (100%). pledge, sacrifice tin cup (30: +3 = 3 of 5, at least half). Time limit moved
   into the past; `scan_active_projects` (the lifecycle tick's callable): +3 favor (Partial
   Success award 3 base), Lapsed, no vision, no held answer.
6. Brother Caddoc, telnet, in the room: sees the rite lines and onlooker lines only.
7. Staff in the Answer builder: the coverage grid shows Partial 1, Failure 1 on the pledge
   row and Critical Failure 1 on the general row; writing the Success answer saves it,
   credits it to the staff contributor, the preview shows it; trying a fact on Partial
   Success is refused with the tier rule.
